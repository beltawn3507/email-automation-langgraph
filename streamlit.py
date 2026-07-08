import json
import time
import copy
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.graph import Workflow
from src.state import build_initial_state, Email
from src.gmailtools import GmailToolsClass


load_dotenv()

st.set_page_config(
    page_title="Email Automation Agent",
    page_icon="mail",
    layout="wide",
)

RUN_CONFIG = {"recursion_limit": 100}
HISTORY_PATH = Path("logs/run_history.json")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def format_step_name(step: str) -> str:
    return step.replace("_", " ").title()


def serialize_email(email) -> dict:
    if email is None:
        return {}
    if hasattr(email, "model_dump"):
        return email.model_dump()
    if isinstance(email, dict):
        return email
    return {}


def get_workflow_app():
    """The graph is compiled once per session and reused across runs."""
    if "workflow_app" not in st.session_state:
        st.session_state.workflow_app = Workflow().app
    return st.session_state.workflow_app


def get_gmail_tools() -> GmailToolsClass:
    if "gmail_tools" not in st.session_state:
        st.session_state.gmail_tools = GmailToolsClass()
    return st.session_state.gmail_tools


# ---------------------------------------------------------------------------
# Rendering - metrics / current email / timeline
# ---------------------------------------------------------------------------

def render_metrics(state: dict) -> None:
    total_fetched = state.get("total_fetched", 0)
    total_processed = state.get("total_processed", 0)
    remaining = max(total_fetched - total_processed, 0)

    row1 = st.columns(4)
    row1[0].metric("Total Fetched", total_fetched)
    row1[1].metric("Total Processed", total_processed)
    row1[2].metric("Unread / Remaining", remaining)
    row1[3].metric("Drafts Created", state.get("drafts_created_count", 0))

    row2 = st.columns(5)
    row2[0].metric("Product Enquiries", state.get("enquiry_count", 0))
    row2[1].metric("Feedback / Complaints", state.get("feedback_count", 0))
    row2[2].metric("Unrelated (skipped)", state.get("unrelated_count", 0))
    row2[3].metric("Rejected (max retries)", state.get("rejected_count", 0))
    row2[4].metric("Flagged (spam/phishing)", state.get("flagged_count", 0))


def render_current_email(state: dict, key_suffix: str) -> None:
    email = serialize_email(state.get("current_email"))
    if not email.get("subject"):
        st.info("No active email right now.")
        return

    st.subheader("Current Email")
    st.markdown(f"**Subject:** {email.get('subject', 'No Subject')}")
    st.markdown(f"**Sender:** {email.get('sender', 'Unknown')}")
    st.markdown(f"**Category:** {state.get('email_category') or 'Pending'}")
    st.text_area(
        "Email Body",
        value=email.get("body", ""),
        height=160,
        disabled=True,
        key=f"email_body_{key_suffix}",
    )


def render_agent_outputs(state: dict, key_suffix: str) -> None:
    st.subheader("Latest Agent Output")

    if state.get("rag_queries"):
        st.markdown("**RAG Queries**")
        st.code("\n".join(state["rag_queries"]), language="text")

    if state.get("retrieved_documents"):
        st.markdown("**Retrieved Context**")
        st.text_area(
            "Retrieved Context",
            value=state["retrieved_documents"],
            height=160,
            disabled=True,
            label_visibility="collapsed",
            key=f"retrieved_context_{key_suffix}",
        )

    if state.get("generated_email"):
        st.markdown("**Draft Reply**")
        st.text_area(
            "Draft Reply",
            value=state["generated_email"],
            height=200,
            disabled=True,
            label_visibility="collapsed",
            key=f"draft_reply_{key_suffix}",
        )

    if not (state.get("rag_queries") or state.get("retrieved_documents") or state.get("generated_email")):
        st.info("Agent outputs will appear here as the workflow progresses.")


def render_timeline(events: list[dict]) -> None:
    st.subheader("Live Timeline")
    if not events:
        st.info("Click Run Workflow to watch the agent work through your inbox.")
        return

    for index, event in enumerate(reversed(events), start=1):
        label = f"{len(events) - index + 1}. {format_step_name(event['step'])}"
        with st.expander(label, expanded=index <= 2):
            st.write(event["message"])


def render_dashboard(events: list[dict], current_state: dict, error_message: str | None) -> None:
    if error_message:
        st.error(error_message)

    key_suffix = f"run_{len(events)}"
    render_metrics(current_state)

    left_col, right_col = st.columns([1.2, 1])
    with left_col:
        render_timeline(events)
    with right_col:
        render_current_email(current_state, key_suffix)
        render_agent_outputs(current_state, key_suffix)
        with st.expander("Raw State Snapshot"):
            st.code(json.dumps(current_state, indent=2, default=str), language="json")


