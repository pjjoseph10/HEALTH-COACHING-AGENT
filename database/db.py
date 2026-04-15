import sqlite3

DB_FILE = "data/health.db"

def connect():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    # Reduce write-lock contention under Streamlit reruns.
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
    except sqlite3.OperationalError:
        # If DB is temporarily locked during initialization, the timeout will handle most cases.
        pass
    return conn

def _column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())

def _table_exists(cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None

def _table_sql(cursor, table: str) -> str:
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
    row = cursor.fetchone()
    return row[0] or "" if row else ""

def create_tables():
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        display_name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS health_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        steps INTEGER,
        sleep REAL,
        water INTEGER,
        exercise INTEGER,
        feedback TEXT,
        utility REAL,
        adherence INTEGER,
        rating INTEGER,
        notes TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS learning_state (
        id INTEGER PRIMARY KEY,
        user_id INTEGER DEFAULT 1,
        steps_weight REAL,
        sleep_weight REAL,
        water_weight REAL,
        exercise_weight REAL,
        prefer_cardio REAL,
        threshold REAL,
        failure_count INTEGER,
        learning_rate REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        name TEXT,
        age INTEGER,
        sex TEXT,
        height_cm REAL,
        weight_kg REAL,
        goal TEXT,
        dietary_preference TEXT,
        allergies TEXT,
        injuries TEXT,
        equipment TEXT,
        schedule TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS coaching_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        steps_goal INTEGER,
        sleep_goal REAL,
        water_goal INTEGER,
        exercise_goal INTEGER,
        streak INTEGER,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        uses_left INTEGER DEFAULT 1,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, key)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS learning_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        steps_weight REAL NOT NULL,
        sleep_weight REAL NOT NULL,
        water_weight REAL NOT NULL,
        exercise_weight REAL NOT NULL,
        threshold REAL NOT NULL,
        failure_count INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Hard migration: old single-user tables used CHECK(id=1) which blocks multi-user inserts.
    # Rebuild them into multi-user friendly tables and copy legacy row to user_id=1.
    legacy_profile_sql = _table_sql(cursor, "user_profile")
    if "CHECK (id = 1)" in legacy_profile_sql or "CHECK(id = 1)" in legacy_profile_sql:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profile_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT,
            age INTEGER,
            sex TEXT,
            height_cm REAL,
            weight_kg REAL,
            goal TEXT,
            dietary_preference TEXT,
            allergies TEXT,
            injuries TEXT,
            equipment TEXT,
            schedule TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        INSERT INTO user_profile_new
        (user_id, name, age, sex, height_cm, weight_kg, goal, dietary_preference, allergies, injuries, equipment, schedule, updated_at)
        SELECT 1, name, age, sex, height_cm, weight_kg, goal, dietary_preference, allergies, injuries, equipment, schedule, updated_at
        FROM user_profile
        WHERE id = 1
        """)
        cursor.execute("DROP TABLE user_profile")
        cursor.execute("ALTER TABLE user_profile_new RENAME TO user_profile")

    legacy_coaching_sql = _table_sql(cursor, "coaching_state")
    if "CHECK (id = 1)" in legacy_coaching_sql or "CHECK(id = 1)" in legacy_coaching_sql:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS coaching_state_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            steps_goal INTEGER,
            sleep_goal REAL,
            water_goal INTEGER,
            exercise_goal INTEGER,
            streak INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        INSERT INTO coaching_state_new
        (user_id, steps_goal, sleep_goal, water_goal, exercise_goal, streak, updated_at)
        SELECT 1, steps_goal, sleep_goal, water_goal, exercise_goal, streak, updated_at
        FROM coaching_state
        WHERE id = 1
        """)
        cursor.execute("DROP TABLE coaching_state")
        cursor.execute("ALTER TABLE coaching_state_new RENAME TO coaching_state")

    # Lightweight forward-compat migrations for existing DBs.
    # (CREATE TABLE IF NOT EXISTS won't add columns to existing tables.)
    if not _column_exists(cursor, "health_data", "user_id"):
        cursor.execute("ALTER TABLE health_data ADD COLUMN user_id INTEGER DEFAULT 1")
    if not _column_exists(cursor, "learning_state", "user_id"):
        cursor.execute("ALTER TABLE learning_state ADD COLUMN user_id INTEGER DEFAULT 1")
    if not _column_exists(cursor, "user_profile", "user_id"):
        cursor.execute("ALTER TABLE user_profile ADD COLUMN user_id INTEGER DEFAULT 1")
    if not _column_exists(cursor, "coaching_state", "user_id"):
        cursor.execute("ALTER TABLE coaching_state ADD COLUMN user_id INTEGER DEFAULT 1")

    if not _column_exists(cursor, "learning_state", "learning_rate"):
        cursor.execute("ALTER TABLE learning_state ADD COLUMN learning_rate REAL DEFAULT 0.08")
    if not _column_exists(cursor, "learning_state", "prefer_cardio"):
        cursor.execute("ALTER TABLE learning_state ADD COLUMN prefer_cardio REAL DEFAULT 0.5")
    if _table_exists(cursor, "user_preferences") and not _column_exists(cursor, "user_preferences", "uses_left"):
        cursor.execute("ALTER TABLE user_preferences ADD COLUMN uses_left INTEGER DEFAULT 1")

    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_learning_state_user ON learning_state(user_id)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profile_user ON user_profile(user_id)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_coaching_state_user ON coaching_state(user_id)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_preferences_user_key ON user_preferences(user_id, key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_data_user_date ON health_data(user_id, date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_history_user_date ON learning_history(user_id, created_at)")

    # Ensure there is at least one user (id=1) for legacy single-user data.
    cursor.execute("INSERT OR IGNORE INTO users (id, display_name) VALUES (1, 'Default user')")

    # Ensure learning_state row exists (compat with old DBs).
    if _column_exists(cursor, "learning_state", "learning_rate") and _column_exists(cursor, "learning_state", "prefer_cardio"):
        cursor.execute(
            """
            INSERT OR IGNORE INTO learning_state
            (id, user_id, steps_weight, sleep_weight, water_weight, exercise_weight, prefer_cardio, threshold, failure_count, learning_rate)
            VALUES (1, 1, 0.30, 0.30, 0.20, 0.20, 0.5, 0.75, 0, 0.08)
            """
        )
    elif _column_exists(cursor, "learning_state", "learning_rate"):
        cursor.execute(
            """
            INSERT OR IGNORE INTO learning_state
            (id, user_id, steps_weight, sleep_weight, water_weight, exercise_weight, threshold, failure_count, learning_rate)
            VALUES (1, 1, 0.30, 0.30, 0.20, 0.20, 0.75, 0, 0.08)
            """
        )
    else:
        cursor.execute(
            """
            INSERT OR IGNORE INTO learning_state
            (id, user_id, steps_weight, sleep_weight, water_weight, exercise_weight, threshold, failure_count)
            VALUES (1, 1, 0.30, 0.30, 0.20, 0.20, 0.75, 0)
            """
        )

    cursor.execute(
        """
        INSERT OR IGNORE INTO user_profile
        (user_id, name, goal)
        VALUES (1, '', 'general_fitness')
        """
    )

    cursor.execute(
        """
        INSERT OR IGNORE INTO coaching_state
        (id, user_id, steps_goal, sleep_goal, water_goal, exercise_goal, streak)
        VALUES (1, 1, 8000, 7.5, 8, 30, 0)
        """
    )
    for col, ddl in [
        ("adherence", "ALTER TABLE health_data ADD COLUMN adherence INTEGER"),
        ("rating", "ALTER TABLE health_data ADD COLUMN rating INTEGER"),
        ("notes", "ALTER TABLE health_data ADD COLUMN notes TEXT"),
    ]:
        if not _column_exists(cursor, "health_data", col):
            cursor.execute(ddl)

    conn.commit()
    conn.close()

def list_users():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, display_name FROM users ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "display_name": r[1]} for r in rows]

