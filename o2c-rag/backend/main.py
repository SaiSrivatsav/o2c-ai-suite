import os
import uuid
import logging
import shutil
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
    ensure_index_exists()
    logger.info("Ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="O2C RAG Bot",
    description="Production-grade RAG chatbot powered by LangChain, AWS Bedrock & Pinecone",
    version="1.0.0",
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


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    sources: list[dict]


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
    if not uploaded_documents:
        raise HTTPException(
            status_code=400,
            detail="No documents uploaded yet. Please upload a document first.",
        )

    session_id = req.session_id or str(uuid.uuid4())
    chain = get_rag_chain()

    result = chain.invoke(
        {"input": req.message},
        config={"configurable": {"session_id": session_id}},
    )

    # Extract source metadata from retrieved documents
    sources = []
    seen = set()
    for doc in result.get("context", []):
        meta = doc.metadata
        key = (meta.get("document_name", ""), meta.get("chunk_index", 0))
        if key not in seen:
            seen.add(key)
            sources.append({
                "document": meta.get("document_name", "Unknown"),
                "page": meta.get("page_number"),
                "chunk": meta.get("chunk_index"),
            })

    return ChatResponse(
        answer=result["answer"],
        session_id=session_id,
        sources=sources,
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
