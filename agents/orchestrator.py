import re
import json
from typing import Dict, Any, List, Literal, TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from sqlalchemy.orm import Session

from shared.config.settings import settings
from shared.logging.logger import logger
from database.db import SessionLocal
from database.models import Source, Document, DocumentChunk
from agents.query_analyzer.analyzer import analyze_query
from agents.router.router import route_query_sources
from ingestion.embeddings.embedder import embedder
from retrieval.hybrid import query_hybrid_search
from retrieval.reranker import rerank_candidates
from connectors.postgres.postgres_connector import (
    get_database_schema_info,
    execute_safe_read_query,
    validate_sql_safety
)
from agents.conflict.detector import detect_conflicts
from agents.answer.generator import generate_grounded_answer

class AgentState(TypedDict, total=False):
    question: str
    query_type: str
    intent: str
    entities: List[str]
    sources_to_query: List[str]
    query_plan: List[Dict[str, Any]]
    retrieved_evidence: List[Dict[str, Any]]
    conflicts: List[Dict[str, Any]]
    answer: str
    citations: List[Dict[str, Any]]
    confidence: str
    confidence_reason: str
    retrieval_round: int
    reformulated_queries: List[str]
    logs: List[str]
    db: Optional[Session]

# ----------------- Helper: Mock LLM SQL Agent -----------------
def generate_sql_query_helper(question: str, schema_info: str) -> str:
    """
    Formulates a safe read-only SQL query based on the schema information.
    Falls back to heuristics if OpenAI is not enabled.
    """
    question_lower = question.lower()
    
    # Heuristics for local testing of active tables
    if "how many users" in question_lower or "count of users" in question_lower:
        return "SELECT COUNT(*) as user_count FROM users;"
    if "list users" in question_lower or "all users" in question_lower:
        return "SELECT id, email, created_at FROM users LIMIT 10;"
    if "list sources" in question_lower or "connected sources" in question_lower:
        return "SELECT id, type, name, status FROM sources LIMIT 10;"
    if "how many documents" in question_lower:
        return "SELECT COUNT(*) as doc_count FROM documents;"

    api_key = settings.OPENAI_API_KEY
    if not api_key or api_key == "mock-key" or api_key == "your-openai-api-key":
        # Safe default select
        return "SELECT 1 as ping;"
        
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import PromptTemplate
        
        llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=api_key, temperature=0.0)
        prompt = PromptTemplate.from_template(
            "You are a PostgreSQL expert. Given the schema:\n{schema}\n\n"
            "Write a read-only SQL query to answer: {question}\n"
            "Write ONLY the SQL code. Do not include markdown wraps."
        )
        chain = prompt | llm
        response = chain.invoke({"schema": schema_info, "question": question})
        sql = response.content.strip()
        # Clean any markdown wrap
        sql = re.sub(r'```sql|```', '', sql).strip()
        return sql
    except Exception as e:
        logger.error(f"SQL generation failed: {e}")
        return "SELECT 1 as ping;"

# ----------------- LangGraph Node Definitions -----------------

def analyze_query_node(state: AgentState) -> Dict[str, Any]:
    question = state["question"]
    logger.info(f"--- Node: Analyze Query: '{question}' ---")
    
    analysis = analyze_query(question)
    
    return {
        "query_type": analysis.query_type,
        "intent": analysis.intent,
        "entities": analysis.entities,
        "sources_to_query": analysis.sources,
        "logs": state.get("logs", []) + ["Analyzed query and identified classification: " + analysis.query_type]
    }

def plan_and_route_node(state: AgentState) -> Dict[str, Any]:
    logger.info("--- Node: Plan & Route Sources ---")
    
    routes = route_query_sources(
        state["question"],
        state["query_type"],
        state["sources_to_query"]
    )
    
    return {
        "query_plan": routes,
        "logs": state.get("logs", []) + [f"Routed query to sources: {', '.join(r['source'] for r in routes)}"]
    }

