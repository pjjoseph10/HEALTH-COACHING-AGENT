from __future__ import annotations

import os

from dotenv import load_dotenv

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - optional runtime dependency behavior
    genai = None


MODEL_CANDIDATES = (
    os.getenv("GEMINI_MODEL", "").strip(),
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
)


def build_llm_motivation(
    *,
    user_name: str,
    goal: str,
    priorities: list[str],
    trend: str,
    fallback_message: str,
    utility: float,
) -> str:
    """
    Generate a short personalized motivation message using Gemini.
    Falls back safely to a deterministic message when configuration is missing.
    """
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or genai is None:
        return fallback_message

    try:
        genai.configure(api_key=api_key)
        focus = ", ".join(priorities) if priorities else "maintenance and consistency"
        prompt = (
            "You are a concise health coach.\n"
            f"User: {user_name or 'User'}\n"
            f"Primary goal: {goal or 'general_fitness'}\n"
            f"Current trend: {trend}\n"
            f"Current utility score: {utility:.2f}\n"
            f"Current focus: {focus}\n\n"
            "Write exactly 2 short motivating sentences.\n"
            "Tone: practical, encouraging, not preachy.\n"
            "No medical claims, no diagnosis, no hashtags."
        )
        for model_name in MODEL_CANDIDATES:
            if not model_name:
                continue
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                text = (getattr(response, "text", "") or "").strip()
                if text:
                    return text
            except Exception:
                continue
        return fallback_message
    except Exception:
        return fallback_message


def get_llm_status() -> tuple[bool, str]:
    """
    Returns (enabled, human-readable-status).
    """
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if genai is None:
        return False, "LLM package unavailable (fallback mode)"
    if not api_key:
        return False, "GOOGLE_API_KEY missing (fallback mode)"
    return True, "Gemini key detected (live call attempted, fallback on API/model errors)"
