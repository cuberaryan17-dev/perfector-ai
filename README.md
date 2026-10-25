# Perfector AI

A Generator -> Critic -> Refiner loop that drafts a document, audits it with a structured peer-review pass, and rewrites it until the Critic's flaw score drops below your threshold.

## Features
- Split-screen view of each draft and the Critic's feedback
- Diff viewer between iterations
- Progress tracker (Drafting -> Auditing -> Polishing -> Complete)
- Per-stage model routing through OpenRouter (Claude, GPT, Gemini)
- Critic personas: General, Aerospace/Engineering, Academic/Medical, Software Code
- Convergence detection (auto-stop) and a max-iteration cap
- Live token and cost tracking
- Export to Markdown or plain text

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
Paste your [OpenRouter](https://openrouter.ai) API key into the sidebar. The key is never stored.

## Roadmap
- LaTeX and PDF export
- LangGraph orchestration
- Next.js + FastAPI frontend
