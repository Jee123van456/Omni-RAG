import os
import ast
from typing import Dict, Any, List
from shared.logging.logger import logger

def get_file_language(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript-react",
        ".jsx": "javascript-react",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c-header",
        ".sh": "bash",
        ".json": "json",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".md": "markdown"
    }
    return mapping.get(ext, "text")

class PythonASTChunker(ast.NodeVisitor):
    """
    AST Visitor that finds class and function definitions, 
    recording their names, content, and exact line ranges.
    """
    def __init__(self, source_code: str):
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.chunks = []
        self.current_class = None

    def visit_ClassDef(self, node: ast.ClassDef):
        # Record class definition
        start_line = node.lineno
        # End line is the maximum lineno of all children
        end_line = max(
            [child.lineno for child in ast.walk(node) if hasattr(child, "lineno")] + [start_line]
        )
        
        class_content = "\n".join(self.lines[start_line - 1 : end_line])
        self.chunks.append({
            "name": node.name,
            "type": "class",
            "line_start": start_line,
            "line_end": end_line,
            "content": class_content
        })
        
        # Visit children
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        start_line = node.lineno
        end_line = max(
            [child.lineno for child in ast.walk(node) if hasattr(child, "lineno")] + [start_line]
        )
        
        func_content = "\n".join(self.lines[start_line - 1 : end_line])
        self.chunks.append({
            "name": f"{self.current_class}.{node.name}" if self.current_class else node.name,
            "type": "function",
            "line_start": start_line,
            "line_end": end_line,
            "content": func_content
        })
        self.generic_visit(node)

def chunk_code_file(filepath: str, relative_path: str, repo_name: str, branch: str, commit_sha: str) -> List[Dict[str, Any]]:
    """
    Chunks a single code file. If Python, uses AST to chunk structures.
    Otherwise, chunks every 50 lines.
    """
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
        
    language = get_file_language(filepath)
    file_lines = content.splitlines()
    chunks = []
    
    # Python AST Chunking
    if language == "python":
        try:
            tree = ast.parse(content)
            visitor = PythonASTChunker(content)
            visitor.visit(tree)
            
            # Map Visitor chunks to RAG chunks
            for idx, ast_chunk in enumerate(visitor.chunks):
                chunks.append({
                    "chunk_index": idx,
                    "content": f"# Code Section: {ast_chunk['name']} ({ast_chunk['type']})\n{ast_chunk['content']}",
                    "metadata": {
                        "repository": repo_name,
                        "branch": branch,
                        "commit_sha": commit_sha,
                        "file_path": relative_path,
                        "language": "python",
                        "line_start": ast_chunk["line_start"],
                        "line_end": ast_chunk["line_end"]
                    }
                })
        except Exception:
            # Fallback to line-based chunking on AST parse error
            pass

    # Fallback / Non-Python Line-based chunking
    if not chunks:
        lines_per_chunk = 50
        overlap_lines = 10
        total_lines = len(file_lines)
        
        i = 0
        chunk_idx = 0
        while i < total_lines:
            end_i = min(i + lines_per_chunk, total_lines)
            chunk_content = "\n".join(file_lines[i:end_i])
            
            chunks.append({
                "chunk_index": chunk_idx,
                "content": chunk_content,
                "metadata": {
                    "repository": repo_name,
                    "branch": branch,
                    "commit_sha": commit_sha,
                    "file_path": relative_path,
                    "language": language,
                    "line_start": i + 1,
                    "line_end": end_i
                }
            })
            
            chunk_idx += 1
            if end_i == total_lines:
                break
            i += lines_per_chunk - overlap_lines
            
    return chunks

import tempfile
import shutil
import subprocess

def scan_repository_directory(
    repo_path: str,
    repo_name: str = "custom-repo",
    branch: str = "main",
    commit_sha: str = "b6873ca94d1f2e482ad500fe32b07e27"
) -> List[Dict[str, Any]]:
    """
    Recursively scans a local or remote Git repository directory and returns code chunks mapped with rich metadata.
    Clones remote URLs (http://, https://, git@) to a temporary directory.
    """
    temp_dir = None
    target_scan_path = repo_path
    
    is_remote = repo_path.startswith(("http://", "https://", "git@")) or ("github.com" in repo_path and not os.path.exists(repo_path))
    if is_remote:
        git_url = repo_path
        if not git_url.startswith(("http://", "https://", "git@")):
            git_url = f"https://{git_url}"
            
        temp_dir = tempfile.mkdtemp(prefix="github_repo_")
        target_scan_path = temp_dir
        
        cloned = False
        try:
            clone_cmd = ["git", "clone", "--depth", "1", git_url, temp_dir]
            if branch and branch != "main":
                clone_cmd.extend(["-b", branch])
            subprocess.run(clone_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            cloned = True
        except Exception as e:
            logger.warning(f"git clone failed ({e}), attempting zip archive download fallback...")

        if not cloned:
            import urllib.request
            import zipfile
            import io
            
            # Parse owner and repo from URL
            clean_url = git_url.rstrip("/").removesuffix(".git")
            parts = clean_url.split("/")
            if len(parts) >= 2:
                owner, repo = parts[-2], parts[-1]
                zip_urls = [
                    f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}",
                    f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/master",
                    f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/main"
                ]
                downloaded = False
                for zurl in zip_urls:
                    try:
                        req = urllib.request.Request(zurl, headers={"User-Agent": "OmniRAG-Bot/1.0"})
                        with urllib.request.urlopen(req, timeout=15) as resp:
                            zf = zipfile.ZipFile(io.BytesIO(resp.read()))
                            zf.extractall(temp_dir)
                            downloaded = True
                            break
                    except Exception:
                        continue
                if not downloaded:
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    raise ValueError(f"Failed to clone or download repository from {repo_path}")

    all_chunks = []
    exclude_dirs = {".git", "node_modules", "venv", "__pycache__", "build", "dist", ".next"}
    
    try:
        if not os.path.exists(target_scan_path):
            raise FileNotFoundError(f"Repository directory does not exist: {target_scan_path}")
            
        for root, dirs, files in os.walk(target_scan_path):
            # Exclude directories in-place
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, target_scan_path)
                
                # Skip binary files
                if file.endswith((".png", ".jpg", ".jpeg", ".ico", ".gif", ".pdf", ".pyc", ".db", ".zip", ".tar", ".gz", ".whl")):
                    continue
                    
                try:
                    chunks = chunk_code_file(file_path, rel_path, repo_name, branch, commit_sha)
                    all_chunks.extend(chunks)
                except Exception as e:
                    logger.error(f"Failed to chunk repository file {rel_path}: {e}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    return all_chunks
