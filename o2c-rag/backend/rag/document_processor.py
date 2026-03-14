import uuid
import logging
from pathlib import Path
from typing import BinaryIO

from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
    CSVLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from config import CHUNK_SIZE, CHUNK_OVERLAP

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv"}


def validate_file_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return ext


def load_document(file_path: str) -> list[Document]:
    ext = Path(file_path).suffix.lower()
    loaders = {
        ".pdf": lambda: PyPDFLoader(file_path),
        ".docx": lambda: Docx2txtLoader(file_path),
        ".txt": lambda: TextLoader(file_path, encoding="utf-8"),
        ".csv": lambda: CSVLoader(file_path, encoding="utf-8"),
    }
    loader = loaders.get(ext)
    if not loader:
        raise ValueError(f"No loader for extension: {ext}")

    docs = loader().load()
    logger.info(f"Loaded {len(docs)} pages/sections from {Path(file_path).name}")
    return docs


def chunk_documents(
    docs: list[Document],
    document_id: str,
    document_name: str,
) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
        is_separator_regex=False,
    )

    chunks = splitter.split_documents(docs)

    # Enrich every chunk with metadata for traceability
    for idx, chunk in enumerate(chunks):
        chunk.metadata.update({
            "document_id": document_id,
            "document_name": document_name,
            "chunk_index": idx,
            "total_chunks": len(chunks),
            "char_count": len(chunk.page_content),
        })
        # Preserve page number from PDF loader if present
        if "page" in chunk.metadata:
            chunk.metadata["page_number"] = chunk.metadata.pop("page") + 1  # 1-indexed

    logger.info(
        f"Split '{document_name}' into {len(chunks)} chunks "
        f"(chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})"
    )
    return chunks


def process_upload(file_path: str, original_filename: str) -> tuple[str, list[Document]]:
    document_id = str(uuid.uuid4())
    docs = load_document(file_path)
    chunks = chunk_documents(docs, document_id, original_filename)
    return document_id, chunks
