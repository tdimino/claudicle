"""Discover available skills from daemon and user skill directories."""

import os


def _read_skills_md() -> str:
    """Read the daemon's built-in skills.md."""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills.md")
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return ""


def _read_claude_skills() -> list[str]:
    """List skill names from ~/.claude/skills/ (claude-code-minoan, etc.)."""
    skills_dir = os.path.expanduser("~/.claude/skills")
    if not os.path.isdir(skills_dir):
        return []
    skills = []
    for name in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, name)
        if os.path.isdir(skill_path) and os.path.exists(
            os.path.join(skill_path, "SKILL.md")
        ):
            skills.append(name)
    return skills


def format_available_skills() -> str:
    """Format all available skills for the interview prompt."""
    parts = []

    # Built-in daemon tools
    daemon_skills = _read_skills_md()
    if daemon_skills:
        parts.append("### Built-in Tools\n")
        parts.append(daemon_skills)

    # Claude Code skills (from ~/.claude/skills/)
    claude_skills = _read_claude_skills()
    if claude_skills:
        parts.append("\n### Claude Code Skills\n")
        for name in claude_skills:
            parts.append(f"- **{name}**")

    return "\n".join(parts) if parts else "No additional skills discovered."