def create_user(display_name: str) -> int:
    conn = connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (display_name) VALUES (?)", (display_name.strip() or "User",))
    user_id = cur.lastrowid
    cur.execute(
        """
        INSERT OR IGNORE INTO user_profile (user_id, name, goal)
        VALUES (?, ?, 'general_fitness')
        """,
        (int(user_id), display_name.strip()),
    )
    cur.execute(
        """
        INSERT OR IGNORE INTO coaching_state (user_id, steps_goal, sleep_goal, water_goal, exercise_goal, streak)
        VALUES (?, 8000, 7.5, 8, 30, 0)
        """,
        (int(user_id),),
    )
    cur.execute(
        """
        INSERT OR IGNORE INTO learning_state (user_id, steps_weight, sleep_weight, water_weight, exercise_weight, prefer_cardio, threshold, failure_count, learning_rate)
        VALUES (?, 0.30, 0.30, 0.20, 0.20, 0.5, 0.75, 0, 0.08)
        """,
        (int(user_id),),
    )
    conn.commit()
    conn.close()
    return int(user_id)

def get_latest_health_row(*, user_id: int = 1):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT steps, sleep, water, exercise, feedback, utility, adherence, rating, notes, date
        FROM health_data
        WHERE user_id = ?
        ORDER BY date DESC
        LIMIT 1
        """
        ,
        (int(user_id),),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "steps": row[0],
        "sleep": row[1],
        "water": row[2],
        "exercise": row[3],
        "feedback": row[4],
        "utility": row[5],
        "adherence": row[6],
        "rating": row[7],
        "notes": row[8],
        "date": row[9],
    }

def insert_health_row(data: dict, *, user_id: int = 1):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO health_data
        (user_id, steps, sleep, water, exercise, feedback, utility, adherence, rating, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            int(data.get("steps") or 0),
            float(data.get("sleep") or 0),
            int(data.get("water") or 0),
            int(data.get("exercise") or 0),
            data.get("feedback"),
            float(data.get("utility") or 0),
            (None if data.get("adherence") is None else int(data.get("adherence"))),
            (None if data.get("rating") is None else int(data.get("rating"))),
            data.get("notes"),
        ),
    )
    conn.commit()
    conn.close()

def update_latest_health_feedback(*, user_id: int = 1, feedback: str | None, adherence: int | None, rating: int | None, notes: str | None):
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id FROM health_data WHERE user_id = ? ORDER BY date DESC LIMIT 1", (int(user_id),))
    row = cur.fetchone()
    if not row:
        conn.close()
        return
    latest_id = row[0]
    cur.execute(
        """
        UPDATE health_data
        SET feedback = ?,
            adherence = ?,
            rating = ?,
            notes = COALESCE(?, notes)
        WHERE id = ?
        """,
        (
            feedback,
            (None if adherence is None else int(adherence)),
            (None if rating is None else int(rating)),
            notes,
            int(latest_id),
        ),
    )
    conn.commit()
    conn.close()

def fetch_recent_health_rows(*, user_id: int = 1, limit: int = 14):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT steps, sleep, water, exercise, adherence, rating, date
        FROM health_data
        WHERE user_id = ?
        ORDER BY date DESC
        LIMIT ?
        """,
        (int(user_id), int(limit)),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "steps": r[0],
            "sleep": r[1],
            "water": r[2],
            "exercise": r[3],
            "adherence": r[4],
            "rating": r[5],
            "date": r[6],
        }
        for r in rows
    ]


