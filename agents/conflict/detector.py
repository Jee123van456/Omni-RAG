import re
import json
from typing import List, Dict, Any
from shared.config.settings import settings
from shared.logging.logger import logger
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

class ConflictDetail(BaseModel):
    conflict_detected: bool = Field(description="True if different sources contradict each other")
    source_a: str = Field(description="Name/ID of Source A involved in contradiction")
    source_b: str = Field(description="Name/ID of Source B involved in contradiction")
    claim_a: str = Field(description="Claim statement in Source A")
    claim_b: str = Field(description="Contradictory claim statement in Source B")
    recommendation: str = Field(description="Suggested resolution (e.g. Human verification required, favor newest)")
    explanation: str = Field(description="Explanation of the conflict considering freshness, authority, or version")

class ConflictReport(BaseModel):
    conflicts: List[ConflictDetail] = Field(default=[], description="List of detected conflicts")

def rule_based_conflict_detector(evidence_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Offline/local rule-based contradiction scanner. 
    Looks for conflicting metrics or numbers on similar subjects (e.g., refund windows).
    """
    conflicts = []
    
    # 1. Look for conflicting numbers in chunks containing keywords like 'days' or 'refund'
    refund_chunks = []
    for ev in evidence_list:
        content = ev.get("content", "").lower()
        if "refund" in content or "window" in content or "policy" in content:
            # Find numbers associated with days, e.g., "30 days", "14 days"
            day_matches = re.findall(r'(\d+)\s*day', content)
            if day_matches:
                refund_chunks.append({
                    "source": ev.get("source_type", "document") + f" (id: {ev.get('document_id', 'unknown')})",
                    "days": int(day_matches[0]),
                    "text": ev.get("content"),
                    "metadata": ev.get("metadata", {})
                })
                
    # Compare
    if len(refund_chunks) >= 2:
        for i in range(len(refund_chunks)):
            for j in range(i + 1, len(refund_chunks)):
                a = refund_chunks[i]
                b = refund_chunks[j]
                if a["days"] != b["days"]:
                    conflicts.append({
                        "conflict_detected": True,
                        "source_a": a["source"],
                        "source_b": b["source"],
                        "claim_a": f"Refund window is stated as {a['days']} days.",
                        "claim_b": f"Refund window is stated as {b['days']} days.",
                        "recommendation": "Human verification required to resolve policy discrepancy.",
                        "explanation": f"Source A ({a['source']}) claims a {a['days']}-day window while Source B ({b['source']}) claims a {b['days']}-day window."
                    })
                    
    return conflicts

def detect_conflicts(evidence_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Inspects evidence list to detect contradictory claims across different sources.
    """
    if len(evidence_list) < 2:
        return []

    api_key = settings.OPENAI_API_KEY
    if not api_key or api_key == "mock-key" or api_key == "your-openai-api-key":
        return rule_based_conflict_detector(evidence_list)
        
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=api_key, temperature=0.0)
        structured_llm = llm.with_structured_output(ConflictReport)
        
        evidence_str = ""
        for idx, ev in enumerate(evidence_list):
            evidence_str += f"\n--- Evidence ID: {idx} (Source: {ev.get('source_type')}, Doc ID: {ev.get('document_id')}) ---\n"
            evidence_str += f"Content: {ev.get('content')}\n"
            evidence_str += f"Metadata: {json.dumps(ev.get('metadata', {}))}\n"

        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are an expert fact-checker and conflict detector. "
                "Analyze the following evidence gathered from different sources. "
                "Detect if there are any direct contradictions or conflicting claims (e.g. differing refund periods, conflicting execution steps, contradictory numbers). "
                "For each conflict detected, evaluate the source freshness and authority and provide a recommendation. Output in structured format."
            )),
            ("human", "Inspect these evidence items:\n{evidence}")
        ])
        
        chain = prompt | structured_llm
        result = chain.invoke({"evidence": evidence_str})
        
        return [c.dict() for c in result.conflicts if c.conflict_detected]
        
    except Exception as e:
        logger.error(f"LLM Conflict detector failed: {e}. Falling back to rule-based scanner.")
        return rule_based_conflict_detector(evidence_list)
