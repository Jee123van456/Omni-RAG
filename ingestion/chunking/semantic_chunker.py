import re
from typing import Dict, Any, List
from ingestion.parsing.text_parser import extract_sections, get_section_for_position

def chunk_document(
    document_text: str,
    pages: List[Dict[str, Any]],
    chunk_size_words: int = 250,
    chunk_overlap_words: int = 50
) -> List[Dict[str, Any]]:
    """
    Chunks a document's text using a structure-aware paragraph-based approach.
    Tracks section headings and page numbers spanned by each chunk.
    
    Returns:
        List of Dicts:
        [{
            "chunk_index": int,
            "content": str,
            "metadata": {
                "section": str,
                "pages": List[int],
                "word_count": int
            }
        }]
    """
    # 1. Identify section headings in the full text
    sections = extract_sections(document_text)
    
    # 2. Build map of characters to page numbers
    # To map char indices of document_text to page numbers, we reconstruct the character offsets
    page_offsets = []
    current_offset = 0
    
    # Let's clean pages content and record their start and end offsets in the joint text
    # In file_loader we joined pages using "\n\n--- PAGE BREAK ---\n\n"
    separator = "\n\n--- PAGE BREAK ---\n\n"
    
    for page in pages:
        page_text = page["text"]
        page_num = page["page_number"]
        page_len = len(page_text)
        
        page_offsets.append({
            "page_number": page_num,
            "char_start": current_offset,
            "char_end": current_offset + page_len
        })
        current_offset += page_len + len(separator)

    def get_pages_for_range(start_idx: int, end_idx: int) -> List[int]:
        pages_found = []
        for offset in page_offsets:
            # Overlaps if the range intersects the page range
            if max(start_idx, offset["char_start"]) < min(end_idx, offset["char_end"]):
                pages_found.append(offset["page_number"])
        return pages_found if pages_found else [1]

    # 3. Split the text into logical sentences/paragraphs
    # Paragraphs are split by double newlines or single newlines
    paragraphs = [p for p in re.split(r'\n+', document_text) if p.strip()]
    
    # Store paragraphs along with their character position in the original text
    paragraph_positions = []
    current_search_idx = 0
    for para in paragraphs:
        start_pos = document_text.find(para, current_search_idx)
        if start_pos == -1:
            start_pos = current_search_idx
        end_pos = start_pos + len(para)
        current_search_idx = end_pos
        paragraph_positions.append({
            "text": para,
            "char_start": start_pos,
            "char_end": end_pos,
            "words": para.split()
        })

    chunks = []
    chunk_index = 0
    
    # We iterate paragraphs to build chunks
    i = 0
    n = len(paragraph_positions)
    
    while i < n:
        current_chunk_paras = []
        current_words = 0
        
        # Accumulate paragraphs until we hit the word limit
        start_char = paragraph_positions[i]["char_start"]
        end_char = start_char
        
        j = i
        while j < n and current_words < chunk_size_words:
            para = paragraph_positions[j]
            current_chunk_paras.append(para["text"])
            current_words += len(para["words"])
            end_char = para["char_end"]
            j += 1
            
        chunk_content = "\n\n".join(current_chunk_paras)
        
        # Determine metadata
        spanned_pages = get_pages_for_range(start_char, end_char)
        # Determine section using the midpoint of the chunk
        midpoint = (start_char + end_char) // 2
        section_name = get_section_for_position(midpoint, sections)
        
        chunks.append({
            "chunk_index": chunk_index,
            "content": chunk_content,
            "metadata": {
                "section": section_name,
                "pages": spanned_pages,
                "word_count": current_words
            }
        })
        
        chunk_index += 1
        
        # Move forward based on overlap
        # We need to find how many paragraphs to rewind for overlap
        if j >= n:
            # We reached the end
            break
            
        # Let's count backwards to satisfy overlap_words
        overlap_words_count = 0
        rewind_steps = 0
        for r in range(j - 1, i, -1):
            overlap_words_count += len(paragraph_positions[r]["words"])
            if overlap_words_count > chunk_overlap_words:
                break
            rewind_steps += 1
            
        i = j - rewind_steps
        if i == j: # prevent infinite loop if a paragraph is huge
            i += 1

    return chunks
