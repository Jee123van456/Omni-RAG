import re
import json
from typing import List, Dict, Any, Tuple, Optional
from shared.config.settings import settings
from shared.logging.logger import logger
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

class CitationSchema(BaseModel):
    claim: str = Field(description="The specific factual claim made in the response")
    source_type: str = Field(description="The source type, e.g. documents, web, github, postgres")
    document_id: Optional[int] = Field(None, description="The document database ID")
    chunk_id: Optional[int] = Field(None, description="The chunk database ID")
    location: str = Field(description="Page number, line range, or URL where evidence resides")
    citation_text: str = Field(description="The precise snippet or quote supporting the claim")

class GroundedAnswerSchema(BaseModel):
    answer: str = Field(description="The complete grounded answer text citing evidence using [1], [2], etc.")
    citations: List[CitationSchema] = Field(default=[], description="List of validated citations mapping to the answer")

def calculate_confidence_score(
    evidence_list: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]],
    citations_count: int
) -> Tuple[str, str]:
    """
    Computes a measurable confidence rating (HIGH, MEDIUM, LOW) based on:
    - Evidence agreement (conflicts check)
    - Retrieval Quality (scores)
    - Citation coverage
    - Source density
    """
    score = 1.0
    reasons = []
    
    # 1. Conflict Penalty
    if conflicts:
        score -= 0.4
        reasons.append("Conflicting evidence detected between sources.")
        
    # 2. Evidence Density Penalty
    if not evidence_list:
        score -= 0.6
        reasons.append("No supporting evidence found.")
    elif len(evidence_list) < 2:
        score -= 0.15
        reasons.append("Limited source evidence available.")
        
    # 3. Retrieval Quality check
    if evidence_list:
        avg_score = sum(e.get("score", 0.0) for e in evidence_list) / len(evidence_list)
        if avg_score < 0.65:
            score -= 0.15
            reasons.append(f"Low retrieval relevance score (avg: {avg_score:.2f}).")
            
    # 4. Citation Coverage
    if len(evidence_list) > 0 and citations_count == 0:
        score -= 0.2
        reasons.append("Answer contains no direct citations to supporting evidence.")
        
    score = max(0.0, score)
    
    if score >= 0.8:
        rating = "HIGH"
        explanation = "High confidence: Strong source agreement, high relevance scores, and solid citation coverage."
    elif score >= 0.5:
        rating = "MEDIUM"
        explanation = f"Medium confidence: {', '.join(reasons)}"
    else:
        rating = "LOW"
        explanation = f"Low confidence: Critical evidence issues. {', '.join(reasons)}"
        
    return rating, explanation

