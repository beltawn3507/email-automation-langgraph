import json
import time

import streamlit as st
from dotenv import load_dotenv

from src.live_runner import snapshot_state, stream_workflow_events


load_dotenv()

st.set_page_config(
    page_title="Email Automation Agent",
    page_icon="mail",
    layout="wide",
)


def format_step_name(step: str) -> str:
    return step.replace("_", " ").title()


def render_metrics(stats: dict[str, int], current_step: str) -> None:
    metric_cols = st.columns(6)
    metric_cols[0].metric("Fetched", stats.get("fetched", 0))
    metric_cols[1].metric("Processed", stats.get("processed", 0))
    metric_cols[2].metric("Drafts", stats.get("drafts_created", 0))
    metric_cols[3].metric("Skipped", stats.get("skipped", 0))
    metric_cols[4].metric("Rewrites", stats.get("rewrites", 0))
    metric_cols[5].metric("Current Step", format_step_name(current_step))


def render_current_email(state: dict, key_suffix: str) -> None:
    current_email = state.get("current_email") or {}
    if not current_email or not current_email.get("subject"):
        st.info("No active email right now.")
        return

    st.subheader("Current Email")
    st.markdown(f"**Subject:** {current_email.get('subject', 'No Subject')}")
    st.markdown(f"**Sender:** {current_email.get('sender', 'Unknown')}")
    st.markdown(f"**Category:** {state.get('email_category') or 'Pending'}")
    st.text_area(
        "Email Body",
        value=current_email.get("body", ""),
        height=180,
        disabled=True,
        key=f"email_body_{key_suffix}",
    )


def render_latest_outputs(state: dict, key_suffix: str) -> None:
    st.subheader("Latest Agent Output")

    if state.get("rag_queries"):
        st.markdown("**RAG Queries**")
        st.code("\n".join(state["rag_queries"]), language="text")

    if state.get("retrieved_documents"):
        st.markdown("**Retrieved Context**")
        st.text_area(
            "Retrieved Context",
            value=state["retrieved_documents"],
            height=180,
            disabled=True,
            label_visibility="collapsed",
            key=f"retrieved_context_{key_suffix}",
        )

    if state.get("generated_email"):
        st.markdown("**Draft Reply**")
        st.text_area(
            "Draft Reply",
            value=state["generated_email"],
            height=220,
            disabled=True,
            label_visibility="collapsed",
            key=f"draft_reply_{key_suffix}",
        )

    if state.get("writer_messages"):
        st.markdown("**Writer / Proofreader History**")
        st.code("\n\n".join(state["writer_messages"]), language="markdown")

    if not (
        state.get("rag_queries")
        or state.get("retrieved_documents")
        or state.get("generated_email")
        or state.get("writer_messages")
    ):
        st.info("Agent outputs will appear here as the workflow progresses.")


def render_timeline(events: list[dict]) -> None:
    st.subheader("Live Timeline")
    if not events:
        st.info("Click Run Workflow to watch the agent work through your inbox.")
        return

    for index, event in enumerate(reversed(events), start=1):
        label = f"{len(events) - index + 1}. {format_step_name(event['step'])}"
        expanded = index <= 2
        with st.expander(label, expanded=expanded):
            st.write(event["message"])
            data = event.get("data", {})
            if data:
                st.json(data)


def render_dashboard(events: list[dict], error_message: str | None) -> None:
    if error_message:
        st.error(error_message)

    current_event = events[-1] if events else {
        "step": "idle",
        "stats": {"fetched": 0, "processed": 0, "drafts_created": 0, "skipped": 0, "rewrites": 0},
        "state": snapshot_state({}),
    }
    key_suffix = f"{current_event['step']}_{len(events)}"

    render_metrics(current_event["stats"], current_event["step"])

    left_col, right_col = st.columns([1.2, 1])
    with left_col:
        render_timeline(events)
    with right_col:
        render_current_email(current_event["state"], key_suffix)
        render_latest_outputs(current_event["state"], key_suffix)
        with st.expander("Raw State Snapshot"):
            st.code(json.dumps(current_event["state"], indent=2), language="json")


if "events" not in st.session_state:
    st.session_state.events = []
if "run_error" not in st.session_state:
    st.session_state.run_error = None

st.title("Email Automation Agent")
st.caption("Watch the workflow fetch emails, classify them, generate replies, and create Gmail drafts in real time.")

with st.sidebar:
    st.header("Controls")
    step_delay = st.slider("Step delay (seconds)", min_value=0.0, max_value=2.0, value=0.2, step=0.1)
    run_workflow = st.button("Run Workflow", use_container_width=True, type="primary")
    clear_results = st.button("Clear Timeline", use_container_width=True)
    st.info("The first run may open Gmail OAuth if your token is missing or expired.")

if clear_results:
    st.session_state.events = []
    st.session_state.run_error = None

dashboard = st.empty()

if run_workflow:
    st.session_state.events = []
    st.session_state.run_error = None

    try:
        for event in stream_workflow_events():
            st.session_state.events.append(event)
            dashboard.empty()
            with dashboard.container():
                render_dashboard(st.session_state.events, st.session_state.run_error)
            if step_delay:
                time.sleep(step_delay)
    except Exception as exc:
        st.session_state.run_error = f"{type(exc).__name__}: {exc}"

dashboard.empty()
with dashboard.container():
    render_dashboard(st.session_state.events, st.session_state.run_error)
