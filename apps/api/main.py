import datetime
import logging
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
import redis

from shared.config.settings import settings
from shared.logging.logger import logger
from database.db import get_db

app = FastAPI(
    title="OmniRAG API",
    description="Enterprise-grade Multi-Source Agentic RAG Platform API",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import routes
from apps.api.routes.sources import router as sources_router
from apps.api.routes.chat import router as chat_router
from apps.api.routes.evaluations import router as evaluations_router

# Include routers
app.include_router(sources_router)
app.include_router(chat_router)
app.include_router(evaluations_router)

@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """
    Simple health check endpoint to verify that the API is running.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "version": "1.0.0",
    }

@app.get("/api/health", status_code=status.HTTP_200_OK)
def api_health_check(db: Session = Depends(get_db)):
    """
    Comprehensive health check verifying database and cache connectivity.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "services": {}
    }
    
    # 1. Check Database Connectivity
    try:
        db.execute(text("SELECT 1"))
        health_status["services"]["database"] = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["services"]["database"] = f"disconnected: {str(e)}"
        health_status["status"] = "unhealthy"
        
    # 2. Check Redis Connectivity
    try:
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
        health_status["services"]["redis"] = "connected"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        health_status["services"]["redis"] = f"disconnected: {str(e)}"
        health_status["status"] = "unhealthy"

    if health_status["status"] == "unhealthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=health_status
        )
        
    return health_status
