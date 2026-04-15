from __future__ import annotations

import json
from dataclasses import dataclass

from agent.decision import find_priority
from agent.learning import get_learning_state, update_from_feedback
from agent.llm import build_llm_motivation
from agent.planner import generate_diet_plan, generate_exercise_plan
from agent.progress import summarize_progress
from agent.reminder import generate_reminder
from agent.trend import detect_trend
from agent.utility import normalize, calculate_utility, validate_input
from database.db import (
    get_coaching_state,
    fetch_recent_health_rows,
    get_latest_health_row,
    get_user_profile,
    insert_health_row,
    update_latest_health_feedback,
    consume_user_preferences,
)


@dataclass(frozen=True)
class CoachResponse:
    priorities: list[str]
    trend: str
    reminders: list[str]
    motivation: str
    exercise_headline: str
    exercise_plan: str
    diet_headline: str
    diet_plan: str
    coaching_targets: dict
    checkin_advice: list[str] | None = None
    reflection: dict | None = None
    progress: dict | None = None
    utility: float | None = None
    learning_state: dict | None = None


def _motivation(priorities: list[str], trend: str, streak: int) -> str:
    if streak >= 5:
        return "You’ve built a strong streak. Today is about staying consistent — small wins compound."
    if trend == "Improving":
        return "Momentum is on your side. Let’s keep it simple and repeat what’s working."
    if priorities:
        focus = ", ".join(priorities[:2])
        return f"Today we focus on {focus}. You don’t need perfect — you need done."
    return "You’re in maintenance mode today. Keep your habits steady."


def _checkin_guardrail_advice(today: dict, coaching: dict) -> list[str]:
    advice: list[str] = []
    sleep_hours = float(today.get("sleep") or 0.0)
    sleep_goal = float(coaching.get("sleep_goal") or 7.5)
    if sleep_hours >= 10.0:
        advice.append(
            f"You logged {sleep_hours:.1f}h sleep, which is higher than your current target ({sleep_goal:.1f}h). "
            "Try tightening to a regular 7-9h sleep window tonight."
        )
    elif 0.0 < sleep_hours < 6.0:
        advice.append(
            f"You logged {sleep_hours:.1f}h sleep, which is low for recovery. "
            "Aim for an earlier wind-down and move toward 7-8h."
        )
    return advice


