from typing import List, Optional
from pydantic import BaseModel, Field
from shared.config.settings import settings
from shared.logging.logger import logger
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

class QueryAnalysis(BaseModel):
    query_type: str = Field(
        description="Classification: DIRECT_LOOKUP, MULTI_SOURCE, STRUCTURED_DATA, CODE_SEARCH, COMPARISON, ANALYSIS, MULTI_HOP, AMBIGUOUS, INSUFFICIENT_INFORMATION"
    )
    intent: str = Field(description="Summary of what the user wants to achieve")
    entities: List[str] = Field(default=[], description="Keywords, proper nouns, or system names mentioned")
    sources: List[str] = Field(
        default=[], 
        description="Target sources. Can contain: 'documents', 'web', 'github', 'postgres'"
    )
    time_range: Optional[str] = Field(None, description="Time filters mentioned (e.g., 'July', 'last week')")
    filters: List[str] = Field(default=[], description="Key-value filters like 'file_path=auth.py'")
    expected_output: str = Field(default="text", description="Expected format: text, table, list, chart")

def rule_based_classify(query: str) -> QueryAnalysis:
    """
    Rule-based regex query analyzer for offline/mock operations.
    """
    query_lower = query.lower()
    
    # Defaults
    q_type = "DIRECT_LOOKUP"
    intent = "Retrieve matching information"
    entities = []
    sources = []
    
    # 1. Detect Structured Database Queries
    db_keywords = ["how many", "count", "average", "orders", "database", "sql", "select", "total number", "metrics"]
    if any(k in query_lower for k in db_keywords):
        q_type = "STRUCTURED_DATA"
        intent = "Query relational structured DB metrics"
        sources.append("postgres")
        
    # 2. Detect Code Queries
    code_keywords = ["code", "function", "class", "repo", "repository", "github", "lines", "implementation", "middleware", "auth.py"]
    if any(k in query_lower for k in code_keywords):
        q_type = "CODE_SEARCH"
        intent = "Locate and analyze code structures in repositories"
        sources.append("github")
        
    # 3. Detect Comparison
    compare_keywords = ["compare", "versus", "vs", "difference", "contrary", "conflict"]
    if any(k in query_lower for k in compare_keywords):
        q_type = "COMPARISON"
        intent = "Compare multiple documents or sources"
        if "postgres" not in sources:
            sources.append("documents")
        if "web" not in sources:
            sources.append("web")
            
    # 4. Extract simple entities
    entity_regex = re_words = ["refund", "order", "auth", "login", "middleware", "api", "jwt"]
    for word in re_words:
        if word in query_lower:
            entities.append(word)
            
    if not sources:
        sources = ["documents"] # default fallback

    return QueryAnalysis(
        query_type=q_type,
        intent=intent,
        entities=entities,
        sources=sources,
        time_range=None,
        filters=[],
        expected_output="text"
    )

def analyze_query(query: str) -> QueryAnalysis:
    """
    Main entry point for Query Analyzer. Combines LLM structured outputs with rule fallback.
    """
    api_key = settings.OPENAI_API_KEY
    if not api_key or api_key == "mock-key" or api_key == "your-openai-api-key":
        return rule_based_classify(query)
        
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=api_key, temperature=0.0)
        structured_llm = llm.with_structured_output(QueryAnalysis)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert query analyzer. Analyze the user's RAG query and classify its intent and target sources."),
            ("human", "{query}")
        ])
        
        chain = prompt | structured_llm
        result = chain.invoke({"query": query})
        return result
    except Exception as e:
        logger.error(f"LLM Query Analyzer failed: {e}. Falling back to rule-based classifier.")
        return rule_based_classify(query)
