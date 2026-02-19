#!/usr/bin/env bash
#
# Claudicle — Soul Agent Setup
#
# Interactive installer for personal or company mode.
# Copies hooks, commands, daemon, and scripts into ~/.claudicle/
# and wires Claude Code hooks in settings.json.
#
# Usage:
#   ./setup.sh [--personal | --company]
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDICLE_HOME="${CLAUDICLE_HOME:-$HOME/.claudicle}"
CLAUDE_DIR="$HOME/.claude"
SETTINGS_FILE="$CLAUDE_DIR/settings.json"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}→${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}!${NC} $*"; }
error() { echo -e "${RED}✗${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# Detect mode
# ---------------------------------------------------------------------------

MODE=""
SOUL_TEMPLATE=""

if [[ "${1:-}" == "--personal" ]]; then
    MODE="personal"
elif [[ "${1:-}" == "--company" ]]; then
    MODE="company"
fi

echo ""
echo -e "${BOLD}  ╔═══════════════════════════════════╗${NC}"
echo -e "${BOLD}  ║     ${CYAN}Claudicle${NC}${BOLD} — Soul Agent Setup   ║${NC}"
echo -e "${BOLD}  ╚═══════════════════════════════════╝${NC}"
echo ""

if [[ -z "$MODE" ]]; then
    echo "  How will you use Claudicle?"
    echo ""
    echo "  1) Personal — Your own soul agent, your machine"
    echo "  2) Company  — Team soul agent with shared channels"
    echo ""
    read -rp "  Choose [1/2]: " choice
    case "$choice" in
        1|personal)  MODE="personal" ;;
        2|company)   MODE="company" ;;
        *)           error "Invalid choice"; exit 1 ;;
    esac
fi

info "Setting up Claudicle in ${BOLD}$MODE${NC} mode"
echo ""

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

if ! command -v claude &>/dev/null; then
    error "Claude Code CLI not found. Install it first: https://docs.anthropic.com/claude-code"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    error "Python 3 not found."
    exit 1
fi

# ---------------------------------------------------------------------------
# Create CLAUDICLE_HOME
# ---------------------------------------------------------------------------

info "Installing to $CLAUDICLE_HOME"
mkdir -p "$CLAUDICLE_HOME"

# Copy core directories
cp -r "$SCRIPT_DIR/daemon"   "$CLAUDICLE_HOME/daemon"
cp -r "$SCRIPT_DIR/soul"     "$CLAUDICLE_HOME/soul"
cp -r "$SCRIPT_DIR/hooks"    "$CLAUDICLE_HOME/hooks"
cp -r "$SCRIPT_DIR/commands" "$CLAUDICLE_HOME/commands"
cp -r "$SCRIPT_DIR/scripts"  "$CLAUDICLE_HOME/scripts"
cp -r "$SCRIPT_DIR/adapters" "$CLAUDICLE_HOME/adapters"
cp -r "$SCRIPT_DIR/docs"     "$CLAUDICLE_HOME/docs"
ok "Core files installed"

# ---------------------------------------------------------------------------
# Soul template
# ---------------------------------------------------------------------------

if [[ "$MODE" == "company" ]] && [[ -f "$SCRIPT_DIR/setups/company/soul.md" ]]; then
    SOUL_TEMPLATE="$SCRIPT_DIR/setups/company/soul.md"
elif [[ -f "$SCRIPT_DIR/setups/personal/soul.md" ]]; then
    SOUL_TEMPLATE="$SCRIPT_DIR/setups/personal/soul.md"
fi

if [[ -n "$SOUL_TEMPLATE" ]]; then
    echo ""
    read -rp "  Use the example soul template for $MODE mode? [Y/n]: " use_template
    if [[ "${use_template:-Y}" =~ ^[Yy] ]]; then
        cp "$SOUL_TEMPLATE" "$CLAUDICLE_HOME/soul/soul.md"
        ok "Soul template installed — edit $CLAUDICLE_HOME/soul/soul.md to customize"
    else
        ok "Keeping default soul.md"
    fi
