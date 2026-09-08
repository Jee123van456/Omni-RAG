import os
import datetime
import hashlib
from celery import Celery
from sqlalchemy.orm import Session

from shared.config.settings import settings
from shared.logging.logger import logger
from database.db import SessionLocal
from database.models import IngestionJob, Source, Document, DocumentChunk
from ingestion.loaders.file_loader import extract_file_content
from ingestion.indexing.indexer import index_document_content
from connectors.web.web_connector import fetch_and_clean_webpage
from connectors.github.github_connector import scan_repository_directory
from connectors.postgres.postgres_connector import get_database_schema_info
from ingestion.embeddings.embedder import embedder

# Initialize Celery app
celery_app = Celery(
    "omnirag_tasks", 
    broker=settings.REDIS_URL, 
    backend=settings.REDIS_URL
)

@celery_app.task(name="tasks.ingest_document")
def ingest_document_task(source_id: int, file_path: str, file_type: str, job_id: int) -> bool:
    """
    Asynchronous Celery task for processing and indexing document files.
    """
    db: Session = SessionLocal()
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        db.close()
        return False
        
    try:
        job.status = "running"
        job.progress = 0.1
        db.commit()
        
        # 1. Content Extraction
        extracted = extract_file_content(file_path, file_type)
        job.progress = 0.4
        db.commit()
        
        # 2. Semantic Chunking & Indexing
        title = extracted["metadata"]["filename"]
        uri = f"file://{file_path}"
        index_document_content(
            db=db,
            source_id=source_id,
            title=title,
            uri=uri,
            raw_text=extracted["text"],
            pages=extracted["pages"],
            job_id=job_id
        )
        
        logger.info(f"Background task: Document ingestion job {job_id} completed.")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Failed document ingestion task {job_id}: {e}")
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.datetime.utcnow()
        db.commit()
        return False
    finally:
        db.close()

@celery_app.task(name="tasks.sync_web_url")
def sync_web_url_task(source_id: int, url: str, job_id: int) -> bool:
    """
    Asynchronous Celery task for crawling and indexing website pages.
    """
    db: Session = SessionLocal()
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        db.close()
        return False
        
    try:
        job.status = "running"
        job.progress = 0.2
        db.commit()
        
        # 1. Fetch and clean website
        crawled = fetch_and_clean_webpage(url)
        job.progress = 0.5
        db.commit()
        
        # 2. Index
        index_document_content(
            db=db,
            source_id=source_id,
            title=crawled["title"],
            uri=url,
            raw_text=crawled["text"],
            pages=crawled["pages"],
            job_id=job_id
        )
        
        logger.info(f"Background task: Web ingestion job {job_id} completed.")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Failed web ingestion task {job_id}: {e}")
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.datetime.utcnow()
        db.commit()
        return False
    finally:
        db.close()

@celery_app.task(name="tasks.sync_github_repository")
def sync_github_repository_task(source_id: int, repo_path: str, repo_name: str, branch: str, job_id: int) -> bool:
    """
    Asynchronous Celery task for parsing and indexing code repositories.
    """
    db: Session = SessionLocal()
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        db.close()
        return False
        
    try:
        job.status = "running"
        job.progress = 0.2
        db.commit()
        
        # 1. Scan directory structure and extract chunks
        logger.info(f"Scanning directory: {repo_path} for repo {repo_name}")
        chunks = scan_repository_directory(repo_path, repo_name, branch)
        
        if not chunks:
            raise ValueError("No matching code structures or text files found in repository path.")
            
        job.progress = 0.4
        db.commit()
        
        # 2. Manually Index Code Chunks
        total_chunks = len(chunks)
        
        # Create a single placeholder document to map chunks to
        doc = Document(
            source_id=source_id,
            title=f"GitHub Repository: {repo_name} ({branch})",
            uri=f"github://{repo_name}",
            content_hash=hashlib.md5(repo_path.encode()).hexdigest(),
            metadata_json={"repo_name": repo_name, "branch": branch, "total_chunks": total_chunks}
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        
        for idx, chunk_data in enumerate(chunks):
            content = chunk_data["content"]
            meta = chunk_data["metadata"]
            
            # Generate embedding
            embedding_vector = embedder.embed_text(content)
            
            db_chunk = DocumentChunk(
                document_id=doc.id,
                chunk_index=chunk_data["chunk_index"],
                content=content,
                embedding=embedding_vector,
                metadata_json=meta,
                token_count=len(content) // 4
            )
            db.add(db_chunk)
            
            # Update job progress dynamically
            job.progress = 0.4 + (0.5 * (idx + 1) / total_chunks)
            if idx % 10 == 0:
                db.commit()
                
        job.status = "completed"
        job.progress = 1.0
        job.completed_at = datetime.datetime.utcnow()
        db.commit()
        
        logger.info(f"Background task: GitHub sync job {job_id} completed successfully.")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Failed GitHub repository sync {job_id}: {e}")
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.datetime.utcnow()
        db.commit()
        return False
    finally:
        db.close()

@celery_app.task(name="tasks.sync_postgres_source")
def sync_postgres_source_task(source_id: int, db_url: str, job_id: int) -> bool:
    """
    Asynchronous Celery task for extracting and indexing PostgreSQL database schema.
    """
    db: Session = SessionLocal()
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        db.close()
        return False
        
    try:
        job.status = "running"
        job.progress = 0.2
        db.commit()
        
        # 1. Fetch schema info
        schema_text = get_database_schema_info(db_url)
        if not schema_text or schema_text.startswith("Error"):
            raise ValueError(schema_text or "Could not retrieve PostgreSQL schema.")
            
        job.progress = 0.5
        db.commit()
        
        # 2. Index
        pages = [{"page_number": 1, "text": schema_text}]
        doc_uri = db_url.split("@")[-1] if "@" in db_url else "postgres://schema"
        index_document_content(
            db=db,
            source_id=source_id,
            title="PostgreSQL Database Schema",
            uri=f"postgres://{doc_uri}",
            raw_text=schema_text,
            pages=pages,
            job_id=job_id
        )
        
        logger.info(f"Background task: Postgres schema sync job {job_id} completed successfully.")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Failed Postgres schema sync task {job_id}: {e}")
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.datetime.utcnow()
        db.commit()
        return False
    finally:
        db.close()

