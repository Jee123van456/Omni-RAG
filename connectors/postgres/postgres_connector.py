import sqlglot
from sqlglot import parse_one, exp
from typing import Dict, Any, List
from sqlalchemy import create_engine, text
from shared.logging.logger import logger

def validate_sql_safety(sql: str) -> bool:
    """
    Parses the query with sqlglot and walks the AST to verify it contains
    only safe read-only operations. Blocks INSERT, UPDATE, DELETE, CREATE, DROP, etc.
    """
    try:
        # Normalize/clean string
        cleaned_sql = sql.strip().rstrip(';')
        
        # Parse statement
        expression = parse_one(cleaned_sql, read="postgres")
        
        # Define forbidden AST expression nodes
        forbidden_nodes = (
            exp.Insert,
            exp.Update,
            exp.Delete,
            exp.Drop,
            exp.Alter,
            exp.Create,
            exp.Into,         # SELECT INTO (which writes tables)
            exp.Command,      # Raw command blocks (GRANT, REVOKE, etc.)
        )
        
        for node in expression.walk():
            if isinstance(node, forbidden_nodes):
                # Allow Command node if it represents an EXPLAIN command
                if isinstance(node, exp.Command):
                    command_text = node.sql("postgres").lower().strip()
                    if command_text.startswith("explain"):
                        continue
                logger.warning(f"SQL AST safety breach: detected forbidden node type {type(node).__name__}")
                return False
                
        # Validate that the root operation is select-based
        allowed_root_classes = (exp.Select, exp.CTE, exp.Union, exp.Subquery)
        is_allowed = (
            isinstance(expression, allowed_root_classes) or 
            type(expression).__name__ == "Explain" or
            (isinstance(expression, exp.Command) and expression.sql("postgres").lower().strip().startswith("explain"))
        )
        
        if not is_allowed:
            logger.warning(f"SQL AST safety breach: root statement type {type(expression).__name__} is not allowed")
            return False
            
        return True
    except Exception as e:
        logger.error(f"SQL validation parse failure: {e}")
        return False

def get_database_schema_info(db_url: str) -> str:
    """
    Queries information_schema to extract tables, columns, and type details.
    """
    engine = create_engine(db_url)
    schema_query = """
        SELECT table_name, column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position;
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(text(schema_query))
            tables_map = {}
            for row in result:
                t_name, c_name, d_type = row[0], row[1], row[2]
                if t_name not in tables_map:
                    tables_map[t_name] = []
                tables_map[t_name].append(f"{c_name} ({d_type})")
                
            schema_str = []
            for t_name, cols in tables_map.items():
                schema_str.append(f"Table: {t_name}\n  Columns: {', '.join(cols)}")
                
            return "\n\n".join(schema_str)
    except Exception as e:
        logger.error(f"Failed to fetch DB schema details: {e}")
        return f"Error retrieving schema details: {str(e)}"

def execute_safe_read_query(db_url: str, sql: str, limit: int = 100, timeout_sec: int = 5) -> List[Dict[str, Any]]:
    """
    Validates safety of the SQL and executes it with row limits and timeouts.
    """
    if not validate_sql_safety(sql):
        raise PermissionError("SQL safety validation failed: Write/Destructive operations are forbidden.")
        
    # Append LIMIT via AST if possible to avoid memory bloat
    try:
        parsed = parse_one(sql, read="postgres")
        if isinstance(parsed, exp.Select):
            # Check if it already has a limit
            if not parsed.args.get("limit"):
                parsed = parsed.limit(limit)
                sql = parsed.sql("postgres")
    except Exception:
        # Fallback to appending LIMIT string if AST parsing failed
        pass

    engine = create_engine(
        db_url,
        connect_args={"options": f"-c statement_timeout={timeout_sec * 1000}"} # Postgres statement timeout in ms
    )
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            rows = []
            
            # Fetch up to the limit explicitly
            for index, row in enumerate(result):
                if index >= limit:
                    break
                rows.append(dict(row._mapping))
                
            return rows
    except Exception as e:
        logger.error(f"SQL Execution failed: {e}")
        raise RuntimeError(f"Database query failed: {str(e)}")
