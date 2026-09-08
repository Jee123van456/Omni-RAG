from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from shared.config.settings import settings

# Create synchronous engine
engine = create_engine(settings.DATABASE_URL)

# Create session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base
Base = declarative_base()

# DB dependency for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
