from connectors.postgres.postgres_connector import validate_sql_safety

def test_safe_sql_queries():
    """
    Verify that safe read-only SQL statements are allowed.
    """
    assert validate_sql_safety("SELECT * FROM users;") is True
    assert validate_sql_safety("SELECT email, created_at FROM users WHERE id = 1;") is True
    assert validate_sql_safety("SELECT COUNT(*) FROM sources;") is True
    assert validate_sql_safety("WITH active_sources AS (SELECT * FROM sources WHERE status='active') SELECT * FROM active_sources;") is True
    assert validate_sql_safety("EXPLAIN SELECT * FROM documents;") is True
    assert validate_sql_safety("SELECT * FROM documents UNION SELECT * FROM documents;") is True

def test_destructive_sql_blocked():
    """
    Verify that modifying or destructive SQL statements are blocked.
    """
    # Standard modifications
    assert validate_sql_safety("INSERT INTO users (email) VALUES ('hacked@omnirag.io');") is False
    assert validate_sql_safety("UPDATE sources SET status = 'error' WHERE id = 1;") is False
    assert validate_sql_safety("DELETE FROM documents WHERE id = 1;") is False
    
    # Schema modifications
    assert validate_sql_safety("DROP TABLE document_chunks;") is False
    assert validate_sql_safety("ALTER TABLE users ADD COLUMN password VARCHAR;") is False
    assert validate_sql_safety("TRUNCATE TABLE ingestion_jobs;") is False
    assert validate_sql_safety("CREATE TABLE temp_table (id INT);") is False
    
    # Privileges
    assert validate_sql_safety("GRANT ALL PRIVILEGES ON ALL TABLES TO PUBLIC;") is False
    assert validate_sql_safety("REVOKE SELECT ON users FROM read_only_role;") is False

def test_sql_injection_and_nested_writes_blocked():
    """
    Verify that SQL injection and nested modifying queries are caught by the AST walker.
    """
    # Nested writing
    assert validate_sql_safety("SELECT * FROM (INSERT INTO users (email) VALUES ('bad@evil.com') RETURNING id) AS t;") is False
    # Semicolon stacking writes
    assert validate_sql_safety("SELECT * FROM sources; DROP TABLE users;") is False
    # Write into select
    assert validate_sql_safety("SELECT * INTO new_table FROM sources;") is False