# ---------------------------------------------------------------------------
# Analytics history persistence
# ---------------------------------------------------------------------------

def load_run_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_run_history(history: list[dict]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2))


def record_completed_run(final_state: dict) -> None:
    history = load_run_history()
    history.append(
        {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_fetched": final_state.get("total_fetched", 0),
            "total_processed": final_state.get("total_processed", 0),
            "enquiry_count": final_state.get("enquiry_count", 0),
            "feedback_count": final_state.get("feedback_count", 0),
            "unrelated_count": final_state.get("unrelated_count", 0),
            "rejected_count": final_state.get("rejected_count", 0),
            "flagged_count": final_state.get("flagged_count", 0),
            "rewrite_count": final_state.get("rewrite_count", 0),
            "drafts_created_count": final_state.get("drafts_created_count", 0),
        }
    )
    save_run_history(history)


def render_analytics_tab() -> None:
    history = load_run_history()

    st.subheader("Lifetime Totals (persisted across restarts)")
    st.caption(
        "These numbers are read from logs/run_history.json on disk, so they survive "
        "closing the app, restarting Streamlit, or a fresh 'Run Workflow' click. "
        "This is the file-based equivalent of localStorage for a server-side Streamlit app - "
        "actual browser localStorage isn't available/reliable here since this runs as a Python process, not client-side JS."
    )
    if history:
        totals = {
            key: sum(row.get(key, 0) for row in history)
            for key in (
                "total_fetched", "total_processed", "enquiry_count", "feedback_count",
                "unrelated_count", "rejected_count", "flagged_count", "drafts_created_count",
            )
        }
        lt_row1 = st.columns(4)
        lt_row1[0].metric("Total Fetched (all-time)", totals["total_fetched"])
        lt_row1[1].metric("Total Processed (all-time)", totals["total_processed"])
        lt_row1[2].metric("Drafts Created (all-time)", totals["drafts_created_count"])
        lt_row1[3].metric("Runs Logged", len(history))

        lt_row2 = st.columns(4)
        lt_row2[0].metric("Enquiries (all-time)", totals["enquiry_count"])
        lt_row2[1].metric("Feedback/Complaints (all-time)", totals["feedback_count"])
        lt_row2[2].metric("Rejected (all-time)", totals["rejected_count"])
        lt_row2[3].metric("Flagged spam/phishing (all-time)", totals["flagged_count"])
    else:
        st.info("No completed runs logged yet - lifetime totals will appear here after your first run.")

    st.divider()
    st.subheader("Current Run (this session)")
    render_metrics(st.session_state.get("last_state") or {})

    st.divider()
    st.subheader("Historical Runs")
    if not history:
        st.info("No completed runs logged yet. History is saved automatically when a run finishes.")
        return

    st.dataframe(history, width="stretch", hide_index=True)

    # Build a DataFrame with a plain integer "Run #" index — timestamp strings like
    # "2026-07-08 11:51:45" break Altair's shorthand field parser because it treats
    # the colons as type-suffix separators (e.g. "field:Q"), so we keep timestamps
    # as a regular column instead of using them as the chart index.
    history_df = pd.DataFrame(history)
    history_df.insert(0, "Run #", range(1, len(history_df) + 1))

    st.markdown("**Drafts created per run**")
    st.bar_chart(history_df.set_index("Run #")[["drafts_created_count"]])

    st.markdown("**Category mix per run**")
    category_df = history_df.set_index("Run #")[["enquiry_count", "feedback_count", "unrelated_count"]]
    category_df = category_df.rename(columns={
        "enquiry_count": "enquiry",
        "feedback_count": "feedback",
        "unrelated_count": "unrelated",
    })
    st.bar_chart(category_df)


# ---------------------------------------------------------------------------
# Review & Send
# ---------------------------------------------------------------------------

def queue_draft_for_review(current_email: dict, draft_text: str) -> None:
    st.session_state.review_queue.append(
        {
            "id": f"{current_email.get('id', 'unknown')}-{len(st.session_state.review_queue)}",
            "current_email": current_email,
            "draft_text": draft_text,
            "status": "pending",
            "error": None,
        }
    )


