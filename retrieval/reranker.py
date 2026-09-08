import numpy as np
from typing import List, Tuple, Dict, Any
from database.models import DocumentChunk
from shared.logging.logger import logger

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """
    Computes cosine similarity between two vectors.
    """
    a = np.array(v1)
    b = np.array(v2)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

def rerank_candidates(
    query_text: str,
    query_embedding: List[float],
    candidates: List[Tuple[DocumentChunk, float]],
    top_k: int = 5
) -> List[Tuple[DocumentChunk, float]]:
    """
    Reranks candidate chunks based on a local hybrid formula:
    Rerank Score = 0.7 * Cosine_Similarity(chunk_embedding, query_embedding)
                   + 0.3 * Match_Density(query_words, chunk_content)
    """
    if not candidates:
        return []
        
    query_words = [w.lower().strip() for w in query_text.split() if len(w.strip()) > 2]
    reranked = []
    
    for chunk, rrf_score in candidates:
        # 1. Semantic Similarity
        # If the chunk has no embedding, default to 0
        semantic_score = 0.0
        if chunk.embedding is not None:
            # pgvector library returns list of floats for embedding
            semantic_score = cosine_similarity(chunk.embedding, query_embedding)
            # Normalize to [0, 1] range (cosine similarity is naturally [-1, 1])
            semantic_score = (semantic_score + 1.0) / 2.0
            
        # 2. Match Density
        density_score = 0.0
        if query_words:
            content_lower = chunk.content.lower()
            matches = sum(1 for word in query_words if word in content_lower)
            density_score = matches / len(query_words)
            
        # Compute combined score
        final_score = 0.7 * semantic_score + 0.3 * density_score
        
        # Keep metadata about similarity
        reranked.append((chunk, final_score))
        
    # Sort descending by final score
    reranked.sort(key=lambda x: x[1], reverse=True)
    
    logger.info(f"Reranking complete. Top candidate score: {reranked[0][1]:.4f} if any.")
    return reranked[:top_k]
