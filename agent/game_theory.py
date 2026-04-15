from __future__ import annotations

import json
import math


STRATEGIES = ("easy_plan", "balanced_plan", "intense_plan")
OUTCOMES = ("adhere", "partial", "drop")


def _extract_strategy(notes: str | None) -> str:
    if not notes:
        return "balanced_plan"
    try:
        payload = json.loads(notes)
        strategy = str(((payload.get("act") or {}).get("coaching_strategy") or "")).strip().lower()
        if strategy in STRATEGIES:
            return strategy
    except Exception:
        pass
    return "balanced_plan"


def _classify_outcome(row: dict) -> str:
    adherence = row.get("adherence")
    rating = row.get("rating")
    if adherence == 1:
        return "adhere"
    if adherence == 0:
        return "drop"
    if rating is not None:
        try:
            r = int(rating)
            if r >= 4:
                return "adhere"
            if r <= 2:
                return "drop"
        except Exception:
            pass
    return "partial"


def build_payoff_matrix(rows: list[dict]) -> dict:
    """
    Build empirical payoff matrix:
    strategy x user-outcome -> average payoff.
    """
    # priors keep matrix stable for small data.
    payoff_sum = {
        s: {"adhere": 2.0, "partial": 1.0, "drop": 0.2}
        for s in STRATEGIES
    }
    count = {
        s: {"adhere": 1, "partial": 1, "drop": 1}
        for s in STRATEGIES
    }

    for row in rows:
        strategy = _extract_strategy(row.get("notes"))
        outcome = _classify_outcome(row)
        utility = float(row.get("utility") or 0.0)
        rating = row.get("rating")
        rating_bonus = 0.0
        if rating is not None:
            try:
                rating_bonus = max(0.0, min(1.0, (float(rating) - 1.0) / 4.0))
            except Exception:
                rating_bonus = 0.0

        if outcome == "adhere":
            payoff = utility + 1.0 + rating_bonus
        elif outcome == "partial":
            payoff = utility + 0.35 + (0.5 * rating_bonus)
        else:
            payoff = max(0.0, utility - 0.3)

        payoff_sum[strategy][outcome] += float(payoff)
        count[strategy][outcome] += 1

    return {
        s: {o: payoff_sum[s][o] / float(count[s][o]) for o in OUTCOMES}
        for s in STRATEGIES
    }


def estimate_outcome_distribution(rows: list[dict]) -> dict[str, float]:
    counts = {"adhere": 2, "partial": 2, "drop": 2}
    for row in rows:
        counts[_classify_outcome(row)] += 1
    total = float(sum(counts.values()) or 1.0)
    return {k: float(v) / total for k, v in counts.items()}


def choose_mixed_strategy(matrix: dict, outcome_distribution: dict[str, float]) -> dict:
    expected = {}
    for s in STRATEGIES:
        expected[s] = sum(
            float(matrix.get(s, {}).get(o, 0.0)) * float(outcome_distribution.get(o, 0.0))
            for o in OUTCOMES
        )
    temperature = 4.0
    exp_vals = {s: math.exp(temperature * expected[s]) for s in STRATEGIES}
    z = float(sum(exp_vals.values()) or 1.0)
    probs = {s: exp_vals[s] / z for s in STRATEGIES}
    recommended = max(expected, key=expected.get)
    return {
        "expected_payoff": expected,
        "strategy_probs": probs,
        "recommended": recommended,
    }
