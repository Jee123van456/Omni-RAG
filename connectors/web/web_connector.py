import socket
import urllib.parse
import ipaddress
from typing import Dict, Any, List
import requests
from bs4 import BeautifulSoup
import html2text

from shared.logging.logger import logger

def is_private_ip(ip_str: str) -> bool:
    """
    Checks if an IP address belongs to a private, loopback, or link-local range.
    Supports both IPv4 and IPv6 addresses. Protects against SSRF attacks.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private or 
            ip.is_loopback or 
            ip.is_link_local or 
            ip.is_reserved or 
            ip.is_unspecified
        )
    except ValueError:
        return True  # Fail closed for invalid/malformed IP strings

def validate_url_for_ssrf(url: str) -> str:
    """
    Parses a URL, resolves its hostname, and raises ValueError if it points to a private address.
    Auto-prefixes 'http://' if scheme is missing.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
        
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    
    if not hostname:
        raise ValueError("Invalid URL: missing hostname.")
        
    try:
        # Resolve hostname to IPs
        addr_info = socket.getaddrinfo(hostname, None)
        ips = [info[4][0] for info in addr_info]
        
        for ip in ips:
            if is_private_ip(ip):
                raise ValueError(f"SSRF Protection block: URL resolves to private IP address {ip}.")
    except socket.gaierror as e:
        raise ValueError(f"Could not resolve hostname '{hostname}': {e}")
        
    return url

def fetch_and_clean_webpage(url: str, timeout_seconds: int = 10, max_size_bytes: int = 5 * 1024 * 1024) -> Dict[str, Any]:
    """
    Safely retrieves a webpage, strips layout navigation, and outputs cleaned text.
    """
    # 1. SSRF Safety Check & URL Normalization
    url = validate_url_for_ssrf(url)
    
    # 2. Fetch headers first to verify Content-Length
    headers = {"User-Agent": "OmniRAG-Bot/1.0"}
    
    try:
        response = requests.get(url, headers=headers, timeout=timeout_seconds, stream=True)
        response.raise_for_status()
        
        # Check size limits
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_size_bytes:
            raise ValueError(f"Page size exceeds maximum limit of {max_size_bytes} bytes.")
            
        # Download content incrementally
        chunks = []
        downloaded = 0
        for chunk in response.iter_content(chunk_size=8192, decode_unicode=True):
            if chunk:
                chunks.append(chunk)
                downloaded += len(chunk)
                if downloaded > max_size_bytes:
                    raise ValueError(f"Page size exceeds limit during streaming.")
                    
        html_content = "".join(chunks)
        
    except requests.RequestException as e:
        logger.error(f"Web request error: {e}")
        raise RuntimeError(f"Web client failed to retrieve page: {e}")

    # 3. Clean layout boilerplate
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove script, style, header, footer, nav tags
    for tag in soup(["script", "style", "header", "footer", "nav", "aside"]):
        tag.decompose()
        
    title = soup.title.string.strip() if soup.title else "Web Article"
    
    # Extract main text
    # Standard html2text conversion to markdown format preserving headers
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.body_width = 0 # No word wrapping
    
    cleaned_markdown = converter.handle(str(soup))
    
    # Paginate by splitting every 2500 characters
    pages = []
    chars_per_page = 2500
    pages_list = [cleaned_markdown[i:i+chars_per_page] for i in range(0, len(cleaned_markdown), chars_per_page)]
    for i, page_text in enumerate(pages_list):
        pages.append({
            "page_number": i + 1,
            "text": page_text
        })
        
    return {
        "title": title,
        "text": cleaned_markdown,
        "pages": pages,
        "metadata": {
            "url": url,
            "title": title,
            "source_type": "web"
        }
    }
