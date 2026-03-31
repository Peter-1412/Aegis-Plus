from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool


_GUIDE_CACHE: str | None = None
_GUIDE_PATH: str | None = None


def _find_log_guide() -> Path | None:
    here = Path(__file__).resolve()
    # Expecting: services/ops-service/app/tools/log_guide_tool.py
    # Repo root: d:\Code\DevOps\Aegis
    repo_root = here.parents[4] if len(here.parents) >= 5 else None
    if repo_root:
        candidate = repo_root / "docs" / "monitoring" / "log.md"
        if candidate.exists():
            return candidate
    
    # Fallback for different deployment structures
    # Maybe relative to app root?
    app_dir = here.parents[1]
    candidate = app_dir / "data" / "log.md"
    if candidate.exists():
        return candidate
        
    return None


def _load_guide() -> str:
    global _GUIDE_CACHE, _GUIDE_PATH
    if _GUIDE_CACHE is not None:
        return _GUIDE_CACHE
    
    path = _find_log_guide()
    if not path:
        return ""
    
    _GUIDE_PATH = str(path)
    try:
        content = path.read_text(encoding="utf-8")
        _GUIDE_CACHE = content
        return content
    except Exception:
        return ""


@tool(
    "log_query_guide_lookup",
    description="查询日志查询指南 (LogQL)，获取如何查询特定服务日志的示例和技巧。支持按关键字过滤。",
)
def log_query_guide_lookup(keyword: str | None = None) -> str:
    content = _load_guide()
    if not content:
        return "未找到日志查询指南文件 (docs/monitoring/log.md)。"
    
    if not keyword:
        return content
        
    # Simple keyword filtering: return paragraphs containing the keyword
    lines = content.split('\n')
    filtered_lines = []
    capture = False
    
    keyword_lower = keyword.lower()
    
    for line in lines:
        if line.startswith('#'):
            # Always keep headers if they match or if we are in a matching section
            if keyword_lower in line.lower():
                capture = True
                filtered_lines.append(line)
            else:
                capture = False # Reset on new header unless it's a sub-header of a match? 
                # Let's keep it simple: if header matches, keep following lines. 
                # If a paragraph matches, keep it.
        
        if keyword_lower in line.lower():
            filtered_lines.append(line)
        elif capture:
             filtered_lines.append(line)
             
    if not filtered_lines:
        return f"在指南中未找到包含 '{keyword}' 的内容。建议不带关键字调用以查看全文。"
        
    return "\n".join(filtered_lines)
