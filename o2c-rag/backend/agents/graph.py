"""Main LangGraph StateGraph — wires the supervisor and all specialist agents together."""

import logging
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agents.state import AgentState
from agents.supervisor import supervisor_node
from agents.customer_agent import create_customer_agent
from agents.order_agent import create_order_agent
from agents.fulfillment_agent import create_fulfillment_agent
from agents.finance_agent import create_finance_agent
from agents.analytics_agent import create_analytics_agent
from agents.rag_agent import create_rag_agent

logger = logging.getLogger(__name__)

# Lazy-initialised singleton
_compiled_graph = None


def build_graph():
    """Build and compile the O2C multi-agent LangGraph."""
    logger.info("Building O2C multi-agent LangGraph…")

    # Create specialist sub-graphs (each is a compiled ReAct agent)
    customer_agent = create_customer_agent()
    order_agent = create_order_agent()
    fulfillment_agent = create_fulfillment_agent()
    finance_agent = create_finance_agent()
    analytics_agent = create_analytics_agent()
    rag_agent = create_rag_agent()

    # Build the parent orchestration graph
    builder = StateGraph(AgentState)

    # ── Nodes ──────────────────────────────────────────────────
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("customer_agent", customer_agent)
    builder.add_node("order_agent", order_agent)
    builder.add_node("fulfillment_agent", fulfillment_agent)
    builder.add_node("finance_agent", finance_agent)
    builder.add_node("analytics_agent", analytics_agent)
    builder.add_node("rag_agent", rag_agent)

    # ── Edges ──────────────────────────────────────────────────
    # Entry point → supervisor
    builder.add_edge(START, "supervisor")

    # Each specialist returns control to the supervisor when done
    builder.add_edge("customer_agent", "supervisor")
    builder.add_edge("order_agent", "supervisor")
    builder.add_edge("fulfillment_agent", "supervisor")
    builder.add_edge("finance_agent", "supervisor")
    builder.add_edge("analytics_agent", "supervisor")
    builder.add_edge("rag_agent", "supervisor")

    # Supervisor uses Command(goto=...) for dynamic routing,
    # including Command(goto="__end__") when the task is complete.

    # ── Compile with checkpointer (enables interrupts & session memory) ──
    checkpointer = MemorySaver()
    graph = builder.compile(
        checkpointer=checkpointer,
    )
    graph.recursion_limit = 30  # safety limit to prevent infinite loops

    logger.info("O2C LangGraph compiled successfully (7 nodes, MemorySaver checkpointer)")
    return graph


def get_graph():
    """Get or create the singleton compiled graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def reset_graph():
    """Force rebuild of the graph (e.g. after config changes)."""
    global _compiled_graph
    _compiled_graph = None
