import os
import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database.db import get_db
from database.models import Source, Document, IngestionJob
from shared.logging.logger import logger
from shared.config.settings import settings

# Import celery tasks if celery is running
try:
    from workers.tasks import (
        ingest_document_task,
        sync_web_url_task,
        sync_github_repository_task,
        sync_postgres_source_task
    )
    celery_enabled = True
except Exception as e:
    logger.error(f"Celery tasks import failed: {e}. Running synchronously for development.")
    celery_enabled = False

router = APIRouter(prefix="/api/sources", tags=["Sources"])

# Base Directories
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Pydantic schemas for requests
class SourceCreateSchema(BaseModel):
    type: str  # "documents", "web", "github", "postgres"
    name: str
    configuration: dict = {}

class SourceResponseSchema(BaseModel):
    id: int
    type: str
    name: str
    status: str
    configuration: dict
    created_at: datetime.datetime
    
    class Config:
        from_attributes = True

@router.post("", response_model=SourceResponseSchema, status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceCreateSchema, db: Session = Depends(get_db)):
    source = Source(
        type=payload.type,
        name=payload.name,
        status="active" if payload.type == "postgres" else "pending",
        configuration=payload.configuration
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source

@router.get("", response_model=List[SourceResponseSchema])
def list_sources(db: Session = Depends(get_db)):
    return db.query(Source).order_by(Source.created_at.desc()).all()

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(id: int, db: Session = Depends(get_db)):
    source = db.query(Source).filter(Source.id == id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
        
    db.delete(source)
    db.commit()
    return None

@router.post("/{id}/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_source(id: int, db: Session = Depends(get_db)):
    source = db.query(Source).filter(Source.id == id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
        
    # Create ingestion job
    job = IngestionJob(
        source_id=source.id,
        status="pending",
        progress=0.0,
        started_at=datetime.datetime.utcnow()
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Sync triggers based on source type
    if source.type == "web":
        url = source.configuration.get("url")
        if not url:
            raise HTTPException(status_code=400, detail="Missing URL in web source configuration.")
            
        if celery_enabled:
            sync_web_url_task.delay(source.id, url, job.id)
        else:
            # Sync fallback for dev tests
            sync_web_url_task(source.id, url, job.id)
            
    elif source.type == "github":
        repo_path = source.configuration.get("repository_path")
        repo_name = source.configuration.get("repository_name", "custom-repo")
        branch = source.configuration.get("branch", "main")
        
        if not repo_path:
            raise HTTPException(status_code=400, detail="Missing repository_path in configuration.")
            
        if celery_enabled:
            sync_github_repository_task.delay(source.id, repo_path, repo_name, branch, job.id)
        else:
            sync_github_repository_task(source.id, repo_path, repo_name, branch, job.id)
            
    elif source.type == "documents":
        # Handled separately via file upload route
        job.status = "failed"
        job.error = "Syncing document source requires uploading a file using the upload route."
        db.commit()
        raise HTTPException(status_code=400, detail=job.error)

    elif source.type == "postgres":
        db_url = source.configuration.get("connection_string") or source.configuration.get("url") or settings.DATABASE_URL
        if celery_enabled:
            sync_postgres_source_task.delay(source.id, db_url, job.id)
        else:
            sync_postgres_source_task(source.id, db_url, job.id)

    return {"job_id": job.id, "status": "job_started"}

@router.post("/{id}/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document_to_source(
    id: int, 
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    source = db.query(Source).filter(Source.id == id).first()
    if not source or source.type != "documents":
        raise HTTPException(status_code=400, detail="Invalid source id or target source type is not 'documents'.")

    # Save uploaded file
    file_type = file.filename.split(".")[-1].lower() if "." in file.filename else "txt"
    if file_type not in ["pdf", "docx", "txt", "md", "markdown"]:
        raise HTTPException(status_code=400, detail=f"Unsupported file format: {file_type}")
        
    file_path = os.path.join(UPLOAD_DIR, f"{datetime.datetime.utcnow().timestamp()}_{file.filename}")
    
    with open(file_path, "wb") as f:
        f.write(await file.read())

    # Create ingestion job
    job = IngestionJob(
        source_id=source.id,
        status="pending",
        progress=0.0,
        started_at=datetime.datetime.utcnow()
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if celery_enabled:
        ingest_document_task.delay(source.id, file_path, file_type, job.id)
    else:
        ingest_document_task(source.id, file_path, file_type, job.id)

    return {"job_id": job.id, "status": "upload_and_ingestion_started"}

@router.get("/ingestion/{job_id}")
def check_ingestion_status(job_id: int, db: Session = Depends(get_db)):
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
        
    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
        "started_at": job.started_at,
        "completed_at": job.completed_at
    }