def fetch_recent_decision_rows(*, user_id: int = 1, limit: int = 40):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT adherence, rating, utility, notes, date
        FROM health_data
        WHERE user_id = ?
        ORDER BY date DESC
        LIMIT ?
        """,
        (int(user_id), int(limit)),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "adherence": r[0],
            "rating": r[1],
            "utility": r[2],
            "notes": r[3],
            "date": r[4],
        }
        for r in rows
    ]

def get_learning_state_row(*, user_id: int = 1):
    conn = connect()
    cur = conn.cursor()
    has_prefer_cardio = _column_exists(cur, "learning_state", "prefer_cardio")
    if has_prefer_cardio:
        cur.execute(
            """
            SELECT steps_weight, sleep_weight, water_weight, exercise_weight, prefer_cardio, threshold, failure_count, learning_rate
            FROM learning_state
            WHERE user_id = ?
            """,
            (int(user_id),),
        )
    else:
        cur.execute(
            """
            SELECT steps_weight, sleep_weight, water_weight, exercise_weight, threshold, failure_count, learning_rate
            FROM learning_state
            WHERE user_id = ?
            """,
            (int(user_id),),
        )
    row = cur.fetchone()
    if row is None:
        if has_prefer_cardio:
            cur.execute(
                """
                INSERT OR IGNORE INTO learning_state
                (user_id, steps_weight, sleep_weight, water_weight, exercise_weight, prefer_cardio, threshold, failure_count, learning_rate)
                VALUES (?, 0.30, 0.30, 0.20, 0.20, 0.5, 0.75, 0, 0.08)
                """,
                (int(user_id),),
            )
        else:
            cur.execute(
                """
                INSERT OR IGNORE INTO learning_state
                (user_id, steps_weight, sleep_weight, water_weight, exercise_weight, threshold, failure_count, learning_rate)
                VALUES (?, 0.30, 0.30, 0.20, 0.20, 0.75, 0, 0.08)
                """,
                (int(user_id),),
            )
        conn.commit()
        if has_prefer_cardio:
            cur.execute(
                """
                SELECT steps_weight, sleep_weight, water_weight, exercise_weight, prefer_cardio, threshold, failure_count, learning_rate
                FROM learning_state
                WHERE user_id = ?
                """,
                (int(user_id),),
            )
        else:
            cur.execute(
                """
                SELECT steps_weight, sleep_weight, water_weight, exercise_weight, threshold, failure_count, learning_rate
                FROM learning_state
                WHERE user_id = ?
                """,
                (int(user_id),),
            )
        row = cur.fetchone()
    conn.close()
    return row

def update_learning_state_row(
    *,
    user_id: int = 1,
    steps_weight: float,
    sleep_weight: float,
    water_weight: float,
    exercise_weight: float,
    prefer_cardio: float | None = None,
    threshold: float,
    failure_count: int,
    learning_rate: float,
):
    conn = connect()
    cur = conn.cursor()
    has_prefer_cardio = _column_exists(cur, "learning_state", "prefer_cardio")
    if has_prefer_cardio:
        cur.execute(
            """
            UPDATE learning_state
            SET steps_weight = ?,
                sleep_weight = ?,
                water_weight = ?,
                exercise_weight = ?,
                prefer_cardio = ?,
                threshold = ?,
                failure_count = ?,
                learning_rate = ?
            WHERE user_id = ?
            """,
            (
                float(steps_weight),
                float(sleep_weight),
                float(water_weight),
                float(exercise_weight),
                float(0.5 if prefer_cardio is None else prefer_cardio),
                float(threshold),
                int(failure_count),
                float(learning_rate),
                int(user_id),
            ),
        )
    else:
        cur.execute(
            """
            UPDATE learning_state
            SET steps_weight = ?,
                sleep_weight = ?,
                water_weight = ?,
                exercise_weight = ?,
                threshold = ?,
                failure_count = ?,
                learning_rate = ?
            WHERE user_id = ?
            """,
            (
                float(steps_weight),
                float(sleep_weight),
                float(water_weight),
                float(exercise_weight),
                float(threshold),
                int(failure_count),
                float(learning_rate),
                int(user_id),
            ),
        )
    conn.commit()
    conn.close()


def insert_learning_history_row(
    *,
    user_id: int = 1,
    steps_weight: float,
    sleep_weight: float,
    water_weight: float,
    exercise_weight: float,
    threshold: float,
    failure_count: int,
):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO learning_history
        (user_id, steps_weight, sleep_weight, water_weight, exercise_weight, threshold, failure_count)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            float(steps_weight),
            float(sleep_weight),
            float(water_weight),
            float(exercise_weight),
            float(threshold),
            int(failure_count),
        ),
    )
    conn.commit()
    conn.close()


def fetch_learning_history(*, user_id: int = 1, limit: int = 30):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT steps_weight, sleep_weight, water_weight, exercise_weight, threshold, failure_count, created_at
        FROM learning_history
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (int(user_id), int(limit)),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "steps": r[0],
            "sleep": r[1],
            "water": r[2],
            "exercise": r[3],
            "threshold": r[4],
            "failure_count": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]

def get_coaching_state(*, user_id: int = 1):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT steps_goal, sleep_goal, water_goal, exercise_goal, streak FROM coaching_state WHERE user_id = ?",
        (int(user_id),),
    )
    row = cur.fetchone()
    if row is None:
        cur.execute(
            """
            INSERT OR IGNORE INTO coaching_state
            (user_id, steps_goal, sleep_goal, water_goal, exercise_goal, streak)
            VALUES (?, 8000, 7.5, 8, 30, 0)
            """,
            (int(user_id),),
        )
        conn.commit()
        cur.execute(
            "SELECT steps_goal, sleep_goal, water_goal, exercise_goal, streak FROM coaching_state WHERE user_id = ?",
            (int(user_id),),
        )
        row = cur.fetchone()
    conn.close()
    return {
        "steps_goal": row[0],
        "sleep_goal": row[1],
        "water_goal": row[2],
        "exercise_goal": row[3],
        "streak": row[4],
    }

def update_coaching_state(*, user_id: int = 1, steps_goal: int, sleep_goal: float, water_goal: int, exercise_goal: int, streak: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE coaching_state
        SET steps_goal = ?,
            sleep_goal = ?,
            water_goal = ?,
            exercise_goal = ?,
            streak = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
        """,
        (int(steps_goal), float(sleep_goal), int(water_goal), int(exercise_goal), int(streak), int(user_id)),
    )
    conn.commit()
    conn.close()