def retrieve_evidence_node(state: AgentState) -> Dict[str, Any]:
    logger.info("--- Node: Retrieve Multi-Source Evidence ---")
    
    db = state.get("db")
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
        
    evidence_list = list(state.get("retrieved_evidence", []))
    logs = list(state.get("logs", []))
    
    # Prepare query embedding
    query_text = state["question"]
    if state["reformulated_queries"]:
        query_text = state["reformulated_queries"][-1]
        
    query_embedding = embedder.embed_text(query_text)
    
    for route in state["query_plan"]:
        source_type = route["source"]
        search_query = route["query"]
        
        logger.info(f"Processing route for source: '{source_type}' with query '{search_query}'")
        
        # Determine source database IDs matching the source_type
        sources = db.query(Source).filter(Source.type == source_type).all()
        source_ids = [s.id for s in sources]
        
        if source_type in ["documents", "web"]:
            # Perform hybrid dense + lexical search over indexed document chunks
            if not source_ids:
                logs.append(f"No active database source found for '{source_type}'. Skipping search.")
                continue
                
            candidates = query_hybrid_search(db, search_query, query_embedding, top_k=6, source_ids=source_ids)
            reranked = rerank_candidates(search_query, query_embedding, candidates, top_k=3)
            
            for chunk, score in reranked:
                # Add to evidence state
                evidence_list.append({
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "source_type": source_type,
                    "content": chunk.content,
                    "score": score,
                    "metadata": chunk.metadata_json
                })
            logs.append(f"Retrieved {len(reranked)} chunks from '{source_type}' connector.")
            
        elif source_type == "github":
            # For simplicity, search repositories indexed under GitHub sources using vector/lexical retrieval
            if not source_ids:
                logs.append("No active GitHub repository sources connected. Skipping github search.")
                continue
                
            candidates = query_hybrid_search(db, search_query, query_embedding, top_k=6, source_ids=source_ids)
            reranked = rerank_candidates(search_query, query_embedding, candidates, top_k=3)
            
            for chunk, score in reranked:
                evidence_list.append({
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "source_type": "github",
                    "content": chunk.content,
                    "score": score,
                    "metadata": chunk.metadata_json
                })
            logs.append(f"Retrieved {len(reranked)} code structures from GitHub connector.")
            
        elif source_type == "postgres":
            # Execute Read-only SQL Agent
            try:
                # 1. Discover active DB schemas
                schema_info = get_database_schema_info(settings.DATABASE_URL)
                
                # 2. Formulate read-only SQL query
                generated_sql = generate_sql_query_helper(search_query, schema_info)
                logger.info(f"SQL Agent formulated query: {generated_sql}")
                
                # 3. Validate safety
                is_safe = validate_sql_safety(generated_sql)
                if not is_safe:
                    logs.append(f"SQL Agent safety validation block: '{generated_sql}' contains forbidden modifications.")
                    continue
                    
                # 4. Execute safely against local database
                rows = execute_safe_read_query(settings.DATABASE_URL, generated_sql, limit=10, timeout_sec=4)
                
                # Format SQL output as structured evidence content
                formatted_rows = "\n".join([str(row) for row in rows])
                evidence_list.append({
                    "chunk_id": None,
                    "document_id": None,
                    "source_type": "postgres",
                    "content": f"SQL Query Executed:\n{generated_sql}\n\nResults:\n{formatted_rows}",
                    "score": 1.0,
                    "metadata": {"query": generated_sql, "row_count": len(rows)}
                })
                logs.append(f"SQL Agent executed query successfully, returning {len(rows)} records.")
                
            except Exception as e:
                logger.error(f"SQL Agent node failure: {e}")
                logs.append(f"SQL Agent connection failed: {str(e)}")

    if should_close:
        db.close()
    
    return {
        "retrieved_evidence": evidence_list,
        "logs": logs,
        "retrieval_round": state.get("retrieval_round", 0) + 1
    }

