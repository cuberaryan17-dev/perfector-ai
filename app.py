"""Perfector AI - polish any piece to near-perfection with a Critic -> Refiner loop.
Run:  pip install -r requirements.txt && streamlit run app.py
Free to use: defaults to OpenRouter ':free' models; every user brings their own free key.
"""
import difflib
import json
import re
import time

import requests
import streamlit as st

API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Free model IDs change often. Browse https://openrouter.ai/models and filter by "free".
FREE_WRITER = "meta-llama/llama-3.3-70b-instruct:free"
FREE_CRITIC = "deepseek/deepseek-r1:free"
PAID_WRITER = "anthropic/claude-sonnet-4.5"
PAID_CRITIC = "openai/gpt-4o"

# (generator, critic, refiner, description)
TIERS = {
    "Free": (FREE_WRITER, FREE_CRITIC, FREE_WRITER, "All free models. $0, but rate-limited and a weaker critic."),
    "Hybrid": (FREE_WRITER, PAID_CRITIC, FREE_WRITER, "Free drafting/editing, paid Critic. Best quality per dollar."),
    "Premium": (PAID_WRITER, PAID_CRITIC, PAID_WRITER, "Paid models at every stage. Best results, costs credits."),
    "Custom": (FREE_WRITER, FREE_CRITIC, FREE_WRITER, "Pick any OpenRouter model IDs yourself."),
}

PERSONAS = {
    "General": "Accuracy, logic, completeness, clarity, structure, tone.",
    "Aerospace / Engineering": (
        "Physical plausibility, formulas and units, materials limits, thermodynamics, safety margins, "
        "unstated assumptions, missing constraints and failure modes."
    ),
    "Academic / Medical": (
        "Claims vs. evidence, citation rigor, methodology, statistical validity, overclaiming, "
        "limitations, logical flow, academic tone."
    ),
    "Software Code": "Correctness, edge cases, security, error handling, performance, readability, tests.",
    "Writing / Persuasion": "Argument strength, clarity, concision, rhythm, word choice, audience fit, hook and ending.",
}

GENERATOR_SYS = (
    "You are an expert drafter. Write a thorough, well-structured first draft that fully addresses "
    "the request. Output only the document."
)

CRITIC_SYS = """You are a ruthless, expert peer reviewer. Your job is to find what is still wrong or weak.
Focus areas: {persona}
Rules:
- Assume the piece is NOT yet perfect. Hunt for real problems; do not flatter or pad with trivia.
- Every issue must quote the exact problematic text in "location", say precisely what is wrong, and give a concrete fix.
- Rank by impact. Severity is one of: "Critical" (wrong/unsafe/invalid), "Major" (weak logic, missing content, unsupported claim), "Minor", "Formatting".
- If a list of previous issues is given, check whether each was truly fixed and flag any regression or new problem introduced.
- Only give quality_score >= 9 if you cannot find any Critical or Major issue.
Respond with ONLY valid JSON, no prose, no code fences:
{{"quality_score": <integer 1-10>, "verdict": "<one sentence>", "issues": [{{"severity": "...", "location": "<quoted text>", "problem": "...", "fix": "..."}}]}}"""

REFINER_SYS = (
    "You are a master editor. Apply the Critic's fixes to the document. Preserve the author's voice, "
    "structure and every valid detail; change only what needs changing; never add filler or invent facts "
    "or citations. If a fix needs information you don't have, mark it clearly as [NEEDS: ...]. "
    "Output ONLY the full revised document."
)


def call_llm(model, system, user, key, retries=3):
    for attempt in range(retries):
        r = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": [{"role": "system", "content": system},
                                               {"role": "user", "content": user}],
                  "usage": {"include": True}},
            timeout=300,
        )
        if r.status_code == 429 and attempt < retries - 1:
            time.sleep(8 * (attempt + 1))  # free models are rate limited
            continue
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"] or ""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        usage = data.get("usage", {})
        return text, usage.get("total_tokens", 0), usage.get("cost", 0.0) or 0.0


def parse_critic(text):
    m = re.search(r"\{.*\}", text, flags=re.S)
    try:
        d = json.loads(m.group(0)) if m else None
        if d and "issues" in d:
            d.setdefault("quality_score", 1)
            return d
    except json.JSONDecodeError:
        pass
    return {"quality_score": 1, "verdict": "Critic output unparseable.",
            "issues": [{"severity": "Major", "location": "-", "problem": "Critic returned invalid JSON.",
                        "fix": text[:400]}]}


def diff_text(a, b):
    return "\n".join(difflib.unified_diff(a.splitlines(), b.splitlines(), "before", "after", lineterm="", n=2))


