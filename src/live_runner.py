from __future__ import annotations

from copy import deepcopy
from typing import Any

from .nodes import Nodes
from .state import Email, GraphState


INITIAL_STATE: GraphState = {
    "emails": [],
    "current_email": {
        "id": "",
        "threadId": "",
        "messageId": "",
        "references": "",
        "sender": "",
        "subject": "",
        "body": "",
    },
    "email_category": "",
    "generated_email": "",
    "rag_queries": [],
    "retrieved_documents": "",
    "writer_messages": [],
    "sendable": False,
    "trials": 0,
}


def build_initial_state() -> GraphState:
    return deepcopy(INITIAL_STATE)


def _serialize_email(email: Email | dict[str, Any] | None) -> dict[str, Any] | None:
    if email is None:
        return None
    if isinstance(email, Email):
        return email.model_dump()
    if isinstance(email, dict):
        return dict(email)
    return None


def snapshot_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "emails": [_serialize_email(email) for email in state.get("emails", [])],
        "current_email": _serialize_email(state.get("current_email")),
        "email_category": state.get("email_category", ""),
        "generated_email": state.get("generated_email", ""),
        "rag_queries": list(state.get("rag_queries", [])),
        "retrieved_documents": state.get("retrieved_documents", ""),
        "writer_messages": list(state.get("writer_messages", [])),
        "sendable": state.get("sendable", False),
        "trials": state.get("trials", 0),
    }


def _make_event(
    step: str,
    message: str,
    state: dict[str, Any],
    stats: dict[str, int],
    **data: Any,
) -> dict[str, Any]:
    return {
        "step": step,
        "message": message,
        "state": snapshot_state(state),
        "stats": dict(stats),
        "data": data,
    }


def stream_workflow_events():
    state = build_initial_state()
    stats = {
        "fetched": 0,
        "processed": 0,
        "drafts_created": 0,
        "skipped": 0,
        "rewrites": 0,
    }
    yield _make_event("startup", "Workflow initialized and ready to fetch emails.", state, stats)
    nodes = Nodes()

    load_result = nodes.load_new_emails(state)
    state.update(load_result)
    stats["fetched"] = len(state["emails"])
    yield _make_event(
        "load_inbox_emails",
        f"Fetched {len(state['emails'])} unanswered email(s) from Gmail.",
        state,
        stats,
        emails=[email.model_dump() for email in state["emails"]],
    )

    while True:
        inbox_status = nodes.check_new_emails(state)
        yield _make_event(
            "check_inbox",
            "No new emails left to process."
            if inbox_status == "empty"
            else f"{len(state['emails'])} email(s) waiting for review.",
            state,
            stats,
            route=inbox_status,
        )
        if inbox_status == "empty":
            break

        categorize_result = nodes.categorize_email(state)
        state.update(categorize_result)
        yield _make_event(
            "categorize_email",
            f"Categorized '{state['current_email'].subject}' as {state['email_category']}.",
            state,
            stats,
            current_email=_serialize_email(state["current_email"]),
        )

        category_route = nodes.route_email_based_on_category(state)
        yield _make_event(
            "route_email",
            f"Routing category {state['email_category']} to '{category_route}'.",
            state,
            stats,
            route=category_route,
        )

        if category_route == "unrelated":
            skipped_email = _serialize_email(state["current_email"])
            state = nodes.skip_unrelated_email(state)
            stats["processed"] += 1
            stats["skipped"] += 1
            yield _make_event(
                "skip_unrelated_email",
                "Skipped unrelated email.",
                state,
                stats,
                skipped_email=skipped_email,
            )
            continue

        if category_route == "product related":
            query_result = nodes.construct_rag_queries(state)
            state.update(query_result)
            yield _make_event(
                "construct_rag_queries",
                f"Generated {len(state['rag_queries'])} RAG querie(s).",
                state,
                stats,
                rag_queries=list(state["rag_queries"]),
            )

            rag_result = nodes.retrieve_from_rag(state)
            state.update(rag_result)
            yield _make_event(
                "retrieve_from_rag",
                "Retrieved internal context for the reply.",
                state,
                stats,
                retrieved_documents=state["retrieved_documents"],
            )

        while True:
            draft_result = nodes.write_draft_email(state)
            state.update(draft_result)
            yield _make_event(
                "email_writer",
                f"Draft #{state['trials']} generated.",
                state,
                stats,
                generated_email=state["generated_email"],
            )

            proofreader_result = nodes.verify_generated_email(state)
            state.update(proofreader_result)
            latest_feedback = state["writer_messages"][-1] if state["writer_messages"] else ""
            yield _make_event(
                "email_proofreader",
                "Proofreader reviewed the draft.",
                state,
                stats,
                sendable=state["sendable"],
                feedback=latest_feedback,
            )

            decision_snapshot = snapshot_state(state)
            decision = nodes.must_rewrite(state)
            yield _make_event(
                "rewrite_decision",
                f"Proofreader decision: {decision}.",
                state,
                stats,
                route=decision,
                decision_state=decision_snapshot,
            )

            if decision == "rewrite":
                stats["rewrites"] += 1
                continue

            if decision == "send":
                stats["processed"] += 1
                stats["drafts_created"] += 1
                draft_email = decision_snapshot["generated_email"]
                current_email = decision_snapshot["current_email"]
                send_result = nodes.create_draft_response(state)
                state.update(send_result)
                yield _make_event(
                    "send_email",
                    "Created a Gmail draft reply.",
                    state,
                    stats,
                    generated_email=draft_email,
                    current_email=current_email,
                )
                break

            if decision == "stop":
                stats["processed"] += 1
                yield _make_event(
                    "stop_after_retries",
                    "Stopped after reaching the rewrite limit for this email.",
                    state,
                    stats,
                )
                break

    yield _make_event("complete", "Workflow finished.", state, stats)
