"""Supervisor agent — routes user queries to the appropriate specialist agent."""

from typing import Literal
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_aws import ChatBedrockConverse
from langgraph.graph import END
from langgraph.types import Command
from pydantic import BaseModel, Field

from config import BEDROCK_MODEL_ID, AWS_REGION
from agents.state import AgentState

MEMBERS = [
    "customer_agent",
    "order_agent",
    "fulfillment_agent",
    "finance_agent",
    "analytics_agent",
    "rag_agent",
]

SYSTEM_PROMPT = """You are the O2C AI Suite Supervisor — an intelligent router for an Order-to-Cash enterprise system.

Your job is to analyse the user's request and route it to the most appropriate specialist agent.
You NEVER answer business questions yourself. You ONLY decide which agent should handle the request.

Available agents:
- **customer_agent**: Customer master data — lookup, list, search, filter, create, update, deactivate customers, 360-degree customer views. USE THIS for any question about customers: counts, lists, filtering by country/region/group, customer details.
- **order_agent**: Sales orders — create, search, update status, add items, cancel orders, document flow/history
- **fulfillment_agent**: Deliveries — create deliveries, update status, tracking info, shipment management
- **finance_agent**: Invoices, payments, credit memos — create invoices, record payments, reverse payments, credit memos, overdue tracking, invoice aging
- **analytics_agent**: Cross-domain reports & analytics — order metrics, revenue analysis, payment collection, delivery performance, customer aging reports, pipeline summaries. Use ONLY for aggregate business metrics across multiple domains.
- **rag_agent**: Document search — search uploaded O2C policy documents, SOPs, contracts for relevant information

Routing guidelines:
1. Questions about customer data (list, count, filter, search, details, onboard, update) → customer_agent
2. "How many customers in [region/country]?" → customer_agent (NOT analytics)
3. Sales order operations (create, search, cancel, status) → order_agent
4. Delivery and shipping questions → fulfillment_agent
5. Invoice, payment, credit memo, billing, overdue → finance_agent
6. Cross-domain aggregate reports (revenue trends, payment collection rates, delivery KPIs) → analytics_agent
7. Policy/procedure/document questions → rag_agent
8. If done (user said thanks/goodbye) → FINISH

Respond with ONLY the agent name to route to, or FINISH if done."""


class RouteDecision(BaseModel):
    """Structured routing decision from the supervisor."""
    next: str = Field(description="The next agent to route to, or FINISH if the task is complete")
    reasoning: str = Field(description="Brief reason for this routing decision")


def get_supervisor_llm():
    return ChatBedrockConverse(
        model=BEDROCK_MODEL_ID,
        region_name=AWS_REGION,
        temperature=0,
        max_tokens=256,
    )


async def supervisor_node(state: AgentState) -> Command[Literal[
    "customer_agent", "order_agent", "fulfillment_agent",
    "finance_agent", "analytics_agent", "rag_agent", "__end__"
]]:
    """Supervisor node that routes to the appropriate specialist agent."""
    messages = state["messages"]

    # ── Early-exit: if a specialist already responded, we're done. ──
    if state.get("active_agent"):
        # Find the last non-empty AI message (the specialist's answer)
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
                return Command(goto="__end__", update={"active_agent": ""})
            # If we reach the original user message without finding an
            # AI answer, break and let the supervisor re-route.
            if isinstance(msg, HumanMessage):
                break

    # ── Route the query ─────────────────────────────────────────
    user_messages = [m for m in messages if isinstance(m, HumanMessage)]
    if not user_messages:
        return Command(goto="__end__", update={"active_agent": ""})

    llm = get_supervisor_llm()
    structured_llm = llm.with_structured_output(RouteDecision)

    llm_messages = [SystemMessage(content=SYSTEM_PROMPT)] + user_messages[-1:]
    decision = await structured_llm.ainvoke(llm_messages)

    goto = decision.next
    if goto == "FINISH" or goto not in MEMBERS:
        goto = "__end__"

    return Command(
        goto=goto,
        update={"active_agent": goto if goto != "__end__" else ""},
    )
