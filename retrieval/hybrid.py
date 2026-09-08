from typing import List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from database.models import DocumentChunk
from retrieval.vector import query_vector_search
from retrieval.lexical import query_lexical_search
from shared.logging.logger import logger

def reciprocal_rank_fusion(
    dense_results: List[Tuple[DocumentChunk, float]],
    lexical_results: List[Tuple[DocumentChunk, float]],
    rrf_k: int = 60
) -> List[Tuple[DocumentChunk, float]]:
    """
    Fuses two lists of ranked chunks using the Reciprocal Rank Fusion (RRF) algorithm.
    """
    rrf_scores = {} # type: Dict[int, float]
    chunk_map = {}  # type: Dict[int, DocumentChunk]
    
    # Process dense search rankings
    for rank, (chunk, _) in enumerate(dense_results):
        c_id = chunk.id
        chunk_map[c_id] = chunk
        # RRF formula: 1.0 / (K + rank)
        rrf_scores[c_id] = rrf_scores.get(c_id, 0.0) + (1.0 / (rrf_k + (rank + 1)))
        
    # Process lexical search rankings
    for rank, (chunk, _) in enumerate(lexical_results):
        c_id = chunk.id
        chunk_map[c_id] = chunk
        rrf_scores[c_id] = rrf_scores.get(c_id, 0.0) + (1.0 / (rrf_k + (rank + 1)))
        
    # Sort chunks descending by RRF score
    sorted_scores = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)
    
    fused_results = []
    for chunk_id, score in sorted_scores:
        fused_results.append((chunk_map[chunk_id], score))
        
    return fused_results

def query_hybrid_search(
    db: Session,
    query_text: str,
    query_embedding: List[float],
    top_k: int = 5,
    source_ids: List[int] = None,
    rrf_k: int = 60
) -> List[Tuple[DocumentChunk, float]]:
    """
    Runs vector and lexical search, fuses them with RRF, and returns the top_k.
    """
    # 1. Fetch dense candidates (fetch top_k * 3 candidates to ensure robust fusion)
    dense_candidates = query_vector_search(db, query_embedding, top_k=top_k * 3, source_ids=source_ids)
    
    # 2. Fetch lexical candidates
    lexical_candidates = query_lexical_search(db, query_text, top_k=top_k * 3, source_ids=source_ids)
    
    # 3. Fuse candidates using Reciprocal Rank Fusion
    fused_results = reciprocal_rank_fusion(dense_candidates, lexical_candidates, rrf_k=rrf_k)
    
    logger.info(f"Hybrid retrieval complete: {len(dense_candidates)} dense, {len(lexical_candidates)} lexical candidates fused to {len(fused_results)} unique items.")
    
    return fused_results[:top_k]