def evaluate_sufficiency_node(state: AgentState) -> Dict[str, Any]:
    logger.info("--- Node: Evaluate Sufficiency ---")
    
    evidence = state["retrieved_evidence"]
    rounds = state["retrieval_round"]
    logs = list(state.get("logs", []))
    
    # Condition: we have enough evidence if we have at least 1 result, or reached round 3
    if len(evidence) > 0 or rounds >= 3:
        logs.append(f"Sufficiency check: PASSED (evidence count: {len(evidence)}, rounds: {rounds})")
        return {
            "logs": logs
        }
        
    # Otherwise: reformulate and prepare for round 2/3
    question = state["question"]
    reformulated = f"alternative terms matching {question}" # Mock reformulation
    
    api_key = settings.OPENAI_API_KEY
    if api_key and api_key != "mock-key" and api_key != "your-openai-api-key":
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=api_key, temperature=0.3)
            response = llm.invoke(f"Reformulate the query to optimize RAG search: {question}")
            reformulated = response.content.strip()
        except Exception:
            pass
            
    logs.append(f"Sufficiency check: FAILED (no evidence in round {rounds}). Reformulating query to: '{reformulated}'")
    
    return {
        "reformulated_queries": state.get("reformulated_queries", []) + [reformulated],
        "logs": logs
    }

def generate_answer_node(state: AgentState) -> Dict[str, Any]:
    logger.info("--- Node: Detect Conflicts & Generate Grounded Answer ---")
    
    evidence = state["retrieved_evidence"]
    logs = list(state.get("logs", []))
    
    # 1. Detect any source conflicts/contradictions
    conflicts = detect_conflicts(evidence)
    if conflicts:
        logs.append(f"Conflict Detector: Warn! Found {len(conflicts)} contradiction(s) between sources.")
    else:
        logs.append("Conflict Detector: No direct source contradictions found.")
        
    # 2. Generate final answer with validated citations
    answer_package = generate_grounded_answer(state["question"], evidence, conflicts)
    
    logs.append("Grounded Generation: Answer produced and citations validated successfully.")
    
    return {
        "conflicts": conflicts,
        "answer": answer_package["answer"],
        "citations": answer_package["citations"],
        "confidence": answer_package["confidence"],
        "confidence_reason": answer_package["confidence_reason"],
        "logs": logs
    }

# ----------------- Conditional Routing -----------------

def decide_sufficiency_routing(state: AgentState) -> Literal["retrieve", "generate"]:
    evidence = state["retrieved_evidence"]
    rounds = state["retrieval_round"]
    
    if len(evidence) > 0 or rounds >= 3:
        return "generate"
    return "retrieve"

# ----------------- Build LangGraph State Machine -----------------

def build_agent_graph() -> StateGraph:
    workflow = StateGraph(AgentState)
    
    # Define Nodes
    workflow.add_node("analyze_query", analyze_query_node)
    workflow.add_node("plan_and_route", plan_and_route_node)
    workflow.add_node("retrieve_evidence", retrieve_evidence_node)
    workflow.add_node("evaluate_sufficiency", evaluate_sufficiency_node)
    workflow.add_node("generate_answer", generate_answer_node)
    
    # Define Transitions
    workflow.add_edge(START, "analyze_query")
    workflow.add_edge("analyze_query", "plan_and_route")
    workflow.add_edge("plan_and_route", "retrieve_evidence")
    workflow.add_edge("retrieve_evidence", "evaluate_sufficiency")
    
    # Conditional Sufficiency check
    workflow.add_conditional_edges(
        "evaluate_sufficiency",
        decide_sufficiency_routing,
        {
            "retrieve": "retrieve_evidence",
            "generate": "generate_answer"
        }
    )
    
    workflow.add_edge("generate_answer", END)
    
    return workflow.compile()

# Global compiled agent graph
agent_executor = build_agent_graph()
