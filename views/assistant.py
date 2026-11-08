import streamlit as st

from anomaly_agent import insights
from anomaly_agent.ai_explainer import ai_available
from anomaly_agent.db import ai_usage
from anomaly_agent.db.database import DatabaseUnavailable, session_scope
from anomaly_agent.ui.context import get_context
from anomaly_agent.ui.theme import page_header

ctx = get_context()
user = ctx["user"]
page_header("AI assistant", f"{ctx['source']} &nbsp;·&nbsp; latest period: <b>{ctx['period']}</b>")

facts = insights.build_facts(
    ctx["df"], ctx["date_column"], ctx["metrics"], ctx["summary"], ctx["anomalies"], ctx["source_name"], ctx["period"]
)
ai_on = ctx["use_ai"] and ai_available()
file_key = (ctx["source_name"], ctx["period"], tuple(ctx["metrics"]))
if st.session_state.get("assistant_file") != file_key:  # a different file or filter: start fresh
    st.session_state["assistant_file"] = file_key
    st.session_state["assistant_chat"] = []
    st.session_state.pop("assistant_summary", None)

if ai_on:
    st.info("AI is on. Only the summary numbers below are sent to Google (never your whole file).")
else:
    st.info("AI is off (turn it on in the sidebar, it needs a GEMINI_API_KEY). Built-in answers are used.")

with st.expander("Exactly what is sent to Google"):
    st.caption(
        "Column names are cleaned, and these computed numbers are all the AI gets. "
        "Its reply is shown as text only, it is never run as code."
    )
    st.code(insights.facts_json(facts), language="json")


def blocked_reason(kind):
    """Records the Gemini call. Returns None if the user may ask now, else a sentence saying why not."""
    try:
        with session_scope() as session:
            if ai_usage.record_call(session, user["id"], kind):
                return None
            wait = ai_usage.minutes_until_free(session, user["id"], kind)
    except DatabaseUnavailable as error:
        return str(error)
    what = "questions" if kind == "question" else "summaries"
    return f"Limit reached: {ai_usage.LIMITS[kind]} AI {what} per hour. Try again in about {wait} minute(s)."


def remaining(kind):
    try:
        with session_scope() as session:
            return ai_usage.remaining(session, user["id"], kind)
    except DatabaseUnavailable:
        return None


# ---------- Summary ----------
st.subheader("Key insights")
if st.button("Write an AI summary" if ai_on else "Refresh built-in summary", key="make_summary"):
    if not ai_on:
        st.session_state["assistant_summary"] = (
            "\n".join(f"- {line}" for line in insights.built_in_insights(facts)), "built-in", None,
        )
    elif (problem := blocked_reason("insight")) is not None:
        st.warning(problem)
    else:
        with st.spinner("Asking Gemini..."):
            st.session_state["assistant_summary"] = insights.insights(facts)
text, source, reason = st.session_state.get(
    "assistant_summary", ("\n".join(f"- {line}" for line in insights.built_in_insights(facts)), "built-in", None)
)
st.markdown(text)
if source == "AI":
    st.caption("Written by Gemini from the numbers above. AI can be wrong: check important points in your data.")
elif reason:
    st.caption(f"Gemini could not answer ({reason}), so this is the built-in summary.")
else:
    st.caption("Built-in summary made from the computed numbers (no AI).")

# ---------- Questions ----------
st.subheader("Ask a question about this file")
left = remaining("question") if ai_on else None
if ai_on and left is not None:
    st.caption(f"{left} of {ai_usage.LIMITS['question']} AI questions left this hour.")
st.caption("For example: Which metric changed the most? Why might Sales be high? Is Refunds trending up?")

for message in st.session_state["assistant_chat"]:
    with st.chat_message(message["role"]):
        st.markdown(message["text"])
        if message["role"] == "assistant":
            st.caption(message["note"])

question = st.chat_input("Ask about your data", key="assistant_question", max_chars=insights.MAX_QUESTION)
if question:
    chat = st.session_state["assistant_chat"]
    chat.append({"role": "user", "text": insights.clean_question(question)})
    problem = blocked_reason("question") if ai_on else None
    if ai_on and problem is None:
        with st.spinner("Asking Gemini..."):
            reply, source, reason = insights.answer(question, facts)
    else:
        reply, source, reason = insights.built_in_answer(question, facts), "built-in", None
    note = (
        "Written by Gemini from the numbers above. AI can be wrong." if source == "AI"
        else f"Built-in answer. {problem}" if problem
        else f"Built-in answer (Gemini could not answer: {reason})." if reason
        else "Built-in answer from the computed numbers (no AI)."
    )
    chat.append({"role": "assistant", "text": reply, "note": note})
    del chat[:-20]  # keep the last 20 messages
    st.rerun()

if st.session_state["assistant_chat"] and st.button("Clear the conversation", key="clear_chat"):
    st.session_state["assistant_chat"] = []
    st.rerun()