st.set_page_config(page_title="Perfector AI", layout="wide")
st.title("Perfector AI")
st.caption("Paste a piece (or a prompt) and it gets audited and rewritten until the Critic can't find real flaws.")

with st.sidebar:
    st.header("Control Panel")
    key = st.text_input("OpenRouter API key (free to create)", type="password")
    persona = st.selectbox("Critic persona", list(PERSONAS))
    tier = st.selectbox("Quality tier", list(TIERS), index=0)
    st.caption(TIERS[tier][3])
    g0, c0, r0, _ = TIERS[tier]
    editable = tier == "Custom"
    # per-tier keys so the boxes reset to the tier's preset when you switch
    gen_model = st.text_input("Generator model", g0, key=f"g_{tier}", disabled=not editable)
    critic_model = st.text_input("Critic model", c0, key=f"c_{tier}", disabled=not editable)
    refiner_model = st.text_input("Refiner model", r0, key=f"r_{tier}", disabled=not editable)
    if tier != "Free":
        st.warning("Paid models use your OpenRouter credits. Add credits at openrouter.ai/credits.")
    max_iter = st.slider("Max iterations", 1, 6, 4)
    target = st.slider("Stop when quality score >=", 6, 10, 9)

mode = st.radio("What do you have?", ["I have a piece to polish", "I only have a prompt (draft it first)"], horizontal=True)
label = "Paste your piece" if mode.startswith("I have a piece") else "Describe what you want drafted"
text_in = st.text_area(label, height=260)
goal = st.text_input("Goal / audience / constraints (optional)", placeholder="e.g. journal submission, non-expert readers, under 800 words")

if st.button("Polish to perfection", type="primary", disabled=not (key and text_in.strip())):
    tokens, cost = 0, 0.0
    stages = ["Drafting", "Auditing", "Polishing", "Complete"]
    stage_box, meter = st.empty(), st.empty()

    def show(stage, it):
        stage_box.markdown(" -> ".join(f"**{s}**" if s == stage else s for s in stages) + f"  (round {it}/{max_iter})")
        meter.caption(f"Tokens used: {tokens:,} | Cost: ${cost:.4f}")

    context = f"Goal/constraints: {goal}\n\n" if goal.strip() else ""
    try:
        if mode.startswith("I have a piece"):
            doc = text_in.strip()
        else:
            show("Drafting", 0)
            doc, t, c = call_llm(gen_model, GENERATOR_SYS, context + text_in, key)
            tokens, cost = tokens + t, cost + c

        previous = []
        for i in range(1, max_iter + 1):
            show("Auditing", i)
            prev = f"\n\nPrevious issues to verify:\n{json.dumps(previous)}" if previous else ""
            raw, t, c = call_llm(critic_model, CRITIC_SYS.format(persona=PERSONAS[persona]),
                              f"{context}Document:\n{doc}{prev}", key)
            tokens, cost = tokens + t, cost + c
            review = parse_critic(raw)
            score = review.get("quality_score", 1)
            issues = review.get("issues", [])
            blocking = [x for x in issues if x.get("severity") in ("Critical", "Major")]

            left, right = st.columns(2)
            with left:
                st.subheader(f"Version {i}")
                st.markdown(doc)
            with right:
                st.subheader(f"Critic: {score}/10")
                st.caption(review.get("verdict", ""))
                for iss in issues:
                    st.markdown(f"**[{iss.get('severity')}]** _{iss.get('location')}_\n\n"
                                f"- Problem: {iss.get('problem')}\n- Fix: {iss.get('fix')}")

            if score >= target and not blocking:
                st.success(f"Converged in round {i} (score {score}, no critical/major issues).")
                break
            if i == max_iter:
                st.info("Reached max iterations. Final version below is the last refinement.")

            show("Polishing", i)
            new_doc, t, c = call_llm(refiner_model, REFINER_SYS,
                                  f"{context}Document:\n{doc}\n\nCritic feedback (JSON):\n{json.dumps(review)}", key)
            tokens, cost = tokens + t, cost + c
            with st.expander(f"Changes: version {i} -> {i + 1}"):
                st.code(diff_text(doc, new_doc), language="diff")
            previous = issues
            doc = new_doc

        show("Complete", i)
        st.session_state["final"] = doc
    except requests.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text[:300]}")
    except Exception as e:  # noqa: BLE001
        st.error(f"Something went wrong: {e}")

if "final" in st.session_state:
    st.divider()
    st.subheader("Final polished version")
    st.markdown(st.session_state["final"])
    a, b = st.columns(2)
    a.download_button("Download .md", st.session_state["final"], "perfected.md", "text/markdown")
    b.download_button("Download .txt", st.session_state["final"], "perfected.txt", "text/plain")