def get_user_profile(*, user_id: int = 1):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT name, age, sex, height_cm, weight_kg, goal, dietary_preference, allergies, injuries, equipment, schedule
        FROM user_profile
        WHERE user_id = ?
        """
        ,
        (int(user_id),),
    )
    row = cur.fetchone()
    if row is None:
        cur.execute(
            """
            INSERT OR IGNORE INTO user_profile
            (user_id, name, goal)
            VALUES (?, '', 'general_fitness')
            """,
            (int(user_id),),
        )
        conn.commit()
        cur.execute(
            """
            SELECT name, age, sex, height_cm, weight_kg, goal, dietary_preference, allergies, injuries, equipment, schedule
            FROM user_profile
            WHERE user_id = ?
            """,
            (int(user_id),),
        )
        row = cur.fetchone()
    conn.close()
    if row is None:
        # Ultra-safe fallback (e.g., if DB is in a partial migration state).
        return {
            "name": "",
            "age": None,
            "sex": "",
            "height_cm": None,
            "weight_kg": None,
            "goal": "general_fitness",
            "dietary_preference": "",
            "allergies": "",
            "injuries": "",
            "equipment": "",
            "schedule": "",
        }
    return {
        "name": row[0] or "",
        "age": row[1],
        "sex": row[2] or "",
        "height_cm": row[3],
        "weight_kg": row[4],
        "goal": row[5] or "general_fitness",
        "dietary_preference": row[6] or "",
        "allergies": row[7] or "",
        "injuries": row[8] or "",
        "equipment": row[9] or "",
        "schedule": row[10] or "",
    }

def upsert_user_profile(profile: dict, *, user_id: int = 1):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_profile
        (user_id, name, age, sex, height_cm, weight_kg, goal, dietary_preference, allergies, injuries, equipment, schedule, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            name = excluded.name,
            age = excluded.age,
            sex = excluded.sex,
            height_cm = excluded.height_cm,
            weight_kg = excluded.weight_kg,
            goal = excluded.goal,
            dietary_preference = excluded.dietary_preference,
            allergies = excluded.allergies,
            injuries = excluded.injuries,
            equipment = excluded.equipment,
            schedule = excluded.schedule,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            int(user_id),
            profile.get("name") or "",
            profile.get("age"),
            profile.get("sex") or "",
            profile.get("height_cm"),
            profile.get("weight_kg"),
            profile.get("goal") or "general_fitness",
            profile.get("dietary_preference") or "",
            profile.get("allergies") or "",
            profile.get("injuries") or "",
            profile.get("equipment") or "",
            profile.get("schedule") or "",
        ),
    )
    conn.commit()
    conn.close()


def get_user_preferences(*, user_id: int = 1) -> dict[str, str]:
    conn = connect()
    cur = conn.cursor()
    if not _table_exists(cur, "user_preferences"):
        # If code is used outside Streamlit (tests/imports), ensure schema exists.
        conn.close()
        create_tables()
        conn = connect()
        cur = conn.cursor()
        if not _table_exists(cur, "user_preferences"):
            conn.close()
            return {}
    cur.execute(
        """
        SELECT key, value
        FROM user_preferences
        WHERE user_id = ?
          AND (uses_left IS NULL OR uses_left > 0)
        """,
        (int(user_id),),
    )
    rows = cur.fetchall()
    conn.close()
    return {str(k): str(v) for (k, v) in rows}


def upsert_user_preference(*, user_id: int = 1, key: str, value: str):
    conn = connect()
    cur = conn.cursor()
    if not _table_exists(cur, "user_preferences"):
        conn.close()
        create_tables()
        conn = connect()
        cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_preferences (user_id, key, value, uses_left, updated_at)
        VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, key) DO UPDATE SET
            value = excluded.value,
            uses_left = 1,
            updated_at = CURRENT_TIMESTAMP
        """,
        (int(user_id), str(key), str(value)),
    )
    conn.commit()
    conn.close()


def consume_user_preferences(*, user_id: int = 1):
    """
    Make preferences temporary: after one use, decrement and remove when depleted.
    Called after a plan is generated.
    """
    conn = connect()
    cur = conn.cursor()
    if not _table_exists(cur, "user_preferences"):
        conn.close()
        return
    if not _column_exists(cur, "user_preferences", "uses_left"):
        conn.close()
        return
    cur.execute(
        """
        UPDATE user_preferences
        SET uses_left = COALESCE(uses_left, 1) - 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
        """,
        (int(user_id),),
    )
    cur.execute(
        """
        DELETE FROM user_preferences
        WHERE user_id = ?
          AND uses_left <= 0
        """,
        (int(user_id),),
    )
    conn.commit()
    conn.close()