fi

# ---------------------------------------------------------------------------
# Wire Claude Code hooks
# ---------------------------------------------------------------------------

info "Wiring Claude Code hooks..."

mkdir -p "$CLAUDE_DIR"

# Create or update settings.json
if [[ ! -f "$SETTINGS_FILE" ]]; then
    echo '{}' > "$SETTINGS_FILE"
fi

# Use Python to safely merge hook config (non-destructive)
python3 << 'PYTHON_MERGE'
import json
import os

settings_file = os.path.expanduser("~/.claude/settings.json")
claudicle_home = os.environ.get("CLAUDICLE_HOME", os.path.expanduser("~/.claudicle"))

with open(settings_file) as f:
    settings = json.load(f)

hooks = settings.setdefault("hooks", {})

# SessionStart hook
session_start = hooks.setdefault("SessionStart", [])
activate_cmd = f"python3 {claudicle_home}/hooks/soul-activate.py"
if not any(activate_cmd in str(h) for h in session_start):
    session_start.append({
        "type": "command",
        "command": activate_cmd
    })

# SessionEnd hook (previously called Stop in some versions)
for event in ["SessionEnd", "Stop"]:
    event_hooks = hooks.setdefault(event, [])
    deregister_cmd = f"python3 {claudicle_home}/hooks/soul-deregister.py"
    if not any(deregister_cmd in str(h) for h in event_hooks):
        event_hooks.append({
            "type": "command",
            "command": deregister_cmd
        })

