import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from shared.config.settings import settings
from database.db import Base, get_db
from database.models import all_models
from apps.api.main import app

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """
    Ensures that the test database 'omnirag_test' exists, 
    installs the pgvector extension, and creates all tables.
    """
    # Connect to the main database first to create the test database
    main_engine = create_engine(settings.DATABASE_URL, isolation_level="AUTOCOMMIT")
    
    with main_engine.connect() as conn:
        # Check if the test database already exists
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'omnirag_test'")
        ).scalar()
        
        if not exists:
            conn.execute(text("CREATE DATABASE omnirag_test"))
            
    # Connect to the test database and enable the vector extension
    test_engine = create_engine(settings.TEST_DATABASE_URL)
    with test_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
        
    # Create all tables in the test database
    Base.metadata.create_all(bind=test_engine)
    
    yield
    
    # Tear down - drop all tables from the test database
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    """
    Yields a clean SQLAlchemy session connected to the test database.
    """
    test_engine = create_engine(settings.TEST_DATABASE_URL)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = TestingSessionLocal()
    try:
        # Clean data before each test
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session):
    """
    Yields a FastAPI TestClient with overridden DB dependency pointing to the test DB.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
            
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
