from typing import List, Dict, Any
from shared.logging.logger import logger

def route_query_sources(query: str, query_type: str, sources_override: List[str] = None) -> List[Dict[str, Any]]:
    """
    Decides which connectors should handle the query and reformulates the search string for each.
    Returns:
        List of dicts: [{"source": str, "reason": str, "priority": int, "query": str, "filters": dict}]
    """
    routes = []
    
    # If sources are explicitly listed by the query analyzer, use them
    target_sources = sources_override if sources_override else []
    
    if not target_sources:
        # Heuristics based on query type
        if query_type == "STRUCTURED_DATA":
            target_sources = ["postgres"]
        elif query_type == "CODE_SEARCH":
            target_sources = ["github"]
        elif query_type == "COMPARISON":
            target_sources = ["documents", "web"]
        else:
            target_sources = ["documents"]

    for src in target_sources:
        reason = f"Routing query to {src} connector because intent matches {query_type} pattern."
        priority = 1
        
        # Reformulate queries depending on the source type
        # E.g. Removing SQL stopwords for DB, keeping search terms clean
        sub_query = query
        filters = {}
        
        if src == "postgres":
            # Provide schemas hint instructions in plan
            priority = 2
            reason = "SQL Query Ingestion requested. Routing to PostgreSQL Read-only schema discovery."
        elif src == "github":
            priority = 2
            reason = "AST Structural Ingest requested. Routing to Code Repository Connector."
        elif src == "web":
            priority = 1
            reason = "External web context requested. Routing to crawling pipeline."
            
        routes.append({
            "source": src,
            "reason": reason,
            "priority": priority,
            "query": sub_query,
            "filters": filters
        })

    logger.info(f"Router mapped '{query}' (type: {query_type}) to sources: {[r['source'] for r in routes]}")
    return routes
