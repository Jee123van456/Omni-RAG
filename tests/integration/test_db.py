from database.models import User, Source, Document, DocumentChunk

def test_database_crud_operations(db_session):
    """
    Test creating, writing, and retrieving basic models in PostgreSQL.
    Also verifies pgvector data persistence.
    """
    # 1. Create a user
    user = User(email="test_user@omnirag.io")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    assert user.id is not None
    assert user.email == "test_user@omnirag.io"
    
    # 2. Create a source
    source = Source(
        type="documents", 
        name="Internal Policy Documents",
        configuration={"scan_interval": 3600}
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    
    assert source.id is not None
    assert source.type == "documents"
    assert source.configuration["scan_interval"] == 3600
    
    # 3. Create a document referencing the source
    doc = Document(
        source_id=source.id,
        title="Refund Policy v2",
        uri="file:///docs/refund_policy_v2.pdf",
        content_hash="d3b07384d113edec49eaa6238ad5ff00"
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    
    assert doc.id is not None
    assert doc.source_id == source.id
    assert doc.content_hash == "d3b07384d113edec49eaa6238ad5ff00"
    
    # 4. Create a document chunk referencing the document with a mock vector embedding
    mock_vector = [0.015] * 1536  # Mock OpenAI dimension (1536 floats)
    chunk = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        content="Our refund window is 30 days from purchase.",
        embedding=mock_vector,
        metadata_json={"page": 1, "section": "Core Policies"},
        token_count=12
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)
    
    assert chunk.id is not None
    assert chunk.document_id == doc.id
    assert chunk.chunk_index == 0
    assert chunk.token_count == 12
    assert len(chunk.embedding) == 1536
    assert abs(chunk.embedding[0] - 0.015) < 1e-6
    assert chunk.metadata_json["section"] == "Core Policies"
