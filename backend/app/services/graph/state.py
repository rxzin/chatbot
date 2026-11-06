from typing import Optional, TypedDict

from schemas.chat import MessageParam
from services.base import ToolExchange


class AgentState(TypedDict):
    # Set once by runner.prepare_context.
    user_id: str
    conversation_id: str
    user_message: str
    has_documents: bool
    document_ids: list[str]
    document_filenames: list[str]
    history: list[MessageParam]
    context_summary: Optional[str]

    # Trimmed history and summary, computed on the agent's first step.
    prepared_history: Optional[list[MessageParam]]
    prepared_summary: Optional[str]

    # Finished tool rounds this turn, and the calls waiting to run.
    exchanges: list[ToolExchange]
    pending: Optional[ToolExchange]
    final_response: Optional[str]
