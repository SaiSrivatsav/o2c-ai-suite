import logging
import ssl
from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore
from langchain_aws import BedrockEmbeddings

from config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    BEDROCK_EMBEDDING_MODEL_ID,
    PINECONE_API_KEY,
    PINECONE_INDEX,
    EMBEDDING_DIM,
)

logger = logging.getLogger(__name__)

# Fix: Pinecone API has HTTP/2 ALPN negotiation issues on some systems.
# Force HTTP/1.1 by patching ssl.create_default_context to set ALPN protocols.
_original_create_context = ssl.create_default_context


def _patched_create_context(*args, **kwargs):
    ctx = _original_create_context(*args, **kwargs)
    ctx.set_alpn_protocols(["http/1.1"])
    return ctx


ssl.create_default_context = _patched_create_context

logger = logging.getLogger(__name__)

_pc_client: Pinecone | None = None
_vector_store: PineconeVectorStore | None = None
_embeddings: BedrockEmbeddings | None = None


def get_embeddings() -> BedrockEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = BedrockEmbeddings(
            model_id=BEDROCK_EMBEDDING_MODEL_ID,
            region_name=AWS_REGION,
            credentials_profile_name=None,
            model_kwargs={"dimensions": EMBEDDING_DIM},
        )
        logger.info(f"Initialized Bedrock embeddings: {BEDROCK_EMBEDDING_MODEL_ID}")
    return _embeddings


def _get_pinecone_client() -> Pinecone:
    global _pc_client
    if _pc_client is None:
        _pc_client = Pinecone(api_key=PINECONE_API_KEY)
    return _pc_client


def ensure_index_exists() -> None:
    pc = _get_pinecone_client()
    existing = [idx.name for idx in pc.list_indexes()]
    if PINECONE_INDEX not in existing:
        logger.info(f"Creating Pinecone index '{PINECONE_INDEX}' (dim={EMBEDDING_DIM})...")
        pc.create_index(
            name=PINECONE_INDEX,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region=AWS_REGION),
        )
        logger.info(f"Index '{PINECONE_INDEX}' created.")
    else:
        logger.info(f"Pinecone index '{PINECONE_INDEX}' already exists.")


def get_vector_store() -> PineconeVectorStore:
    global _vector_store
    if _vector_store is None:
        ensure_index_exists()
        _vector_store = PineconeVectorStore(
            index_name=PINECONE_INDEX,
            embedding=get_embeddings(),
            pinecone_api_key=PINECONE_API_KEY,
        )
        logger.info("PineconeVectorStore initialized.")
    return _vector_store


def get_index_stats() -> dict:
    pc = _get_pinecone_client()
    index = pc.Index(PINECONE_INDEX)
    stats = index.describe_index_stats()
    return {
        "total_vectors": stats.total_vector_count,
        "dimension": stats.dimension,
        "index_fullness": stats.index_fullness,
    }


def delete_document_vectors(document_id: str) -> int:
    pc = _get_pinecone_client()
    index = pc.Index(PINECONE_INDEX)

    # Pinecone serverless doesn't support delete by metadata filter directly.
    # We need to query for matching vectors first, then delete by IDs.
    embeddings = get_embeddings()
    dummy_vector = [0.0] * EMBEDDING_DIM

    deleted = 0
    while True:
        results = index.query(
            vector=dummy_vector,
            top_k=1000,
            filter={"document_id": {"$eq": document_id}},
            include_metadata=False,
        )
        if not results.matches:
            break
        ids = [m.id for m in results.matches]
        index.delete(ids=ids)
        deleted += len(ids)

    logger.info(f"Deleted {deleted} vectors for document_id={document_id}")
    return deleted