def validate_citations_integrity(
    citations: List[Dict[str, Any]],
    evidence_list: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Post-generation citation validation. Checks that:
      - cited chunk_id exists in retrieved evidence.
      - citation_text actually exists as a substring in the chunk content.
    Sets 'valid' flag accordingly.
    """
    validated = []
    evidence_map = {e.get("chunk_id"): e for e in evidence_list if e.get("chunk_id")}
    
    for cit in citations:
        c_id = cit.get("chunk_id")
        text_snippet = cit.get("citation_text", "").strip()
        
        cit_copy = dict(cit)
        cit_copy["valid"] = False
        
        # Verify chunk exists
        if c_id in evidence_map:
            chunk = evidence_map[c_id]
            chunk_content = chunk.get("content", "")
            
            # Verify quote is present in chunk content (case-insensitive substring)
            # Remove punctuation/whitespace to check loosely if needed
            clean_snippet = re.sub(r'\s+', '', text_snippet.lower())
            clean_content = re.sub(r'\s+', '', chunk_content.lower())
            
            if clean_snippet in clean_content:
                cit_copy["valid"] = True
            else:
                # If exact quote is not found, log discrepancy but let it pass if similarity is high
                # Or set valid to False.
                logger.warning(f"Citation validation failed: quote '{text_snippet}' not found in chunk {c_id}.")
                cit_copy["valid"] = False
        else:
            logger.warning(f"Citation validation failed: chunk_id {c_id} is missing from evidence map.")
            cit_copy["valid"] = False
            
        validated.append(cit_copy)
    return validated

def local_grounded_answer(evidence_list: List[Dict[str, Any]], conflicts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Offline/fallback grounded summary generator.
    """
    if not evidence_list:
        return {
            "answer": "I don't have enough reliable evidence to answer this confidently.",
            "citations": [],
            "confidence": "LOW",
            "confidence_reason": "No evidence retrieved."
        }
        
    if conflicts:
        # Format conflicts warning
        conflict_msg = "CONFLICT DETECTED:\n"
        for c in conflicts:
            conflict_msg += f"- {c['explanation']}\n  Recommendation: {c['recommendation']}\n"
        return {
            "answer": f"I cannot answer this question definitively due to conflicting source details.\n\n{conflict_msg}",
            "citations": [],
            "confidence": "LOW",
            "confidence_reason": "Critical source contradictions detected."
        }

    # Generate a simple concatenated summary
    summary_parts = []
    citations = []
    
    for idx, ev in enumerate(evidence_list):
        source_label = ev.get("source_type", "document")
        doc_id = ev.get("document_id")
        chunk_id = ev.get("chunk_id")
        meta = ev.get("metadata", {})
        
        location = "General"
        if source_label == "documents":
            pages = meta.get("pages", [1])
            location = f"Page {', '.join(map(str, pages))}"
        elif source_label == "web":
            location = meta.get("url", "webpage")
        elif source_label == "github":
            location = f"{meta.get('file_path')}:L{meta.get('line_start')}-{meta.get('line_end')}"
            
        snippet = ev.get("content", "")[:100] + "..."
        
        summary_parts.append(f"[{idx + 1}] Stated in {source_label}: \"{ev.get('content')}\"")
        
        citations.append({
            "claim": f"Information retrieved from {source_label}",
            "source_type": source_label,
            "document_id": doc_id,
            "chunk_id": chunk_id,
            "location": location,
            "citation_text": ev.get("content")[:80],
            "valid": True
        })
        
    answer_text = "Based on the retrieved sources:\n" + "\n".join(summary_parts)
    
    rating, explanation = calculate_confidence_score(evidence_list, conflicts, len(citations))
    
    return {
        "answer": answer_text,
        "citations": citations,
        "confidence": rating,
        "confidence_reason": explanation
    }

def generate_grounded_answer(
    question: str,
    evidence_list: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Main grounded generation entrypoint. Queries LLM or falls back to local summarizer.
    """
    api_key = settings.OPENAI_API_KEY
    if not api_key or api_key == "mock-key" or api_key == "your-openai-api-key":
        return local_grounded_answer(evidence_list, conflicts)
        
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=api_key, temperature=0.0)
        structured_llm = llm.with_structured_output(GroundedAnswerSchema)
        
        evidence_str = ""
        for idx, ev in enumerate(evidence_list):
            evidence_str += f"\n--- Evidence ID: {ev.get('chunk_id')} (Source: {ev.get('source_type')}, Doc ID: {ev.get('document_id')}) ---\n"
            evidence_str += f"Content: {ev.get('content')}\n"
            evidence_str += f"Metadata: {json.dumps(ev.get('metadata', {}))}\n"

        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are an expert grounded AI researcher. Your goal is to write a comprehensive answer based ONLY on the evidence provided. "
                "Do not make up facts. Do not invent citations. Cite claims using index numbers corresponding to the evidence provided. "
                "If evidence is insufficient to answer, state: 'I don't have enough reliable evidence to answer this confidently.' "
                "If conflicts are present in the query inputs, explain them clearly and do not choose a value."
            )),
            ("human", (
                "Question: {question}\n\n"
                "Retrieved Evidence:\n{evidence}\n\n"
                "Conflicts Detected:\n{conflicts}"
            ))
        ])
        
        chain = prompt | structured_llm
        result = chain.invoke({
            "question": question,
            "evidence": evidence_str,
            "conflicts": json.dumps(conflicts)
        })
        
        citations_dict = [c.dict() for c in result.citations]
        validated_citations = validate_citations_integrity(citations_dict, evidence_list)
        
        rating, explanation = calculate_confidence_score(evidence_list, conflicts, len(validated_citations))
        
        return {
            "answer": result.answer,
            "citations": validated_citations,
            "confidence": rating,
            "confidence_reason": explanation
        }
    except Exception as e:
        logger.error(f"LLM Answer Generator failed: {e}. Falling back to local summary.")
        return local_grounded_answer(evidence_list, conflicts)