with open(settings_file, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")

print("  Hooks merged into settings.json")
PYTHON_MERGE

ok "Hooks wired"

# ---------------------------------------------------------------------------
# Copy commands to Claude Code
# ---------------------------------------------------------------------------

info "Installing slash commands..."
mkdir -p "$CLAUDE_DIR/commands"
for cmd_file in "$CLAUDICLE_HOME/commands"/*.md; do
    cmd_name=$(basename "$cmd_file")
    if [[ ! -f "$CLAUDE_DIR/commands/$cmd_name" ]]; then
        cp "$cmd_file" "$CLAUDE_DIR/commands/$cmd_name"
        ok "  /$(basename "$cmd_name" .md)"
    else
        warn "  /$(basename "$cmd_name" .md) already exists — skipping"
    fi
done

# ---------------------------------------------------------------------------
# Create soul-sessions directory
# ---------------------------------------------------------------------------

mkdir -p "$HOME/.claude/soul-sessions/active"
ok "Soul sessions directory ready"

# ---------------------------------------------------------------------------
# Install agent docs
# ---------------------------------------------------------------------------

info "Installing agent docs..."
mkdir -p "$CLAUDE_DIR/agent_docs"

for doc_file in "$SCRIPT_DIR/agent_docs"/*.md; do
    doc_name=$(basename "$doc_file")
    target="$CLAUDE_DIR/agent_docs/claudicle-${doc_name}"
    if [[ ! -f "$target" ]]; then
        cp "$doc_file" "$target"
        ok "  agent_docs/claudicle-${doc_name}"
    else
        warn "  agent_docs/claudicle-${doc_name} already exists — skipping"
    fi
done

# ---------------------------------------------------------------------------
# Install bundled skills
# ---------------------------------------------------------------------------

info "Installing bundled skills..."
if [[ -d "$SCRIPT_DIR/skills/open-souls-paradigm" ]]; then
    target_skill="$CLAUDE_DIR/skills/open-souls-paradigm"
    if [[ ! -d "$target_skill" ]]; then
        mkdir -p "$target_skill"
        cp -r "$SCRIPT_DIR/skills/open-souls-paradigm/"* "$target_skill/"
        ok "  open-souls-paradigm skill installed"
    else
        warn "  open-souls-paradigm skill already exists — skipping"
    fi
fi

# ---------------------------------------------------------------------------
# Create handoffs directory
# ---------------------------------------------------------------------------

mkdir -p "$HOME/.claude/handoffs"
ok "Handoffs directory ready"

# ---------------------------------------------------------------------------
# User model (optional)
# ---------------------------------------------------------------------------

echo ""
info "User model (optional — helps Claudicle adapt to your style)"
echo ""
read -rp "  Create a user model? [Y/n]: " create_model

if [[ "${create_model:-Y}" =~ ^[Yy] ]]; then
    read -rp "  Your first name: " user_name
    if [[ -n "$user_name" ]]; then
        model_file="$HOME/.claude/userModels/${user_name}Model.md"
        mkdir -p "$HOME/.claude/userModels"
        if [[ ! -f "$model_file" ]]; then
            sed "s/\[Your Name\]/$user_name/" "$SCRIPT_DIR/soul/userModel-template.md" > "$model_file"
            ok "User model template created at $model_file"
            echo "  Fill it in, or let Claudicle interview you via Slack to build it automatically."
        else
            warn "User model already exists at $model_file — skipping"
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Handoff/continuity hooks (optional)
# ---------------------------------------------------------------------------

echo ""
read -rp "  Enable session handoff hooks? (recommended) [Y/n]: " enable_handoffs

if [[ "${enable_handoffs:-Y}" =~ ^[Yy] ]]; then
    python3 << 'PYTHON_HANDOFF'
import json
import os

settings_file = os.path.expanduser("~/.claude/settings.json")
claudicle_home = os.environ.get("CLAUDICLE_HOME", os.path.expanduser("~/.claudicle"))

with open(settings_file) as f:
    settings = json.load(f)

hooks = settings.setdefault("hooks", {})

handoff_cmd = f"python3 {claudicle_home}/hooks/claudicle-handoff.py"

# PreCompact hook
precompact = hooks.setdefault("PreCompact", [])
if not any(handoff_cmd in str(h) for h in precompact):
    precompact.append({"type": "command", "command": handoff_cmd})

# Stop hook
stop = hooks.setdefault("Stop", [])
if not any(handoff_cmd in str(h) for h in stop):
    stop.append({"type": "command", "command": handoff_cmd})

with open(settings_file, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")

print("  Handoff hooks wired")
PYTHON_HANDOFF
    ok "Session handoff hooks enabled"
fi

# ---------------------------------------------------------------------------
# Set CLAUDICLE_HOME in shell profile
# ---------------------------------------------------------------------------

SHELL_RC=""
if [[ -f "$HOME/.zshrc" ]]; then
    SHELL_RC="$HOME/.zshrc"
elif [[ -f "$HOME/.bashrc" ]]; then
    SHELL_RC="$HOME/.bashrc"
fi

if [[ -n "$SHELL_RC" ]]; then
    if ! grep -q "CLAUDICLE_HOME" "$SHELL_RC" 2>/dev/null; then
        echo "" >> "$SHELL_RC"
        echo "# Claudicle soul agent" >> "$SHELL_RC"
        echo "export CLAUDICLE_HOME=\"$CLAUDICLE_HOME\"" >> "$SHELL_RC"
        ok "Added CLAUDICLE_HOME to $SHELL_RC"
    else
        ok "CLAUDICLE_HOME already in $SHELL_RC"
    fi
fi

# ---------------------------------------------------------------------------
# Generate skills manifest
# ---------------------------------------------------------------------------

info "Generating skills manifest..."
SKILLS_MD="$CLAUDICLE_HOME/daemon/skills.md"
echo "# Available Skills & Tools" > "$SKILLS_MD"
echo "" >> "$SKILLS_MD"
echo "Skills discovered at install time from \`~/.claude/skills/\`:" >> "$SKILLS_MD"
echo "" >> "$SKILLS_MD"

skill_count=0
for skill_dir in "$HOME/.claude/skills"/*/; do
    if [[ -f "$skill_dir/SKILL.md" ]]; then
        name=$(basename "$skill_dir")
        desc=$(grep -m1 "^description:" "$skill_dir/SKILL.md" 2>/dev/null | sed 's/description: *//' | tr -d '"' || echo "")
        if [[ -n "$desc" ]]; then
            echo "- **$name**: $desc" >> "$SKILLS_MD"
        else
            echo "- **$name**" >> "$SKILLS_MD"
        fi
        skill_count=$((skill_count + 1))
    fi
done

if [[ $skill_count -eq 0 ]]; then
    echo "_No skills found. Install skills to \`~/.claude/skills/\` and re-run setup._" >> "$SKILLS_MD"
fi
ok "Skills manifest: $skill_count skill(s) found"

# ---------------------------------------------------------------------------
# Install Python dependencies
# ---------------------------------------------------------------------------

info "Installing Python dependencies..."
if command -v uv &>/dev/null; then
    uv pip install --system slack_bolt slack_sdk textual psutil 2>/dev/null && ok "Dependencies installed (uv)" || warn "Dependency install failed — install manually: pip install slack_bolt slack_sdk textual psutil"
elif command -v pip3 &>/dev/null; then
    pip3 install slack_bolt slack_sdk textual psutil 2>/dev/null && ok "Dependencies installed (pip)" || warn "Dependency install failed — install manually: pip install slack_bolt slack_sdk textual psutil"
else
    warn "No pip found. Install manually: pip install slack_bolt slack_sdk textual psutil"
fi

# ---------------------------------------------------------------------------
# Slack tokens (optional)
# ---------------------------------------------------------------------------

echo ""
info "Slack integration (optional — skip if you only want /ensoul)"
echo ""

if [[ -z "${SLACK_BOT_TOKEN:-}" ]]; then
    read -rp "  SLACK_BOT_TOKEN (or press Enter to skip): " slack_bot
    if [[ -n "$slack_bot" ]]; then
        if [[ -n "$SHELL_RC" ]]; then
            echo "export SLACK_BOT_TOKEN=\"$slack_bot\"" >> "$SHELL_RC"
        fi
    fi
else
    ok "SLACK_BOT_TOKEN already set"
fi

if [[ -z "${SLACK_APP_TOKEN:-}" ]]; then
    read -rp "  SLACK_APP_TOKEN (or press Enter to skip): " slack_app
    if [[ -n "$slack_app" ]]; then
        if [[ -n "$SHELL_RC" ]]; then
            echo "export SLACK_APP_TOKEN=\"$slack_app\"" >> "$SHELL_RC"
        fi
    fi
else
    ok "SLACK_APP_TOKEN already set"
fi

# ---------------------------------------------------------------------------
# Company mode extras
# ---------------------------------------------------------------------------

if [[ "$MODE" == "company" ]]; then
    echo ""
    info "Company mode setup"
    read -rp "  Team/company name: " team_name
    if [[ -n "$team_name" ]]; then
        # Update soul.md with company name
        sed -i '' "s/\[COMPANY\]/$team_name/g" "$CLAUDICLE_HOME/soul/soul.md" 2>/dev/null || true
        ok "Company name set to $team_name"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo -e "${BOLD}  ═══════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  Claudicle is ready.${NC}"
echo -e "${BOLD}  ═══════════════════════════════════${NC}"
echo ""
echo "  Installed to: $CLAUDICLE_HOME"
echo "  Mode: $MODE"
echo "  Skills: $skill_count"
echo ""
echo "  Quick start:"
echo "    1. Open Claude Code in any project"
echo "    2. Run /ensoul to activate the soul"
echo "    3. (Optional) Run /slack-sync #channel for Slack"
echo ""
echo "  To customize your soul:"
echo "    Edit $CLAUDICLE_HOME/soul/soul.md"
echo ""
echo "  To start the Slack listener:"
echo "    cd $CLAUDICLE_HOME/daemon && python3 slack_listen.py --bg"
echo ""
echo "  To start the autonomous daemon:"
echo "    cd $CLAUDICLE_HOME/daemon && python3 claudicle.py"
echo ""
