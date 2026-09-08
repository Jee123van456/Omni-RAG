import time
import json
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from database.db import SessionLocal
from database.models import EvaluationRun
from agents.orchestrator import agent_executor
from shared.logging.logger import logger

# Golden Dataset as defined in prompt requirements
GOLDEN_DATASET = [
    {
        "question": "What is our company refund window policy?",
        "expected_answer": "30 days",
        "expected_sources": ["documents"],
        "difficulty": 1  # Direct lookup
    },
    {
        "question": "How many total users do we have in our database?",
        "expected_answer": "Count of users in the system",
        "expected_sources": ["postgres"],
        "difficulty": 2  # Structured data
    },
    {
        "question": "Where is the authentication middleware implemented in our code?",
        "expected_answer": "Details of auth middleware implementation",
        "expected_sources": ["github"],
        "difficulty": 2  # Code search
    },
    {
        "question": "Compare our internal refund policy with our public website text.",
        "expected_answer": "Internal is 30 days, public is 14 days",
        "expected_sources": ["documents", "web"],
        "difficulty": 5  # Conflicting evidence
    },
    {
        "question": "Is there any discrepancy between website pricing and repository config files?",
        "expected_answer": "Pricing mismatch details",
        "expected_sources": ["web", "github"],
        "difficulty": 10  # Complex multi-source reasoning
    },
    {
        "question": "What are our server deployment environment settings?",
        "expected_answer": "Production settings details",
        "expected_sources": ["documents"],
        "difficulty": 3  # Multi-hop
    },
    {
        "question": "Compare database schema structures for postgres sources.",
        "expected_answer": "Schema differences",
        "expected_sources": ["postgres"],
        "difficulty": 4  # Cross-source
    },
    {
        "question": "How to handle database connection issues?",
        "expected_answer": "Retry settings and connection timeouts",
        "expected_sources": ["documents", "github"],
        "difficulty": 6  # Distractor info
    },
    {
        "question": "What is the policy regarding database password rotation?",
        "expected_answer": "Unavailable info",
        "expected_sources": ["documents"],
        "difficulty": 8  # Insufficient evidence
    },
    {
        "question": "Give me code changes needed to add drop table sql commands.",
        "expected_answer": "Blocked command validation",
        "expected_sources": ["postgres"],
        "difficulty": 9  # Adversarial SQL validation
    }
]

def run_evaluation_suite(dataset_name: str = "Golden Golden Core") -> Dict[str, Any]:
    """
    Executes the golden dataset queries, measures RAG pipeline performance,
    computes evaluation metrics, and persists run data.
    """
    db: Session = SessionLocal()
    
    total_latency = 0.0
    total_recall = 0.0
    total_faithfulness = 0.0
    total_citation_acc = 0.0
    
    test_runs_results = []
    
    logger.info(f"Starting evaluation suite: {dataset_name} ({len(GOLDEN_DATASET)} queries)")
    
    for case in GOLDEN_DATASET:
        question = case["question"]
        expected_srcs = case["expected_sources"]
        
        start_time = time.time()
        
        # Execute agent workflow
        state_input = {
            "question": question,
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
        
        try:
            state_output = agent_executor.invoke(state_input)
            latency_ms = int((time.time() - start_time) * 1000)
            
            # --- Calculate Metrics ---
            # 1. Source Recall@K
            routed_sources = [r["source"] for r in state_output.get("query_plan", [])]
            matched_sources = set(expected_srcs).intersection(set(routed_sources))
            recall = len(matched_sources) / len(expected_srcs) if expected_srcs else 1.0
            
            # 2. Citation Accuracy
            citations = state_output.get("citations", [])
            valid_citations = sum(1 for c in citations if c.get("valid", False))
            citation_acc = (valid_citations / len(citations)) if citations else 1.0
            
            # 3. Faithfulness (Groundedness check: ratio of answer grounded in retrieved chunks)
            # In mock mode, we measure based on whether answer was produced and checked for conflicts
            has_conflicts = len(state_output.get("conflicts", [])) > 0
            faithfulness = 1.0
            if has_conflicts and "CONFLICT DETECTED" not in state_output.get("answer", ""):
                faithfulness = 0.3  # Penalized if conflicts were found but not reported
            elif not state_output.get("answer"):
                faithfulness = 0.0
                
            total_latency += latency_ms
            total_recall += recall
            total_citation_acc += citation_acc
            total_faithfulness += faithfulness
            
            test_runs_results.append({
                "question": question,
                "difficulty": case["difficulty"],
                "recall": recall,
                "citation_accuracy": citation_acc,
                "faithfulness": faithfulness,
                "latency_ms": latency_ms,
                "confidence": state_output.get("confidence", "LOW")
            })
        except Exception as e:
            logger.error(f"Evaluation query failed '{question}': {e}")
            test_runs_results.append({
                "question": question,
                "difficulty": case["difficulty"],
                "recall": 0.0,
                "citation_accuracy": 0.0,
                "faithfulness": 0.0,
                "latency_ms": 0,
                "error": str(e)
            })

    # Average metrics
    count = len(GOLDEN_DATASET)
    avg_latency = total_latency / count
    avg_recall = total_recall / count
    avg_citation_acc = total_citation_acc / count
    avg_faithfulness = total_faithfulness / count
    
    summary_metrics = {
        "avg_latency_ms": int(avg_latency),
        "avg_recall_at_k": float(avg_recall),
        "avg_citation_accuracy": float(avg_citation_acc),
        "avg_faithfulness": float(avg_faithfulness),
        "hallucination_rate": float(1.0 - avg_faithfulness),
        "total_cost_usd": float(count * 0.002), # Mock Cost heuristic
        "test_runs": test_runs_results
    }
    
    # Save evaluation run to database
    run_record = EvaluationRun(
        dataset=dataset_name,
        model="gpt-4o-mini / local-heuristics",
        metrics=summary_metrics
    )
    db.add(run_record)
    db.commit()
    db.refresh(run_record)
    db.close()
    
    logger.info(f"Evaluation run {run_record.id} completed. Metrics logged.")
    return summary_metrics
