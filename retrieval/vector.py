from typing import List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from database.models import DocumentChunk, Document
from shared.logging.logger import logger

def query_vector_search(
    db: Session,
    query_embedding: List[float],
    top_k: int = 10,
    source_ids: List[int] = None
) -> List[Tuple[DocumentChunk, float]]:
    """
    Performs dense vector retrieval using pgvector cosine distance.
    Returns:
        List of Tuples (DocumentChunk, similarity_score)
    """
    try:
        # Distance operator from pgvector. 
        # cosine_distance is 1 - cosine_similarity. Range: [0, 2]
        # Querying with distance operator and sorting ascending
        distance_expr = DocumentChunk.embedding.cosine_distance(query_embedding)
        
        stmt = select(DocumentChunk, distance_expr).join(Document)
        
        if source_ids:
            stmt = stmt.where(Document.source_id.in_(source_ids))
            
        stmt = stmt.order_by(distance_expr).limit(top_k)
        
        results = db.execute(stmt).all()
        
        ranked_chunks = []
        for chunk, distance in results:
            if distance is None:
                distance = 1.0
            # Convert cosine distance to a similarity score [0, 1] where 1 is identical
            score = float(1.0 - (distance / 2.0))
            ranked_chunks.append((chunk, score))
            
        return ranked_chunks
    except Exception as e:
        logger.error(f"Vector search execution failed: {e}")
        return []
