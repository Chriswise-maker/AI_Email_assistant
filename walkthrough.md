# Project Walkthrough: Email Triage Assistant

## Project Status: COMPLETE ✅
All core features (IMAP fetching, LLM categorization, Rules Engine, UI Dashboard) are implemented and verified.

## Overview
A local, privacy-focused email assistant that uses LLMs (Groq/Llama 3 or DeepSeek) to categorize, summarize, and prioritize your emails.

## Phases Completed

### Phase 1: Setup
- Installed dependencies (`imap-tools`, `groq`, `streamlit`).
- Configured `.env` for secrets.

### Phase 2: Configuration
- Created `config.yaml` for rules, categories, and system prompts.
- Built robust config loading/saving utilities.

### Phase 3: Modular Backend & UI
- Integrated `GroqProvider` and `DeepSeekProvider`.
- Connected backend logic to Streamlit UI.

### Phase 4: Optimization & Polish
- **Persistent Connections**: Optimized IMAP usage for batch processing.
- **Real Actions**: The assistant now **marks emails as read** or **flags** them based on your rules.
- **Daily Briefing**: Automatically generates a localized markdown summary in `daily_briefing.md`.
- **Error Tracking**: Detects and reports skipped emails (e.g., due to Rate Limits).

## Known Limitations
- **Groq Rate Limits**: The free tier of Groq has a daily token limit (~100k tokens). High volumes of email (40+) may hit this limit, causing some emails to be skipped.
    - *Solution*: Wait 24h for reset, or switch to a paid tier/different provider (DeepSeek).

## How to Run
```bash
source venv/bin/activate
streamlit run app.py
```
1. Open [http://localhost:8501](http://localhost:8501) (or port shown).
2. Go to **Dashboard** -> **Run Triage Now**.
3. View **Daily Briefing** in the right column.

## Project Structure
- `app.py`: Main Streamlit dashboard.
- `backend.py`: Core logic for fetching, analyzing, and acting on emails.
- `llm_providers.py`: Abstraction for AI models (Groq/DeepSeek).
- `utils.py`: Helper functions for config and environment.
- `config.yaml`: Rules and settings.
