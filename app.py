"""Perfector AI - Generator -> Critic -> Refiner loop with convergence detection.
Run:  pip install streamlit requests
      streamlit run app.py
"""
import difflib
import json
import re

import requests
import streamlit as st

API_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    "anthropic/claude-sonnet-4.5",
    "openai/gpt-4o",
    "openai/o3-mini",
    "google/gemini-2.5-pro",
]

PERSONAS = {
    "General": "Check for factual errors, weak logic, unsupported claims, clarity and structure.",
    "Aerospace / Engineering": (
        "Check physical constraints, formulas and units, materials limits, thermodynamics, "
        "safety margins and unstated assumptions (e.g. for rotating detonation engine designs)."
    ),
    "Academic / Medical": (
        "Check citation rigor, methodology, statistical validity, overclaiming, clarity and "
        "academic tone (e.g. for cancer research papers)."
    ),
    "Software Code": "Check edge cases, security vulnerabilities, error handling, efficiency and readability.",
}

GENERATOR_SYS = (
    "You are the Generator: a creative, thorough drafter. Produce a well-structured, "
    "comprehensive technical draft that expands on the user's prompt."
)

CRITIC_SYS = (
    "You are the Critic: a ruthless peer reviewer. {persona}\n"
    "Respond with ONLY valid JSON, no prose, no code fences, in this schema:\n"
    '{{"flaw_score": <integer 0-10, 0 = flawless>, "issues": [{{"severity": '
    '"Critical Error" | "Minor Suggestion" | "Formatting", "location": "<quote or section>", '
    '"problem": "<what is wrong>", "fix": "<how to fix>"}}]}}'
)

REFINER_SYS = (
    "You are the Refiner: a master editor. Rewrite the draft to fix every issue the Critic "
    "raised while preserving all valid original details. Output ONLY the revised document."
)


def call_llm(model, system, user, key):
    r = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "usage": {"include": True},
        },
        timeout=300,
    )
    r.raise_for_status()
    data = r.json()
    usage = data.get("usage", {})
    return (
        data["choices"][0]["message"]["content"],
        usage.get("total_tokens", 0),
        usage.get("cost", 0.0) or 0.0,
    )


def parse_critic(text):
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"flaw_score": 10, "issues": [{"severity": "Critical Error", "location": "-",
                                              "problem": "Critic returned unparseable output.",
                                              "fix": text[:500]}]}


def diff_text(a, b):
    return "\n".join(difflib.unified_diff(a.splitlines(), b.splitlines(), "previous", "revised", lineterm="", n=2))


st.set_page_config(page_title="Perfector AI", layout="wide")
st.title("Perfector AI")
st.caption("Draft -> Audit -> Polish, looped until the Critic runs out of complaints.")

with st.sidebar:
    st.header("Control Panel")
    key = st.text_input("OpenRouter API key", type="password")
    persona = st.selectbox("Critic persona", list(PERSONAS))
    gen_model = st.selectbox("Generator model", MODELS, 0)
    critic_model = st.selectbox("Critic model", MODELS, 1)
    refiner_model = st.selectbox("Refiner model", MODELS, 3)
    max_iter = st.slider("Max iterations", 1, 5, 3)
    threshold = st.slider("Stop when flaw score <=", 0, 5, 1)

prompt = st.text_area("Your prompt", height=140, placeholder="Describe what you want drafted...")

if st.button("Perfect it", type="primary", disabled=not (key and prompt.strip())):
    tokens, cost = 0, 0.0
    history = []  # list of dicts: draft, review
    stages = ["Drafting", "Auditing", "Polishing", "Complete"]
    stage_box = st.empty()
    meter = st.empty()

    def show(stage, it):
        stage_box.markdown(" -> ".join(f"**{s}**" if s == stage else s for s in stages) + f"  (iteration {it}/{max_iter})")
        meter.caption(f"Tokens: {tokens:,} | Est. cost: ${cost:.4f}")

    try:
        show("Drafting", 0)
        draft, t, c = call_llm(gen_model, GENERATOR_SYS, prompt, key)
        tokens, cost = tokens + t, cost + c

        for i in range(1, max_iter + 1):
            show("Auditing", i)
            raw, t, c = call_llm(critic_model, CRITIC_SYS.format(persona=PERSONAS[persona]),
                                 f"Original request:\n{prompt}\n\nDraft:\n{draft}", key)
            tokens, cost = tokens + t, cost + c
            review = parse_critic(raw)
            score = review.get("flaw_score", 10)
            history.append({"draft": draft, "review": review})

            left, right = st.columns(2)
            with left:
                st.subheader(f"Draft v{i}")
                st.markdown(draft)
            with right:
                st.subheader(f"Critic feedback (flaw score {score}/10)")
                for iss in review.get("issues", []):
                    st.markdown(f"**[{iss.get('severity')}]** {iss.get('location')}\n\n"
                                f"- Problem: {iss.get('problem')}\n- Fix: {iss.get('fix')}")

            critical = [x for x in review.get("issues", []) if x.get("severity") == "Critical Error"]
            if score <= threshold and not critical:
                st.success(f"Converged at iteration {i} (score {score}). Stopping early.")
                break

            show("Polishing", i)
            new_draft, t, c = call_llm(refiner_model, REFINER_SYS,
                                       f"Draft:\n{draft}\n\nCritic feedback (JSON):\n{json.dumps(review)}", key)
            tokens, cost = tokens + t, cost + c
            with st.expander(f"Diff: v{i} -> v{i + 1}"):
                st.code(diff_text(draft, new_draft), language="diff")
            draft = new_draft

        show("Complete", len(history))
        st.session_state["final"] = draft
    except requests.HTTPError as e:
        st.error(f"API error: {e.response.status_code} {e.response.text[:300]}")
    except Exception as e:  # noqa: BLE001
        st.error(f"Something went wrong: {e}")

if "final" in st.session_state:
    st.divider()
    st.subheader("Final output")
    st.markdown(st.session_state["final"])
    a, b = st.columns(2)
    a.download_button("Download .md", st.session_state["final"], "perfected.md", "text/markdown")
    b.download_button("Download .txt", st.session_state["final"], "perfected.txt", "text/plain")
