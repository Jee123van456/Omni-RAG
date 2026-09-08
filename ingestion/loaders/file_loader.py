import os
from typing import Dict, Any, List
import pypdf
import docx

def extract_file_content(file_path: str, file_type: str) -> Dict[str, Any]:
    """
    Extracts text and page-level structures from PDF, DOCX, TXT, and Markdown files.
    Returns:
        Dict containing:
            - "text": full extracted text (joined)
            - "pages": list of dicts: [{"page_number": int, "text": str}]
            - "metadata": dict of file properties (file size, filename, page count)
    """
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    
    result = {
        "text": "",
        "pages": [],
        "metadata": {
            "filename": filename,
            "file_size": file_size,
            "file_type": file_type
        }
    }

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if file_type == "pdf":
        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            num_pages = len(reader.pages)
            result["metadata"]["page_count"] = num_pages
            
            full_text_list = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                result["pages"].append({
                    "page_number": i + 1,
                    "text": page_text
                })
                full_text_list.append(page_text)
            result["text"] = "\n\n--- PAGE BREAK ---\n\n".join(full_text_list)

    elif file_type == "docx":
        doc = docx.Document(file_path)
        full_text_list = []
        # docx has no strict "pages" concept, so we treat paragraphs or groups as pseudo-pages
        # For simplicity, we chunk it into pages every 500 words
        current_page_text = []
        word_count = 0
        page_num = 1
        
        for para in doc.paragraphs:
            para_text = para.text
            if not para_text.strip():
                continue
            current_page_text.append(para_text)
            word_count += len(para_text.split())
            
            if word_count >= 400:
                page_content = "\n".join(current_page_text)
                result["pages"].append({
                    "page_number": page_num,
                    "text": page_content
                })
                full_text_list.append(page_content)
                current_page_text = []
                word_count = 0
                page_num += 1
                
        # Append remaining paragraphs
        if current_page_text:
            page_content = "\n".join(current_page_text)
            result["pages"].append({
                "page_number": page_num,
                "text": page_content
            })
            full_text_list.append(page_content)
            
        result["text"] = "\n\n".join(full_text_list)
        result["metadata"]["page_count"] = len(result["pages"])

    elif file_type in ["txt", "md", "markdown"]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
            
        result["text"] = text
        # For plain text files, paginate every 2000 characters
        chars_per_page = 2000
        pages_list = [text[i:i+chars_per_page] for i in range(0, len(text), chars_per_page)]
        
        for i, page_text in enumerate(pages_list):
            result["pages"].append({
                "page_number": i + 1,
                "text": page_text
            })
            
        result["metadata"]["page_count"] = len(pages_list)
        
    else:
        raise ValueError(f"Unsupported file type: {file_type}")

    return result
