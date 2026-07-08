from pydantic import BaseModel, Field
from typing import List, Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class Email(BaseModel):
    id: str = Field(..., description="Unique identifier of the email")
    threadId: str = Field(..., description="Thread identifier of the email")
    messageId: str = Field(..., description="Message identifier of the email")
    references: str = Field(..., description="References of the email")
    sender: str = Field(..., description="Email address of the sender")
    subject: str = Field(..., description="Subject line of the email")
    body: str = Field(..., description="Body content of the email")
    
class GraphState(TypedDict):
    emails: List[Email]
    current_email: Email
    email_category: str
    generated_email: str
    rag_queries: List[str]
    retrieved_documents: str
    writer_messages: Annotated[list, add_messages]
    sendable: bool
    trials: int
    is_suspicious: bool
    threat_reason: str

    # --- Analytics counters (reset once per run, incremented by nodes) ---
    total_fetched: int          # emails pulled from Gmail this run
    total_processed: int        # emails that reached a terminal outcome (sent/rejected/skipped)
    enquiry_count: int          # emails categorized as product_enquiry
    feedback_count: int         # emails categorized as feedback_or_complaint
    unrelated_count: int        # emails categorized as unrelated / skipped
    rejected_count: int         # emails that hit the max rewrite limit and were dropped
    flagged_count: int          # emails flagged as spam/phishing/prompt-injection attempts
    rewrite_count: int          # total number of rewrite cycles across all emails
    drafts_created_count: int   # Gmail drafts successfully created


def build_initial_state() -> GraphState:
    """Fresh GraphState for the start of a run (used by main.py and the Streamlit dashboard)."""
    return {
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
        "is_suspicious": False,
        "threat_reason": "",
        "total_fetched": 0,
        "total_processed": 0,
        "enquiry_count": 0,
        "feedback_count": 0,
        "unrelated_count": 0,
        "rejected_count": 0,
        "flagged_count": 0,
        "rewrite_count": 0,
        "drafts_created_count": 0,
    }