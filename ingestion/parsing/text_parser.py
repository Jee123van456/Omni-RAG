import re
from typing import Dict, Any, List

def clean_text(text: str) -> str:
    """
    Cleans raw text by normalizing whitespaces and removes redundant break lines.
    """
    if not text:
        return ""
    # Normalize space characters
    text = re.sub(r'[ \t]+', ' ', text)
    # Normalize multiple line breaks to maximum of two
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def extract_sections(text: str) -> List[Dict[str, Any]]:
    """
    Attempts to identify document sections based on Markdown headers or capitalized headings.
    Returns:
        List of dicts: [{"heading": str, "char_start": int, "char_end": int}]
    """
    sections = []
    # Match markdown headings: e.g. # Header 1, ## Header 2
    md_heading_regex = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    
    # Also fallback: lines that look like "Section X" or "Chapter Y"
    section_fallback_regex = re.compile(r'^(Section \d+|Chapter \d+|[A-Z\s]{5,100})$', re.MULTILINE)
    
    matches = list(md_heading_regex.finditer(text))
    if not matches:
        matches = list(section_fallback_regex.finditer(text))
        
    for i, match in enumerate(matches):
        heading = match.group(0).strip()
        start = match.start()
        
        # End of this section is start of next section, or end of text
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        
        sections.append({
            "heading": heading,
            "char_start": start,
            "char_end": end
        })
        
    if not sections:
        # Default single section
        sections.append({
            "heading": "General Document",
            "char_start": 0,
            "char_end": len(text)
        })
        
    return sections

def get_section_for_position(char_index: int, sections: List[Dict[str, Any]]) -> str:
    """
    Returns the heading of the section containing the char_index.
    """
    for sec in sections:
        if sec["char_start"] <= char_index < sec["char_end"]:
            return sec["heading"]
    return "General Document"
