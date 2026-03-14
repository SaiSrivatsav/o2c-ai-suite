"""Shared state definition for the O2C multi-agent LangGraph system."""

from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Extended state that carries messages plus orchestration metadata."""
    # Which specialist agent is currently active
    active_agent: str = ""
    # The original user query (preserved across routing)
    original_query: str = ""