def run_daily_coach(*, user_id: int = 1, today: dict, coaching_strategy: str = "balanced_plan") -> CoachResponse:
    """
    Perception: validate + load memory (profile, targets, last row)
    Reasoning: internal utility + priorities
    Action: detailed plans + reminders + motivation
    Learning: handled separately via apply_feedback()
    """
    create = validate_input(today)
    normalized = normalize(create)

    profile = get_user_profile(user_id=user_id)
    coaching = get_coaching_state(user_id=user_id)
    learning = get_learning_state(user_id=user_id)
    preferences = learning.get("preferences") or {}

    # Internal utility used for action scoring and UI diagnostics.
    _utility = calculate_utility(normalized, learning["weights"])

    previous = get_latest_health_row(user_id=user_id)
    trend = detect_trend(create, previous) if previous else "No previous data"

    priorities = find_priority(
        create,
        coaching=coaching,
        threshold=float(learning["threshold"]),
    )

    action_coaching = dict(coaching)
    strategy = str(coaching_strategy or "balanced_plan").strip().lower()
    if strategy == "easy_plan":
        action_coaching["exercise_goal"] = max(10, int(round(int(coaching["exercise_goal"]) * 0.8)))
        action_coaching["steps_goal"] = max(4000, int(round(int(coaching["steps_goal"]) * 0.9)))
    elif strategy == "intense_plan":
        action_coaching["exercise_goal"] = min(90, int(round(int(coaching["exercise_goal"]) * 1.15)))
        action_coaching["steps_goal"] = min(14000, int(round(int(coaching["steps_goal"]) * 1.1)))

    # Act (utility-based): generate a few candidates and choose the best under preferences.
    # We intentionally keep this simple (2 variants) but it closes the loop: action is selected by a utility score.
    def _load_avoid_set(prefs: dict) -> set[str]:
        raw = prefs.get("avoid_activities") or "[]"
        try:
            return set(json.loads(raw))
        except Exception:
            return set()

    prefer_cardio = float(preferences.get("prefer_cardio") or 0.5)
    base_avoid = _load_avoid_set(preferences)

    prefs_allow_cardio = dict(preferences)
    prefs_allow_cardio["avoid_activities"] = json.dumps(sorted({x for x in base_avoid if x != "cardio"}))

    prefs_block_cardio = dict(preferences)
    prefs_block_cardio["avoid_activities"] = json.dumps(sorted(set(base_avoid) | {"cardio"}))

    ex_allow = generate_exercise_plan(
        priorities=priorities, profile=profile, coaching=action_coaching, today=create, preferences=prefs_allow_cardio
    )
    ex_block = generate_exercise_plan(
        priorities=priorities, profile=profile, coaching=action_coaching, today=create, preferences=prefs_block_cardio
    )

    # Utility score: health utility + preference alignment
    def _score_ex(plan_meta: dict) -> float:
        contains_cardio = bool(plan_meta.get("contains_cardio"))
        # Alignment reward: if prefer_cardio=1, reward cardio plans; if 0, reward no-cardio plans
        align = (prefer_cardio if contains_cardio else (1.0 - prefer_cardio))
        # Hard-constraint penalty if cardio is currently avoided but plan contains it
        penalty = 0.0
        if "cardio" in base_avoid and contains_cardio:
            penalty += 1.0
        return float(_utility) + (0.35 * align) - penalty

    score_allow = _score_ex(ex_allow.meta or {})
    score_block = _score_ex(ex_block.meta or {})
    exercise = ex_allow if score_allow >= score_block else ex_block
    chosen_ex_variant = "allow_cardio" if exercise is ex_allow else "block_cardio"

    diet = generate_diet_plan(
        priorities=priorities, profile=profile, coaching=action_coaching, today=create, preferences=preferences
    )

    reminders = generate_reminder(
        priorities=priorities,
        failure_count=int(learning["failure_count"]),
        coaching=coaching,
    )
    motivation = _motivation(priorities, trend, int(coaching.get("streak", 0)))
    motivation = build_llm_motivation(
        user_name=str(profile.get("name") or ""),
        goal=str(profile.get("goal") or ""),
        priorities=priorities,
        trend=trend,
        fallback_message=motivation,
        utility=float(_utility),
    )
    checkin_advice = _checkin_guardrail_advice(create, coaching)

    # Reflect (informational): summarize whether progress looks normal.
    recent = fetch_recent_health_rows(user_id=user_id, limit=21)
    recent = list(reversed(recent)) if recent else []
    progress = summarize_progress(recent, coaching=coaching)
    # Daily guardrail: do not show an "Improving" headline when today's check-in is clearly poor.
    goals = {
        "steps": float(coaching.get("steps_goal") or 8000),
        "sleep": float(coaching.get("sleep_goal") or 7.5),
        "water": float(coaching.get("water_goal") or 8),
        "exercise": float(coaching.get("exercise_goal") or 30),
    }
    today_ratio = {
        k: (float(create.get(k) or 0.0) / goals[k] if goals[k] > 0 else 0.0)
        for k in ["steps", "sleep", "water", "exercise"]
    }
    today_met_count = sum(1 for v in today_ratio.values() if v >= 0.85)
    today_very_low_count = sum(1 for v in today_ratio.values() if v < 0.40)
    if today_met_count == 0 and today_very_low_count >= 2:
        progress = type(progress)(
            verdict="Needs attention",
            message="Today’s check-in is well below target in multiple areas. Let’s simplify today and rebuild consistency tomorrow.",
            stats=progress.stats,
        )

    # Store today’s check-in (utility is stored for internal monitoring only)
    reflection_payload = {
        "act": {
            "coaching_strategy": strategy,
            "exercise_variant": chosen_ex_variant,
            "exercise_score_allow": round(float(score_allow), 3),
            "exercise_score_block": round(float(score_block), 3),
        },
        "plan_meta": {
            "exercise": exercise.meta,
            "diet": diet.meta,
        },
        # snapshot what the agent believed at action time (useful for reflection)
        "preferences_snapshot": {k: v for k, v in preferences.items() if k != "prefer_cardio"} | {"prefer_cardio": prefer_cardio},
    }
    insert_health_row(
        {
            **create,
            "feedback": None,
            "utility": _utility,
            "adherence": None,
            "rating": None,
            "notes": json.dumps(reflection_payload),
        },
        user_id=user_id,
    )

    # Preferences are temporary (next-plan only). Consume after planning.
    consume_user_preferences(user_id=user_id)

    return CoachResponse(
        priorities=priorities,
        trend=trend,
        reminders=reminders,
        motivation=motivation,
        exercise_headline=exercise.headline,
        exercise_plan=exercise.details,
        diet_headline=diet.headline,
        diet_plan=diet.details,
        coaching_targets=coaching,
        checkin_advice=checkin_advice,
        reflection=reflection_payload,
        progress={"verdict": progress.verdict, "message": progress.message, "stats": progress.stats},
        utility=float(_utility),
        learning_state={
            "weights": learning.get("weights", {}),
            "threshold": float(learning.get("threshold", 0.75)),
            "failure_count": int(learning.get("failure_count", 0)),
        },
    )


def apply_feedback(*, user_id: int = 1, priorities: list[str], adherence: int | None, rating: int | None, text: str | None) -> dict:
    """
    Learning step: updates weights/threshold + coaching targets based on user feedback.
    """
    update_latest_health_feedback(
        user_id=user_id,
        feedback=text,
        adherence=adherence,
        rating=rating,
        notes=None,
    )

    # Reflect: compare outcome/feedback with what we actually recommended (stored in notes JSON).
    latest = get_latest_health_row(user_id=user_id)
    context: dict | None = None
    if latest and latest.get("notes"):
        try:
            context = json.loads(latest.get("notes") or "")
        except Exception:
            context = None
    return update_from_feedback(
        user_id=user_id,
        priorities=priorities,
        adherence=adherence,
        rating=rating,
        feedback_text=text,
        context=context,
    )