def send_draft(item: dict, edited_text: str) -> tuple[bool, str]:
    try:
        gmail_tools = get_gmail_tools()
        email_obj = Email(**item["current_email"])
        result = gmail_tools.send_reply(email_obj, edited_text)
        if result is None:
            return False, "Gmail API did not return a confirmation. Check credentials and console logs."
        return True, "Email sent successfully."
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def render_review_send_tab() -> None:
    st.subheader("Drafts Awaiting Review")
    st.caption(
        "Every AI-generated draft lands here. Edit if needed, then send it yourself as the admin — "
        "nothing reaches a customer without a human clicking Send."
    )

    queue = st.session_state.review_queue
    pending_items = [item for item in queue if item["status"] == "pending"]

    if not pending_items:
        st.info("No drafts waiting for review. Run the workflow to generate some.")
    else:
        for item in pending_items:
            email = item["current_email"]
            with st.container(border=True):
                st.markdown(f"**{email.get('subject', 'No Subject')}**")
                st.caption(f"To: {email.get('sender', 'Unknown')}")

                edited_text = st.text_area(
                    "Draft reply (editable)",
                    value=item["draft_text"],
                    height=200,
                    key=f"draft_text_{item['id']}",
                )

                confirmed = st.checkbox(
                    "I've reviewed this draft and confirm it's ready to send",
                    key=f"confirm_{item['id']}",
                )

                send_col, discard_col = st.columns([1, 1])
                with send_col:
                    if st.button("📤 Send Email", key=f"send_{item['id']}", disabled=not confirmed, type="primary"):
                        success, message = send_draft(item, edited_text)
                        item["status"] = "sent" if success else "error"
                        item["error"] = None if success else message
                        item["draft_text"] = edited_text
                        st.toast(message, icon="✅" if success else "⚠️")
                        st.rerun()
                with discard_col:
                    if st.button("🗑️ Discard", key=f"discard_{item['id']}"):
                        item["status"] = "discarded"
                        st.rerun()

    resolved_items = [item for item in queue if item["status"] != "pending"]
    if resolved_items:
        st.divider()
        st.subheader("Resolved")
        for item in reversed(resolved_items):
            email = item["current_email"]
            icon = {"sent": "✅", "discarded": "🗑️", "error": "⚠️"}[item["status"]]
            with st.expander(f"{icon} {email.get('subject', 'No Subject')} — {item['status'].title()}"):
                st.caption(f"To: {email.get('sender', 'Unknown')}")
                st.text(item["draft_text"])
                if item["status"] == "error" and item["error"]:
                    st.error(item["error"])


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------

for key, default in {
    "events": [],
    "run_error": None,
    "review_queue": [],
    "last_state": build_initial_state(),
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


st.title("Email Automation Agent")
st.caption("Runs the real LangGraph workflow (src/graph.py) live — no separate simulation logic.")

with st.sidebar:
    st.header("Controls")
    step_delay = st.slider("Step delay (seconds)", min_value=0.0, max_value=2.0, value=0.2, step=0.1)
    run_workflow = st.button("Run Workflow", width="stretch", type="primary")
    clear_results = st.button("Clear Timeline", width="stretch")
    st.info("The first run may open Gmail OAuth if your token is missing or expired.")

if clear_results:
    st.session_state.events = []
    st.session_state.run_error = None

run_tab, analytics_tab, review_tab = st.tabs(["🏃 Run Workflow", "📊 Analytics", "✉️ Review & Send"])

if run_workflow:
    st.session_state.events = []
    st.session_state.run_error = None

    app = get_workflow_app()
    initial_state = build_initial_state()
    running_state = dict(initial_state)  # local display accumulator, merged from each node's output
    prev_drafts_created = 0

    dashboard_placeholder = run_tab.empty()

    try:
        for output in app.stream(initial_state, RUN_CONFIG):
            for step_name, partial_state in output.items():
                if not isinstance(partial_state, dict):
                    continue
                running_state.update(partial_state)

                st.session_state.events.append(
                    {"step": step_name, "message": f"Finished running: {step_name}"}
                )

                # A Gmail draft was just created -> queue it for human review/send
                drafts_now = running_state.get("drafts_created_count", 0)
                if drafts_now > prev_drafts_created:
                    queue_draft_for_review(
                        current_email=serialize_email(running_state.get("current_email")),
                        draft_text=running_state.get("generated_email", ""),
                    )
                    prev_drafts_created = drafts_now

                st.session_state.last_state = copy.deepcopy(running_state)

                with dashboard_placeholder.container():
                    render_dashboard(st.session_state.events, running_state, st.session_state.run_error)
                if step_delay:
                    time.sleep(step_delay)

        record_completed_run(running_state)
    except Exception as exc:
        st.session_state.run_error = f"{type(exc).__name__}: {exc}"
        with dashboard_placeholder.container():
            render_dashboard(st.session_state.events, running_state, st.session_state.run_error)

with run_tab:
    if not run_workflow:
        render_dashboard(st.session_state.events, st.session_state.last_state, st.session_state.run_error)

with analytics_tab:
    render_analytics_tab()

with review_tab:
    render_review_send_tab()