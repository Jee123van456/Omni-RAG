from typing import List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_
from database.models import DocumentChunk, Document
from shared.logging.logger import logger

def query_lexical_search(
    db: Session,
    query_text: str,
    top_k: int = 10,
    source_ids: List[int] = None
) -> List[Tuple[DocumentChunk, float]]:
    """
    Performs lexical retrieval using PostgreSQL full-text search (tsvector + ts_rank).
    Falls back to ILIKE matching if full-text search fails.
    """
    try:
        # PostgreSQL full-text search ranking
        # ts_rank_cd computes density-based ranking of terms
        ts_vector = func.to_tsvector('english', DocumentChunk.content)
        ts_query = func.plainto_tsquery('english', query_text)
        rank_expr = func.ts_rank_cd(ts_vector, ts_query)
        
        stmt = select(DocumentChunk, rank_expr).join(Document)
        
        if source_ids:
            stmt = stmt.where(Document.source_id.in_(source_ids))
            
        # We filter where rank > 0 to ensure some keywords matched
        stmt = stmt.where(ts_vector.op('@@')(ts_query))
        stmt = stmt.order_by(rank_expr.desc()).limit(top_k)
        
        results = db.execute(stmt).all()
        
        ranked_chunks = []
        for chunk, score in results:
            ranked_chunks.append((chunk, float(score or 0.0)))
            
        if ranked_chunks:
            return ranked_chunks
            
    except Exception as e:
        logger.warning(f"Postgres full-text search unavailable ({e}). Falling back to ILIKE lexical search.")

    # Fallback: keyword ILIKE search
    try:
        words = [w.strip() for w in query_text.split() if w.strip()]
        if not words:
            return []
            
        stmt = select(DocumentChunk).join(Document)
        if source_ids:
            stmt = stmt.where(Document.source_id.in_(source_ids))
            
        # Match chunks containing ANY of the search terms
        ilike_filters = [DocumentChunk.content.ilike(f"%{word}%") for word in words]
        stmt = stmt.where(or_(*ilike_filters)).limit(top_k)
        
        results = db.execute(stmt).scalars().all()
        
        # Rank by matching keywords density
        ranked_chunks = []
        for chunk in results:
            match_count = sum(1 for word in words if word.lower() in chunk.content.lower())
            score = match_count / len(words)
            ranked_chunks.append((chunk, score))
            
        # Sort by match density descending
        ranked_chunks.sort(key=lambda x: x[1], reverse=True)
        return ranked_chunks[:top_k]
        
    except Exception as ex:
        logger.error(f"Fallback ILIKE search failed: {ex}")
        return []
