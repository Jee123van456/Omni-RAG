from ingestion.chunking.semantic_chunker import chunk_document

def test_chunk_short_document():
    """
    Test that a short document fitting within size limits produces a single chunk.
    """
    text = "This is a short document. It has only one paragraph and fits in a single chunk."
    pages = [{"page_number": 1, "text": text}]
    
    chunks = chunk_document(text, pages, chunk_size_words=100, chunk_overlap_words=10)
    
    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["content"] == text
    assert chunks[0]["metadata"]["pages"] == [1]
    assert chunks[0]["metadata"]["section"] == "General Document"

def test_chunk_long_document_splitting():
    """
    Test that a document split by headers assigns section names correctly
    and spans page numbers correctly.
    """
    # Create text with markdown headers
    text = (
        "# Introduction\n"
        "This is paragraph one in the intro section.\n"
        "It contains multiple sentences and spans pages.\n"
        "# Section two\n"
        "Here is the text in section two which will be placed in a separate chunk."
    )
    pages = [
        {"page_number": 1, "text": "# Introduction\nThis is paragraph one in the intro section.\n"},
        {"page_number": 2, "text": "It contains multiple sentences and spans pages.\n# Section two\nHere is the text in section two which will be placed in a separate chunk."}
    ]
    
    chunks = chunk_document(text, pages, chunk_size_words=10, chunk_overlap_words=2)
    
    # We expect multiple chunks since we set size limit to 10 words
    assert len(chunks) > 1
    
    # Check that first chunk matches Introduction section
    assert chunks[0]["metadata"]["section"] == "# Introduction"
    
    # Check that last chunk matches Section two
    assert chunks[-1]["metadata"]["section"] == "# Section two"
    
    # Check that pages list is recorded
    assert len(chunks[0]["metadata"]["pages"]) >= 1
