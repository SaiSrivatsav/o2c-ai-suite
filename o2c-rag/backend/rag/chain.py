import logging
from langchain_aws import ChatBedrockConverse
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_classic.chains.history_aware_retriever import create_history_aware_retriever
from langchain_classic.chains.retrieval import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain

from config import (
    AWS_REGION,
    BEDROCK_MODEL_ID,
    RETRIEVER_TOP_K,
)
from rag.vector_store import get_vector_store

logger = logging.getLogger(__name__)

# ── In-memory session store ─────────────────────────────────────
_session_store: dict[str, ChatMessageHistory] = {}


def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in _session_store:
        _session_store[session_id] = ChatMessageHistory()
    return _session_store[session_id]


def clear_session_history(session_id: str) -> None:
    _session_store.pop(session_id, None)


def list_sessions() -> list[str]:
    return list(_session_store.keys())


# ── LLM ─────────────────────────────────────────────────────────
def get_llm() -> ChatBedrockConverse:
    return ChatBedrockConverse(
        model=BEDROCK_MODEL_ID,
        region_name=AWS_REGION,
        temperature=0,
        max_tokens=4096,
    )


# ── Prompts ─────────────────────────────────────────────────────
CONTEXTUALIZE_SYSTEM_PROMPT = (
    "Given the chat history and the latest user question, "
    "reformulate the question to be a standalone question that can be "
    "understood without the chat history. Do NOT answer the question — "
    "only reformulate it if needed, otherwise return it as-is."
)

QA_SYSTEM_PROMPT = """You are a precise document Q&A assistant. Your ONLY purpose is to answer questions based strictly on the provided document context.

RULES — follow these without exception:
1. Answer ONLY using information found in the context below. Never use your training knowledge.
2. If the answer is NOT in the context, respond exactly: "I couldn't find this information in the uploaded document(s). Please try rephrasing your question or upload a document that contains this information."
3. When possible, cite the source document name and page/section number.
4. Be concise, accurate, and well-structured in your responses.
5. If the context contains partial information, state what you found and note what is missing.
6. For numerical data, quote the exact figures from the document.
7. Never fabricate, infer beyond what's stated, or speculate.

Context from uploaded documents:
{context}"""

contextualize_prompt = ChatPromptTemplate.from_messages([
    ("system", CONTEXTUALIZE_SYSTEM_PROMPT),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])

qa_prompt = ChatPromptTemplate.from_messages([
    ("system", QA_SYSTEM_PROMPT),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])


# ── Build the RAG chain ────────────────────────────────────────
def build_rag_chain() -> RunnableWithMessageHistory:
    llm = get_llm()
    vector_store = get_vector_store()
    retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": RETRIEVER_TOP_K},
    )

    # Step 1: make the retriever history-aware (rewrites follow-ups)
    history_aware_retriever = create_history_aware_retriever(
        llm, retriever, contextualize_prompt
    )

    # Step 2: combine retrieved docs + question → answer
    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)

    # Step 3: full retrieval chain
    rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)

    # Step 4: wrap with session memory
    conversational_rag = RunnableWithMessageHistory(
        rag_chain,
        get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history",
        output_messages_key="answer",
    )

    logger.info("RAG chain built successfully.")
    return conversational_rag


# ── Singleton ───────────────────────────────────────────────────
_chain: RunnableWithMessageHistory | None = None


def get_rag_chain() -> RunnableWithMessageHistory:
    global _chain
    if _chain is None:
        _chain = build_rag_chain()
    return _chain


def reset_chain() -> None:
    """Force rebuild of the chain (e.g., after index changes)."""
    global _chain
    _chain = None
