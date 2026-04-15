# Personalized Health Coaching Agent

A Streamlit-based, utility-driven health coach that adapts plans from user feedback using a closed loop:

Perception -> Reasoning -> Action -> Learning.

## What It Does

- Collects daily check-in data: steps, sleep, water, exercise
- Computes an internal utility score from normalized metrics and learned weights
- Generates personalized exercise and nutrition plans
- Uses Gemini (via `google-generativeai`) for personalized motivation text with safe fallback
- Learns from feedback (`adherence`, `rating`, free-text notes)
- Updates goals, priorities, and preferences over time

## Tech Stack

- Python
- Streamlit
- SQLite
- Pandas

## Project Structure

- `app.py` - Streamlit UI and workflow
- `agent/` - reasoning, planning, learning, utility, reminders, progress
- `database/db.py` - SQLite schema and data access
- `requirements.txt` - dependencies

## Setup (Windows PowerShell)

From the project root:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
.\venv\Scripts\Activate.ps1
```

## Run

```powershell
streamlit run app.py
```

Optional: create a `.env` file in project root to enable Gemini calls:

```env
GOOGLE_API_KEY=your_api_key_here
```

Then open the local URL shown in terminal (usually `http://localhost:8501`).

## Setup (macOS/Linux)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## How the Closed Feedback Loop Works

1. **Perception**: User enters daily health signals.
2. **Reasoning**: Agent scores state with utility + gap-based priorities.
3. **Action**: Agent produces coach plans/reminders.
4. **Learning**: Feedback updates weights, thresholds, and coaching targets.
5. **Next Cycle**: Updated state changes future recommendations.

The app displays before/after evidence after feedback submission so learning changes are visible.

## Core Features

- Utility-based scoring (`agent/utility.py`)
- Adaptive priorities/thresholds (`agent/decision.py`, `agent/learning.py`)
- Personalized plan generation (`agent/planner.py`)
- LLM-enhanced motivation with fallback (`agent/llm.py`)
- Progress analytics over all 4 metrics (`agent/progress.py`)
- Input safety bounds with coaching guidance for rough values
- Simulator demo mode (5 scripted days) to show autonomous episodes in UI
- Game-theory strategy selection with payoff matrix + mixed policy (`agent/game_theory.py`)
- Agent intelligence panel with BDI snapshot and task specification views

## Quick Validation Checklist

- Submit low check-in + negative feedback -> goals reduce, failure count rises.
- Submit strong check-in + positive feedback -> goals rise gradually, streak increases.
- Enter high sleep (e.g., 13h) -> accepted with corrective sleep-cycle guidance.
- Check Progress tab -> separate trends for steps, sleep, water, exercise.
- Click "Run 5-day simulation" -> observe automated episode + learning updates.
- In Coach plan tab -> verify visible utility score, threshold, and weight chart.
- Open "Agent Intelligence" tab -> inspect BDI model, payoff matrix, and mixed strategy recommendation.

## Notes

- Data is stored locally in SQLite (`data/health.db`).
- The utility score is internal; user-facing output emphasizes plans and coaching.

