import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, 
    Text, Float, Boolean, JSON
)
from sqlalchemy.orm import relationship
from database.db import Base
from pgvector.sqlalchemy import Vector

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)  # "documents", "web", "github", "postgres"
    name = Column(String, nullable=False)
    status = Column(String, default="active")  # "active", "syncing", "error"
    configuration = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    documents = relationship("Document", back_populates="source", cascade="all, delete-orphan")
    ingestion_jobs = relationship("IngestionJob", back_populates="source", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    uri = Column(String, nullable=False)
    content_hash = Column(String, index=True, nullable=True)
    metadata_json = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    source = relationship("Source", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="document")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=True)  # Standard dimension for OpenAI models
    metadata_json = Column("metadata", JSON, default=dict)
    token_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    document = relationship("Document", back_populates="chunks")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, default="pending")  # "pending", "running", "completed", "failed"
    progress = Column(Float, default=0.0)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    source = relationship("Source", back_populates="ingestion_jobs")


class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")
    retrieval_runs = relationship("RetrievalRun", back_populates="message", cascade="all, delete-orphan")
    citations = relationship("Citation", back_populates="message", cascade="all, delete-orphan")


class RetrievalRun(Base):
    __tablename__ = "retrieval_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    query = Column(Text, nullable=False)
    sources_used = Column(JSON, default=list)
    retrieval_count = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    message = relationship("Message", back_populates="retrieval_runs")
    evidence = relationship("Evidence", back_populates="retrieval_run", cascade="all, delete-orphan")


class Evidence(Base):
    __tablename__ = "evidence"
    
    id = Column(Integer, primary_key=True, index=True)
    retrieval_run_id = Column(Integer, ForeignKey("retrieval_runs.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    chunk_id = Column(Integer, ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True)
    source_type = Column(String, nullable=False)  # "documents", "web", "github", "postgres"
    content = Column(Text, nullable=False)
    score = Column(Float, nullable=False)
    metadata_json = Column("metadata", JSON, default=dict)

    retrieval_run = relationship("RetrievalRun", back_populates="evidence")
    document = relationship("Document", back_populates="evidence")
    citations = relationship("Citation", back_populates="evidence", cascade="all, delete-orphan")


class Citation(Base):
    __tablename__ = "citations"
    
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    evidence_id = Column(Integer, ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False)
    claim = Column(Text, nullable=False)
    citation_text = Column(Text, nullable=False)
    valid = Column(Boolean, default=True)

    message = relationship("Message", back_populates="citations")
    evidence = relationship("Evidence", back_populates="citations")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    dataset = Column(String, nullable=False)
    model = Column(String, nullable=False)
    metrics = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
