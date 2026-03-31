from __future__ import annotations

import logging
from pathlib import Path
from langchain_core.tools import tool

_SKILLS_CACHE: dict[str, str] = {}

def _load_skills():
    global _SKILLS_CACHE
    if _SKILLS_CACHE:
        return _SKILLS_CACHE
    
    here = Path(__file__).resolve()
    # Expecting: services/ops-service/app/tools/skill_tool.py
    # Skills dir: services/ops-service/app/skills/
    # 在 Docker 容器中，代码位于 /app/app/tools/skill_tool.py
    # 所以 skills 目录应该是 /app/app/skills/
    # 路径解析：here 是 /app/app/tools/skill_tool.py
    # here.parent 是 /app/app/tools/
    # here.parent.parent 是 /app/app/
    # here.parent.parent / "skills" 是 /app/app/skills/
    skills_dir = here.parent.parent / "skills"
    
    if not skills_dir.exists():
        logging.warning("skills directory not found: %s", skills_dir)
        # Fallback: try to find skills dir relative to cwd
        cwd = Path.cwd()
        fallback_dir = cwd / "app" / "skills"
        if fallback_dir.exists():
            logging.info("found skills directory at fallback path: %s", fallback_dir)
            skills_dir = fallback_dir
        else:
            return {}
        
    for path in skills_dir.glob("*.md"):
        try:
            content = path.read_text(encoding="utf-8")
            # Use filename (without extension) as skill name
            skill_name = path.stem
            _SKILLS_CACHE[skill_name] = content
        except Exception as e:
            logging.warning("failed to load skill %s: %s", path, e)
            
    return _SKILLS_CACHE

@tool(
    "skill_lookup",
    description="查询特定的运维技能（SOP/Workflow）。当用户要求执行'巡检'、'排查'等复杂任务时，先调用此工具获取标准作业流程。参数：skill_name (例如 'daily_patrol')。",
)
def skill_lookup(skill_name: str) -> str:
    skills = _load_skills()
    content = skills.get(skill_name)
    if content:
        return content
    
    # Fuzzy match or list available
    available = ", ".join(skills.keys())
    return f"Skill '{skill_name}' not found. Available skills: {available}"
