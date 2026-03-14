import json
import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Reference to the in-memory document registry (populated by main.py)
_uploaded_documents: dict[str, dict] = {}


def set_document_registry(registry: dict):
    """Called by main.py to share the document registry."""
    global _uploaded_documents
    _uploaded_documents = registry


@tool
async def search_documents(query: str) -> str:
    """Search uploaded O2C documents (policies, SOPs, contracts, manuals) using
    semantic similarity search. Returns the most relevant document passages."""
    try:
        from rag.vector_store import get_retriever
        retriever = get_retriever()
        docs = await retriever.ainvoke(query)

        if not docs:
            return "No relevant documents found for the query."

        results = []
        for doc in docs:
            results.append({
                "content": doc.page_content[:500],
                "source": doc.metadata.get("document_name", "unknown"),
                "page": doc.metadata.get("page_number"),
                "chunk": doc.metadata.get("chunk_index"),
            })
        return json.dumps(results, indent=2)
    except Exception as e:
        logger.warning(f"RAG search error: {e}")
        return f"Document search unavailable: {str(e)}. Make sure documents have been uploaded."


@tool
async def get_uploaded_documents() -> str:
    """List all documents currently uploaded to the RAG knowledge base,
    including filename, chunk count, and file size."""
    if not _uploaded_documents:
        return "No documents have been uploaded to the knowledge base yet."

    docs = [
        {
            "document_id": doc_id,
            "filename": info["filename"],
            "chunks": info["chunks"],
            "file_size_mb": info["file_size_mb"],
            "uploaded_at": info["uploaded_at"],
        }
        for doc_id, info in _uploaded_documents.items()
    ]
    return json.dumps(docs, indent=2)


all_rag_tools = [
    search_documents,
    get_uploaded_documents,
]
