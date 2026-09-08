import json
import time
import datetime
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database.db import get_db
from database.models import (
    Conversation, Message, RetrievalRun, Evidence, Citation, Source
)
from agents.orchestrator import agent_executor
from agents.query_analyzer.analyzer import analyze_query
from agents.router.router import route_query_sources
from shared.logging.logger import logger

router = APIRouter(prefix="/api/chat", tags=["Chat"])

class ChatRequestSchema(BaseModel):
    question: str
    conversation_id: Optional[int] = None
    user_id: Optional[int] = None

@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db)):
    return db.query(Conversation).order_by(Conversation.created_at.desc()).all()

@router.get("/conversations/{id}")
def get_conversation(id: int, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    messages = db.query(Message).filter(Message.conversation_id == id).order_by(Message.created_at.ascii()).all()
    # Format return
    return {
        "id": conv.id,
        "created_at": conv.created_at,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at
            } for m in messages
        ]
    }

@router.post("")
def chat_investigate(payload: ChatRequestSchema, db: Session = Depends(get_db)):
    """
    Standard HTTP endpoint for running the Agentic RAG pipeline.
    Useful for testing or static clients.
    """
    # 1. Fetch or create conversation
    conv_id = payload.conversation_id
    if not conv_id:
        conv = Conversation(user_id=payload.user_id)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        conv_id = conv.id
        
    # Save User message
    user_msg = Message(
        conversation_id=conv_id,
        role="user",
        content=payload.question
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # 2. Run agentic graph
    state_input = {
        "question": payload.question,
        "query_type": "",
        "intent": "",
        "entities": [],
        "sources_to_query": [],
        "query_plan": [],
        "retrieved_evidence": [],
        "conflicts": [],
        "answer": "",
        "citations": [],
        "confidence": "",
        "confidence_reason": "",
        "retrieval_round": 0,
        "reformulated_queries": [],
        "logs": []
    }
    
    start_time = time.time()
    try:
        state_output = agent_executor.invoke(state_input)
        latency_ms = int((time.time() - start_time) * 1000)
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Agent workflow failure: {str(e)}")

    # 3. Persist outputs to Database
    # Save Assistant message
    assistant_msg = Message(
        conversation_id=conv_id,
        role="assistant",
        content=state_output["answer"]
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    
    # Save Retrieval Run metadata
    sources_used = [r["source"] for r in state_output.get("query_plan", [])]
    ret_run = RetrievalRun(
        message_id=assistant_msg.id,
        query=payload.question,
        sources_used=sources_used,
        retrieval_count=len(state_output.get("retrieved_evidence", [])),
        latency_ms=latency_ms
    )
    db.add(ret_run)
    db.commit()
    db.refresh(ret_run)
    
    # Save Evidence items
    for ev in state_output.get("retrieved_evidence", []):
        db_ev = Evidence(
            retrieval_run_id=ret_run.id,
            document_id=ev.get("document_id"),
            chunk_id=ev.get("chunk_id"),
            source_type=ev.get("source_type"),
            content=ev.get("content"),
            score=ev.get("score"),
            metadata_json=ev.get("metadata", {})
        )
        db.add(db_ev)
    db.commit()
    
    # Save Citations (resolve evidence_id mapping if possible, or link first matched)
    evidences = db.query(Evidence).filter(Evidence.retrieval_run_id == ret_run.id).all()
    evidence_chunk_map = {e.chunk_id: e.id for e in evidences if e.chunk_id}
    
    for cit in state_output.get("citations", []):
        c_id = cit.get("chunk_id")
        ev_id = evidence_chunk_map.get(c_id)
        if not ev_id and evidences:
            ev_id = evidences[0].id # fallback
            
        if ev_id:
            db_cit = Citation(
                message_id=assistant_msg.id,
                evidence_id=ev_id,
                claim=cit.get("claim"),
                citation_text=cit.get("citation_text"),
                valid=cit.get("valid", True)
            )
            db.add(db_cit)
    db.commit()

    return {
        "conversation_id": conv_id,
        "message_id": assistant_msg.id,
        "answer": state_output["answer"],
        "citations": state_output["citations"],
        "conflicts": state_output["conflicts"],
        "confidence": state_output["confidence"],
        "confidence_reason": state_output["confidence_reason"],
        "logs": state_output["logs"]
    }

@router.post("/stream")
async def chat_investigate_stream(payload: ChatRequestSchema, db: Session = Depends(get_db)):
    """
    SSE Stream endpoint that sends live logs of agent nodes executing,
    before sending the final RAG payload.
    """
    async def event_generator():
        # Initialize
        conv_id = payload.conversation_id
        if not conv_id:
            conv = Conversation(user_id=payload.user_id)
            db.add(conv)
            db.commit()
            db.refresh(conv)
            conv_id = conv.id

        yield f"data: {json.dumps({'event': 'progress', 'text': 'Analyzing query...'})}\n\n"
        await asyncio.sleep(0.3)
        
        # 1. Classification
        analysis = analyze_query(payload.question)
        yield f"data: {json.dumps({'event': 'progress', 'text': f'✓ Classified as {analysis.query_type}'})}\n\n"
        await asyncio.sleep(0.3)
        
        # 2. Routing
        routes = route_query_sources(payload.question, analysis.query_type, analysis.sources)
        srcs = [r["source"] for r in routes]
        srcs_str = ", ".join(srcs)
        yield f"data: {json.dumps({'event': 'progress', 'text': f'Selecting sources: {srcs_str}...'})}\n\n"
        await asyncio.sleep(0.3)
        
        # 3. Retrieve
        yield f"data: {json.dumps({'event': 'progress', 'text': 'Retrieving and reranking evidence...'})}\n\n"
        
        state_input = {
            "question": payload.question,
            "query_type": analysis.query_type,
            "intent": analysis.intent,
            "entities": analysis.entities,
            "sources_to_query": analysis.sources,
            "query_plan": routes,
            "retrieved_evidence": [],
            "conflicts": [],
            "answer": "",
            "citations": [],
            "confidence": "",
            "confidence_reason": "",
            "retrieval_round": 0,
            "reformulated_queries": [],
            "logs": []
        }
        
        start_time = time.time()
        state_output = agent_executor.invoke(state_input)
        latency_ms = int((time.time() - start_time) * 1000)
        evidence_count = len(state_output["retrieved_evidence"])
        yield f"data: {json.dumps({'event': 'progress', 'text': f'✓ Retrieved {evidence_count} chunks'})}\n\n"
        await asyncio.sleep(0.2)
        
        yield f"data: {json.dumps({'event': 'progress', 'text': 'Checking conflicts and validating citations...'})}\n\n"
        await asyncio.sleep(0.3)

        # Save User Message
        user_msg = Message(conversation_id=conv_id, role="user", content=payload.question)
        db.add(user_msg)
        db.commit()
        
        # Save Assistant Message
        assistant_msg = Message(conversation_id=conv_id, role="assistant", content=state_output["answer"])
        db.add(assistant_msg)
        db.commit()

        # Save runs
        ret_run = RetrievalRun(
            message_id=assistant_msg.id,
            query=payload.question,
            sources_used=srcs,
            retrieval_count=len(state_output["retrieved_evidence"]),
            latency_ms=latency_ms
        )
        db.add(ret_run)
        db.commit()

        # Save evidences
        for ev in state_output["retrieved_evidence"]:
            db_ev = Evidence(
                retrieval_run_id=ret_run.id,
                document_id=ev.get("document_id"),
                chunk_id=ev.get("chunk_id"),
                source_type=ev.get("source_type"),
                content=ev.get("content"),
                score=ev.get("score"),
                metadata_json=ev.get("metadata", {})
            )
            db.add(db_ev)
        db.commit()

        evidences = db.query(Evidence).filter(Evidence.retrieval_run_id == ret_run.id).all()
        evidence_chunk_map = {e.chunk_id: e.id for e in evidences if e.chunk_id}
        
        for cit in state_output.get("citations", []):
            c_id = cit.get("chunk_id")
            ev_id = evidence_chunk_map.get(c_id) or (evidences[0].id if evidences else None)
            if ev_id:
                db_cit = Citation(
                    message_id=assistant_msg.id,
                    evidence_id=ev_id,
                    claim=cit.get("claim"),
                    citation_text=cit.get("citation_text"),
                    valid=cit.get("valid", True)
                )
                db.add(db_cit)
        db.commit()

        # Yield completion payload
        completion_data = {
            'event': 'complete',
            'data': {
                'conversation_id': conv_id,
                'message_id': assistant_msg.id,
                'answer': state_output['answer'],
                'citations': state_output['citations'],
                'conflicts': state_output['conflicts'],
                'confidence': state_output['confidence'],
                'confidence_reason': state_output['confidence_reason'],
                'logs': state_output['logs']
            }
        }
        yield f"data: {json.dumps(completion_data)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
