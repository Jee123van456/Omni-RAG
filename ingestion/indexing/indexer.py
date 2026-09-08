import hashlib
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from database.models import Document, DocumentChunk, IngestionJob, Source
from ingestion.chunking.semantic_chunker import chunk_document
from ingestion.embeddings.embedder import embedder
from shared.logging.logger import logger

def calculate_content_hash(text: str) -> str:
    """
    Computes MD5 hash of raw text to identify content duplicates.
    """
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def index_document_content(
    db: Session,
    source_id: int,
    title: str,
    uri: str,
    raw_text: str,
    pages: List[Dict[str, Any]],
    job_id: int = None
) -> Document:
    """
    Idempotent document ingestion pipeline:
      1. Calculates content hash.
      2. If already indexed under this source, returns existing record.
      3. Otherwise, creates Document record.
      4. Chunks text using paragraph-structure.
      5. Embeds chunks.
      6. Inserts DocumentChunks with pgvector embeddings.
    """
    if job_id:
        job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
        if job:
            job.status = "running"
            job.progress = 0.1
            db.commit()

    content_hash = calculate_content_hash(raw_text)
    
    # Check if duplicate exists for this source
    existing_doc = db.query(Document).filter(
        Document.source_id == source_id,
        Document.content_hash == content_hash
    ).first()
    
    if existing_doc:
        logger.info(f"Document already indexed (hash match): {title}. Skipping duplicate ingestion.")
        if job_id and job:
            job.status = "completed"
            job.progress = 1.0
            db.commit()
        return existing_doc

    # Create new document
    doc = Document(
        source_id=source_id,
        title=title,
        uri=uri,
        content_hash=content_hash,
        metadata_json={"pages_count": len(pages)}
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    if job_id and job:
        job.progress = 0.3
        db.commit()

    try:
        # Create semantic chunks
        chunks = chunk_document(raw_text, pages)
        
        if job_id and job:
            job.progress = 0.5
            db.commit()

        # Batch embed and insert
        total_chunks = len(chunks)
        for idx, chunk_data in enumerate(chunks):
            content = chunk_data["content"]
            chunk_index = chunk_data["chunk_index"]
            meta = chunk_data["metadata"]
            
            # Generate embedding vector
            embedding_vector = embedder.embed_text(content)
            
            # Estimate token count (standard heuristic: ~4 chars per token)
            token_count = len(content) // 4
            
            db_chunk = DocumentChunk(
                document_id=doc.id,
                chunk_index=chunk_index,
                content=content,
                embedding=embedding_vector,
                metadata_json=meta,
                token_count=token_count
            )
            db.add(db_chunk)
            
            # Update job progress dynamically
            if job_id and job:
                job.progress = 0.5 + (0.4 * (idx + 1) / total_chunks)
                db.commit()
                
        db.commit()
        
        if job_id and job:
            job.status = "completed"
            job.progress = 1.0
            db.commit()
            
        logger.info(f"Ingested document: {title} successfully into {total_chunks} chunks.")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error during document ingestion indexing: {e}")
        if job_id and job:
            job.status = "failed"
            job.error = str(e)
            db.commit()
        raise e

    return doc
