# Perfector AI

Paste a finished piece (or just a prompt) and Perfector AI audits and rewrites it in a **Critic -> Refiner loop** until the Critic can't find real flaws. Built for paper drafts, engineering write-ups, code docs, and anything else you want polished.

## Features
- **Polish-first workflow:** paste an existing piece, or give a prompt and let it draft first, then polish
- **Strict Critic:** quotes the exact weak text, explains the problem, gives a concrete fix, and ranks issues (Critical / Major / Minor / Formatting)
- **Regression checking:** each round verifies earlier issues were really fixed and flags new ones
- **Careful Refiner:** targeted edits that keep your voice, never invent facts or citations (unknowns are marked `[NEEDS: ...]`)
- **Quality tiers:** Free, Hybrid (free drafting + paid Critic), Premium, or Custom model IDs
- **Critic personas:** General, Aerospace/Engineering, Academic/Medical, Software Code, Writing/Persuasion
- **Smart stopping:** ends early when the score hits your target with no Critical/Major issues left; capped by a max-iteration slider
- **Transparency:** side-by-side version and feedback view, diff between rounds, progress tracker, live token and cost counter
- **Export:** Markdown or plain text

## Tiers
| Tier | Generator / Refiner | Critic | Cost |
|---|---|---|---|
| Free | Free model | Free model | $0 (rate-limited) |
| Hybrid | Free model | Paid model | Low |
| Premium | Paid model | Paid model | Highest quality |
| Custom | Any OpenRouter ID | Any | Varies |

Model IDs change often. If one errors with "model not found", find a current ID at [openrouter.ai/models](https://openrouter.ai/models) and update the constants at the top of `app.py`.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
Paste your [OpenRouter](https://openrouter.ai) API key into the sidebar (free to create). The key is never stored, and the app has no key of its own, so hosting it costs nothing and any paid usage is billed to the user's own account.

## Notes
- Free models are rate-limited and are weaker critics than paid ones. If feedback feels shallow, try Hybrid.
- Always review the final output yourself, especially facts, numbers and citations.

## Roadmap
- LaTeX and PDF export
- LangGraph orchestration
- Next.js + FastAPI frontend
