# Skill Registry — point.ai

Generated: 2026-04-06

## User Skills

| Skill | Trigger | Source |
|-------|---------|--------|
| go-testing | Go tests, Bubbletea TUI testing | ~/.claude/skills/go-testing |
| skill-creator | Creating new AI skills | ~/.claude/skills/skill-creator |
| branch-pr | Creating PRs, opening PRs | ~/.claude/skills/branch-pr |
| issue-creation | Creating GitHub issues | ~/.claude/skills/issue-creation |
| judgment-day | Adversarial review protocol | ~/.claude/skills/judgment-day |
| fastapi | FastAPI patterns | .venv (vendored) |

## Project Conventions

| File | Purpose |
|------|---------|
| ~/.claude/CLAUDE.md | Global user instructions, personality, language rules |

## Compact Rules

### fastapi
- FastAPI project with service layer pattern
- Routes in app.py, services in backend/services/
- Pydantic models in backend/models.py

### go-testing
- Not applicable to this project (Python + TypeScript)
