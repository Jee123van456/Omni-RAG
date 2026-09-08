import pytest
from database.models import Source
from ingestion.indexing.indexer import index_document_content
from agents.orchestrator import agent_executor

def test_full_rag_pipeline_execution(db_session):
    """
    Integration test executing the full multi-source LangGraph RAG pipeline:
    1. Indexes a test document in the PostgreSQL test database.
    2. Runs the LangGraph agent executor to query the document.
    3. Verifies intent classification, source routing, hybrid vector retrieval,
       citation generation, and confidence score calculation.
    """
    # 1. Setup - Create Source
    source = Source(
        type="documents",
        name="Security Guidelines",
        configuration={"path": "/mock/security"}
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    
    # 2. Ingest document
    raw_text = (
        "# Password Policy\n"
        "Our password rotation policy requires changing passwords every 90 days.\n"
        "Passwords must be at least 12 characters long and contain numbers."
    )
    pages = [
        {"page_number": 1, "text": "# Password Policy\nOur password rotation policy requires changing passwords every 90 days."},
        {"page_number": 2, "text": "Passwords must be at least 12 characters long and contain numbers."}
    ]
    
    doc = index_document_content(
        db=db_session,
        source_id=source.id,
        title="password_guideline.txt",
        uri="file:///mock/security/password_guideline.txt",
        raw_text=raw_text,
        pages=pages
    )
    
    assert doc.id is not None
    
    # 3. Invoke Agent Pipeline via LangGraph
    state_input = {
        "question": "What is our password rotation policy?",
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
        "logs": [],
        "db": db_session
    }
    
    # Execute graph
    state_output = agent_executor.invoke(state_input)
    
    # 4. Asserts
    # Verify classification
    assert state_output["query_type"] in ["DIRECT_LOOKUP", "ANALYSIS", "MULTI_SOURCE"]
    
    # Verify routing plan contains documents source
    routed_sources = [r["source"] for r in state_output["query_plan"]]
    assert "documents" in routed_sources
    
    # Verify evidence retrieved
    assert len(state_output["retrieved_evidence"]) >= 1
    retrieved_contents = [e["content"] for e in state_output["retrieved_evidence"]]
    assert any("90 days" in content for content in retrieved_contents)
    
    # Verify answer generated and grounded
    assert "90 days" in state_output["answer"]
    
    # Verify citations generated
    assert len(state_output["citations"]) >= 1
    assert state_output["citations"][0]["valid"] is True
    assert state_output["citations"][0]["source_type"] == "documents"
    
    # Verify confidence calculation
    assert state_output["confidence"] in ["HIGH", "MEDIUM"]
