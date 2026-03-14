import os
import uuid
import logging
import shutil
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command

from config import (
    UPLOAD_DIR,
    MAX_UPLOAD_FILE_SIZE_MB,
    MAX_TOTAL_STORAGE_MB,
    ESTIMATED_BYTES_PER_VECTOR,
    PINECONE_MAX_STORAGE_BYTES,
)
from rag.document_processor import validate_file_extension, process_upload
from rag.vector_store import (
    get_vector_store,
    get_index_stats,
    delete_document_vectors,
    ensure_index_exists,
)
from rag.chain import (
    get_rag_chain,
    get_session_history,
    clear_session_history,
    reset_chain,
)
from agents.graph import get_graph
from tools.rag_tools import set_document_registry
from db.connection import close_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-28s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── In-memory document registry ────────────────────────────────
uploaded_documents: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — ensuring Pinecone index exists...")
    try:
        ensure_index_exists()
    except Exception as e:
        logger.warning(f"Pinecone init skipped: {e}")

    # Share the document registry with RAG tools
    set_document_registry(uploaded_documents)

    # Pre-build the LangGraph agent graph
    logger.info("Building LangGraph agent graph…")
    try:
        get_graph()
        logger.info("LangGraph ready.")
    except Exception as e:
        logger.warning(f"LangGraph init deferred: {e}")

    logger.info("Ready.")
    yield
    logger.info("Shutting down.")
    await close_pool()


app = FastAPI(
    title="O2C AI Suite",
    description="Multi-agent O2C system powered by LangGraph, AWS Bedrock & Pinecone",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ──────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ResumeRequest(BaseModel):
    thread_id: str
    approved: bool
    comment: str = ""


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    sources: list[dict] = []
    agent: str = ""
    approval_request: dict | None = None


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
    chunks: int
    uploaded_at: str
    file_size_mb: float


# ── Endpoints ──────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "o2c-rag-bot"}


@app.post("/api/upload", response_model=DocumentInfo)
async def upload_document(file: UploadFile = File(...)):
    # Validate extension
    try:
        validate_file_extension(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Read file and check size
    contents = await file.read()
    file_size_mb = len(contents) / (1024 * 1024)

    if file_size_mb > MAX_UPLOAD_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File size ({file_size_mb:.1f} MB) exceeds the {MAX_UPLOAD_FILE_SIZE_MB} MB limit. "
                f"The Pinecone free tier has 2 GB total storage. "
                f"Please upload a smaller document."
            ),
        )

    # Estimate if this upload would breach Pinecone free tier
    try:
        stats = get_index_stats()
        current_vectors = stats["total_vectors"]
        estimated_new_chunks = max(1, int(len(contents) / 800))  # rough: 800 bytes per chunk
        projected_bytes = (current_vectors + estimated_new_chunks) * ESTIMATED_BYTES_PER_VECTOR
        if projected_bytes > PINECONE_MAX_STORAGE_BYTES * 0.95:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"This upload would push Pinecone storage close to the 2 GB free-tier limit "
                    f"(current vectors: {current_vectors:,}, estimated new: {estimated_new_chunks:,}). "
                    f"Please delete some documents first or upgrade your Pinecone plan."
                ),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Could not check index stats: {e}")

    # Save to temp file
    temp_path = UPLOAD_DIR / f"{uuid.uuid4()}_{file.filename}"
    try:
        with open(temp_path, "wb") as f:
            f.write(contents)

        # Process: load → chunk → embed → store
        document_id, chunks = process_upload(str(temp_path), file.filename)
        vector_store = get_vector_store()
        vector_store.add_documents(chunks)

        # Register
        doc_info = {
            "document_id": document_id,
            "filename": file.filename,
            "chunks": len(chunks),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "file_size_mb": round(file_size_mb, 2),
        }
        uploaded_documents[document_id] = doc_info

        # Reset chain so retriever picks up new vectors
        reset_chain()

        logger.info(f"Uploaded '{file.filename}': {len(chunks)} chunks, {file_size_mb:.2f} MB")
        return DocumentInfo(**doc_info)
    finally:
        if temp_path.exists():
            temp_path.unlink()


@app.get("/api/documents", response_model=list[DocumentInfo])
async def list_documents():
    return [DocumentInfo(**doc) for doc in uploaded_documents.values()]


@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: str):
    if document_id not in uploaded_documents:
        raise HTTPException(status_code=404, detail="Document not found")

    deleted = delete_document_vectors(document_id)
    doc_name = uploaded_documents.pop(document_id)["filename"]
    reset_chain()

    return {"message": f"Deleted '{doc_name}' ({deleted} vectors removed)"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    thread_id = req.session_id or str(uuid.uuid4())
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=req.message)]},
            config=config,
        )
    except Exception as e:
        logger.exception("Agent invocation error")
        raise HTTPException(status_code=500, detail=str(e))

    # Check for interrupts (human-in-the-loop)
    state = graph.get_state(config)
    if state.next:
        # Graph is paused — extract interrupt payload
        interrupt_data = {}
        if state.tasks:
            for task in state.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    interrupt_data = task.interrupts[0].value
                    break

        # Get the last AI message before the interrupt
        messages = result.get("messages", [])
        last_ai = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_ai = msg.content
                break

        return ChatResponse(
            answer=last_ai or "An action requires your approval before proceeding.",
            session_id=thread_id,
            agent=state.values.get("active_agent", ""),
            approval_request=interrupt_data,
        )

    # Normal completion — extract answer from last AI message
    messages = result.get("messages", [])
    answer = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            answer = msg.content
            break

    return ChatResponse(
        answer=answer or "I processed your request but have no additional information to share.",
        session_id=thread_id,
        agent=result.get("active_agent", ""),
    )


@app.post("/api/chat/resume", response_model=ChatResponse)
async def resume_chat(req: ResumeRequest):
    """Resume a paused agent after human-in-the-loop approval/rejection."""
    graph = get_graph()
    config = {"configurable": {"thread_id": req.thread_id}}

    # Check that this thread actually has a pending interrupt
    state = graph.get_state(config)
    if not state.next:
        raise HTTPException(status_code=400, detail="No pending approval for this thread.")

    human_response = {"approved": req.approved, "comment": req.comment}

    try:
        result = await graph.ainvoke(
            Command(resume=human_response),
            config=config,
        )
    except Exception as e:
        logger.exception("Agent resume error")
        raise HTTPException(status_code=500, detail=str(e))

    # Check for further interrupts
    state = graph.get_state(config)
    if state.next:
        interrupt_data = {}
        if state.tasks:
            for task in state.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    interrupt_data = task.interrupts[0].value
                    break
        messages = result.get("messages", [])
        last_ai = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_ai = msg.content
                break
        return ChatResponse(
            answer=last_ai or "Another action requires your approval.",
            session_id=req.thread_id,
            approval_request=interrupt_data,
        )

    # Completed
    messages = result.get("messages", [])
    answer = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            answer = msg.content
            break

    return ChatResponse(
        answer=answer or "Action completed.",
        session_id=req.thread_id,
    )


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    clear_session_history(session_id)
    return {"message": f"Session '{session_id}' cleared"}


@app.get("/api/stats")
async def stats():
    try:
        idx_stats = get_index_stats()
    except Exception as e:
        idx_stats = {"error": str(e)}

    return {
        "documents": len(uploaded_documents),
        "index": idx_stats,
        "storage_guidance": (
            "Pinecone free tier: 2 GB. Estimated safe capacity: ~200 MB of documents "
            "(~400K chunks). Large PDFs with images may use more space."
        ),
    }
