import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (two levels up from backend/)
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# AWS
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Bedrock models
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
BEDROCK_EMBEDDING_MODEL_ID = os.getenv("BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")

# Pinecone
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "o2c-rag-docs")

# RAG settings
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
RETRIEVER_TOP_K = int(os.getenv("RETRIEVER_TOP_K", "5"))

# Pinecone free tier limits
PINECONE_MAX_STORAGE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
EMBEDDING_DIM = 1024  # Titan Embed v2 dimension
ESTIMATED_BYTES_PER_VECTOR = 4 * EMBEDDING_DIM + 500  # float32 + metadata overhead
MAX_VECTORS = PINECONE_MAX_STORAGE_BYTES // ESTIMATED_BYTES_PER_VECTOR

# File upload limits — conservative estimate for Pinecone free tier
# ~400K vectors × ~2KB text per chunk ≈ ~800MB raw text capacity
# With format overhead, ~200MB file size is a safe ceiling
MAX_UPLOAD_FILE_SIZE_MB = 200
MAX_TOTAL_STORAGE_MB = 500  # warn when cumulative uploads approach this

UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
