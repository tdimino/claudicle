#!/usr/bin/env python3
"""claudicle-gc — Garbage collection and mind wipe for Claudicle.

Modes:
  status    Show sizes and counts of all data locations
  gc        Prune session data older than --age days (default: 7)
  wipe      Reset soul memory (working memory, soul state, user models, streams)

Usage:
  claudicle-gc status
  claudicle-gc gc [--age DAYS] [--dry-run] [--yes]
  claudicle-gc wipe [--dry-run] [--yes] [--keep-models]
"""

import argparse
import fcntl
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────

CLAUDICLE_HOME = Path(os.environ.get("CLAUDICLE_HOME", Path.home() / ".claudicle"))
CLAUDE_HOME = Path.home() / ".claude"

MEMORY_DB = CLAUDICLE_HOME / "daemon" / "memory" / "memory.db"
SOUL_STREAM = CLAUDICLE_HOME / "soul-stream.jsonl"
WM_STREAM = CLAUDICLE_HOME / "working-memory-stream.jsonl"
SESSION_INDEX = CLAUDICLE_HOME / "session-index.json"
MEMORY_DIR = CLAUDICLE_HOME / "memory"

HANDOFFS_DIR = CLAUDE_HOME / "handoffs"
SESSION_TAGS_DIR = CLAUDE_HOME / "session-tags"
SOUL_SESSIONS_DIR = CLAUDE_HOME / "soul-sessions"

# Protected files — never deleted
PROTECTED = {
    HANDOFFS_DIR / ".last-stop-handoff",
    HANDOFFS_DIR / "INDEX.md",
}


# ── Helpers ────────────────────────────────────────────────────────────

def _age_seconds(days: int) -> float:
    return days * 86400


def _file_age_days(path: Path) -> float:
    try:
        return (time.time() - path.stat().st_mtime) / 86400
    except OSError:
        return 999  # unreadable files treated as old (eligible for pruning)


def _iso_age_days(iso_str: str) -> float:
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except (ValueError, TypeError):
        return 999  # treat unparseable as very old


def _human_size(nbytes: int) -> str:
    for unit in ("B", "K", "M", "G"):
        if nbytes < 1024:
            return f"{nbytes:.0f}{unit}" if unit == "B" else f"{nbytes:.1f}{unit}"
        nbytes /= 1024
    return f"{nbytes:.1f}T"


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with open(path) as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _db_count(db_path: Path, table: str) -> int:
    if not db_path.exists():
        return 0
    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return row[0] if row else 0
    except sqlite3.Error:
        return 0
    finally:
        if conn:
            conn.close()


def _dir_files(d: Path, pattern: str = "*") -> list[Path]:
    if not d.exists():
        return []
    return [f for f in d.glob(pattern) if f.is_file() and f not in PROTECTED]


def _safe_unlink(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except OSError:
        return False


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically via tmp file + rename."""
    tmp = path.with_suffix(".gc-tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _flock_truncate(path: Path) -> None:
    """Truncate a file with fcntl.flock for safety against concurrent writers."""
    try:
        with open(path, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.truncate(0)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except OSError:
        pass


# ── Status ─────────────────────────────────────────────────────────────

def cmd_status():
    """Show sizes and counts of all Claudicle data locations."""
    print("Claudicle Data Status")
    print("─" * 50)

    # Handoffs
    handoffs = _dir_files(HANDOFFS_DIR, "*.yaml")
    h_size = sum(f.stat().st_size for f in handoffs) if handoffs else 0
    oldest_h = min((_file_age_days(f) for f in handoffs), default=0)
    print(f"  Session handoffs:     {len(handoffs):>3} files   {_human_size(h_size):>6}   (oldest: {oldest_h:.0f}d)")

    # Session tags
    tags = _dir_files(SESSION_TAGS_DIR, "*.json")
    t_size = sum(f.stat().st_size for f in tags) if tags else 0
    print(f"  Session tags:         {len(tags):>3} files   {_human_size(t_size):>6}")

    # Active stamps
    active = _dir_files(SOUL_SESSIONS_DIR / "active")
    print(f"  Active stamps:        {len(active):>3} files")

    # Cooldown stamps
    cooldowns = _dir_files(SOUL_SESSIONS_DIR / "reflect-cooldown")
    print(f"  Cooldown stamps:      {len(cooldowns):>3} files")

    # Registry
    reg_path = SOUL_SESSIONS_DIR / "registry.json"
    reg_count = 0
    if reg_path.exists():
        try:
            reg = json.loads(reg_path.read_text())
            reg_count = len(reg.get("sessions", {}))
        except (json.JSONDecodeError, OSError):
            pass
    print(f"  Registry entries:     {reg_count:>3}")

    # Session index
    si_count = 0
    if SESSION_INDEX.exists():
        try:
            si = json.loads(SESSION_INDEX.read_text())
            si_count = len(si.get("sessions", {}))
        except (json.JSONDecodeError, OSError):
            pass
    print(f"  Session index:        {si_count:>3} entries")

    print()

    # Memory DB
    wm = _db_count(MEMORY_DB, "working_memory")
    um = _db_count(MEMORY_DB, "user_models")
    sm = _db_count(MEMORY_DB, "soul_memory")
    db_size = MEMORY_DB.stat().st_size if MEMORY_DB.exists() else 0
    print(f"  Working memory:       {wm:>3} rows     ({_human_size(db_size)} total DB)")
    print(f"  User models:          {um:>3} rows")
    print(f"  Soul state:           {sm:>3} keys")

    # Soul stream
    ss_lines = _count_lines(SOUL_STREAM)
    ss_size = SOUL_STREAM.stat().st_size if SOUL_STREAM.exists() else 0
    print(f"  Soul stream:          {ss_lines:>3} lines   {_human_size(ss_size):>6}")

    # Memory git
    git_objects = 0
    git_dir = MEMORY_DIR / ".git"
    if git_dir.exists():
        try:
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=str(MEMORY_DIR), capture_output=True, text=True, timeout=5
            )
            git_objects = int(result.stdout.strip()) if result.returncode == 0 else 0
        except (subprocess.TimeoutExpired, ValueError):
            pass
    print(f"  Memory git commits:   {git_objects:>3}")

    # User/dossier markdown files
    user_mds = _dir_files(MEMORY_DIR / "users", "*.md")
    dossier_mds = list((MEMORY_DIR / "dossiers").rglob("*.md")) if (MEMORY_DIR / "dossiers").exists() else []
    print(f"  Memory user files:    {len(user_mds):>3}")
    print(f"  Memory dossier files: {len(dossier_mds):>3}")


# ── GC (session prune) ────────────────────────────────────────────────

def cmd_gc(age_days: int = 7, dry: bool = False, yes: bool = False) -> dict:
    """Prune session data older than age_days. Returns totals dict."""
    cutoff = time.time() - _age_seconds(age_days) + 1  # +1s buffer for --age 0

    if not dry and not yes:
        print(f"\nPrune session data older than {age_days} days? [y/N] ", end="", flush=True)
        if input().strip().lower() != "y":
            print("Aborted.")
            return {}

    print(f"Claudicle GC — pruning session data older than {age_days} days")
    if dry:
        print("  (dry run — no files will be deleted)\n")
    else:
        print()

    totals = {}

    # 1. Handoffs
    handoffs = _dir_files(HANDOFFS_DIR, "*.yaml")
    to_delete = [f for f in handoffs if f.stat().st_mtime < cutoff]
    to_keep = len(handoffs) - len(to_delete)
    totals["handoffs"] = len(to_delete)
    print(f"  Handoffs:        {len(to_delete)} to delete ({to_keep} to keep)")
    if not dry:
        for f in to_delete:
            _safe_unlink(f)

    # 2. Session tags
    tags = _dir_files(SESSION_TAGS_DIR, "*.json")
    tag_delete = []
    for f in tags:
        try:
            data = json.loads(f.read_text())
            updated = data.get("updated", "")
            if _iso_age_days(updated) > age_days:
                tag_delete.append(f)
        except (json.JSONDecodeError, OSError):
            tag_delete.append(f)  # malformed = delete
    totals["tags"] = len(tag_delete)
    print(f"  Session tags:    {len(tag_delete)} to delete ({len(tags) - len(tag_delete)} to keep)")
    if not dry:
        for f in tag_delete:
            _safe_unlink(f)

    # 3. Active stamps (filter by age — don't nuke live sessions)
    active = _dir_files(SOUL_SESSIONS_DIR / "active")
    if age_days == 0:
        stale_active = active  # wipe mode: all stamps
    else:
        stale_active = [f for f in active if _file_age_days(f) > age_days]
    totals["active"] = len(stale_active)
    print(f"  Active stamps:   {len(stale_active)} stale files")
    if not dry:
        for f in stale_active:
            _safe_unlink(f)

    # 4. Cooldown stamps (all)
    cooldowns = _dir_files(SOUL_SESSIONS_DIR / "reflect-cooldown")
    totals["cooldowns"] = len(cooldowns)
    print(f"  Cooldown stamps: {len(cooldowns)} files")
    if not dry:
        for f in cooldowns:
            _safe_unlink(f)

    # 5. Registry entries
    reg_path = SOUL_SESSIONS_DIR / "registry.json"
    reg_pruned = 0
    if reg_path.exists():
        try:
            reg = json.loads(reg_path.read_text())
            sessions = reg.get("sessions", {})
            to_remove = [
                sid for sid, info in sessions.items()
                if _iso_age_days(info.get("last_active", "")) > age_days
            ]
            reg_pruned = len(to_remove)
            if not dry and to_remove:
                for sid in to_remove:
                    del sessions[sid]
                reg["updated_at"] = datetime.now(timezone.utc).isoformat()
                _atomic_write_json(reg_path, reg)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  Warning: registry update failed: {e}", file=sys.stderr)
    totals["registry"] = reg_pruned
    print(f"  Registry:        {reg_pruned} entries to prune")

    # 6. Session index
    si_pruned = 0
    if SESSION_INDEX.exists():
        try:
            si = json.loads(SESSION_INDEX.read_text())
            sessions = si.get("sessions", {})
            to_remove = [
                sid for sid, info in sessions.items()
                if _iso_age_days(info.get("last_active", "")) > age_days
            ]
            si_pruned = len(to_remove)
            if not dry and to_remove:
                for sid in to_remove:
                    del sessions[sid]
                si["updated_at"] = datetime.now(timezone.utc).isoformat()
                _atomic_write_json(SESSION_INDEX, si)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  Warning: session index update failed: {e}", file=sys.stderr)
    totals["session_index"] = si_pruned
    print(f"  Session index:   {si_pruned} entries to prune")

    # 7. Working memory (SQLite TTL)
    wm_deleted = 0
    if MEMORY_DB.exists():
        conn = None
        try:
            conn = sqlite3.connect(str(MEMORY_DB))
            if not dry:
                cursor = conn.execute(
                    "DELETE FROM working_memory WHERE created_at < ?", (cutoff,)
                )
                wm_deleted = cursor.rowcount
                conn.commit()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM working_memory WHERE created_at < ?", (cutoff,)
                ).fetchone()
                wm_deleted = row[0] if row else 0
        except sqlite3.Error as e:
            print(f"  Warning: working memory cleanup failed: {e}", file=sys.stderr)
        finally:
            if conn:
                conn.close()
    totals["working_memory"] = wm_deleted
    print(f"  Working memory:  {wm_deleted} rows")

    # 8. Rebuild INDEX.md from remaining handoffs
    if not dry and totals["handoffs"] > 0:
        _rebuild_handoff_index()

    total = sum(totals.values())
    print(f"\n  Total: {total} items {'would be ' if dry else ''}pruned")
    return totals


def _parse_handoff_objective(text: str) -> str:
    """Extract objective from a handoff YAML, handling block scalars."""
    lines = text.splitlines()
    objective_parts = []
    in_objective = False

    for line in lines:
        if in_objective:
            if line.startswith("  ") or line.startswith("\t"):
                objective_parts.append(line.strip())
            elif line.strip():
                break  # new top-level key
        elif line.startswith("objective:"):
            rest = line[len("objective:"):].strip()
            if rest in (">", "|", ">-", "|-", ""):
                in_objective = True  # block scalar follows
            else:
                objective_parts.append(rest.strip('"').strip("'"))
                break

    objective = " ".join(objective_parts)
    if len(objective) > 120:
        objective = objective[:117] + "..."
    return objective


def _rebuild_handoff_index():
    """Rebuild INDEX.md from remaining YAML handoff files."""
    index_file = HANDOFFS_DIR / "INDEX.md"
    header = (
        "# Session Handoffs\n\n"
        "| Date | Project | Session | Trigger | Directory | Summary |\n"
        "|------|---------|---------|---------|-----------|---------|"
    )

    rows = []
    for f in sorted(HANDOFFS_DIR.glob("*.yaml"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            text = f.read_text()
            fields = {}
            for line in text.splitlines()[:10]:
                m = re.match(r'^(\w+):\s*"(.+?)"\s*$', line)
                if m:
                    fields[m.group(1)] = m.group(2)

            objective = _parse_handoff_objective(text)

            rows.append(
                f"| {fields.get('timestamp', '?')} "
                f"| {fields.get('project', '?')} "
                f"| `{fields.get('session_short', '?')}` "
                f"| {fields.get('trigger', '?')} "
                f"| `{fields.get('cwd', '?')}` "
                f"| {objective} |"
            )
        except OSError:
            continue

    rows = rows[:50]
    index_file.write_text(header + "\n" + "\n".join(rows) + "\n")


# ── Wipe (soul memory reset) ──────────────────────────────────────────

def cmd_wipe(dry: bool = False, yes: bool = False, keep_models: bool = False):
    """Reset soul memory — user models, soul state, streams, working memory."""
    print("Claudicle Mind Wipe — erasing soul memory")
    if dry:
        print("  (dry run — nothing will be deleted)\n")
    else:
        print()

    # Show what will be wiped
    wm = _db_count(MEMORY_DB, "working_memory")
    sm = _db_count(MEMORY_DB, "soul_memory")
    um = _db_count(MEMORY_DB, "user_models")
    ss = _count_lines(SOUL_STREAM)
    ws = _count_lines(WM_STREAM) if WM_STREAM.exists() else 0
    user_mds = _dir_files(MEMORY_DIR / "users", "*.md")
    dossier_mds = list((MEMORY_DIR / "dossiers").rglob("*.md")) if (MEMORY_DIR / "dossiers").exists() else []
    soul_state_md = MEMORY_DIR / "soul_state.md"

    print(f"  Working memory:    {wm:>3} rows → DELETE ALL")
    print(f"  Soul state:        {sm:>3} keys → DELETE ALL")
    if keep_models:
        print(f"  User models:       {um:>3} rows → KEEP (--keep-models)")
    else:
        print(f"  User models:       {um:>3} rows → DELETE ALL")
    print(f"  Soul stream:       {ss:>3} lines → TRUNCATE")
    if ws:
        print(f"  WM stream:         {ws:>3} lines → TRUNCATE")
    if not keep_models:
        print(f"  User MD exports:   {len(user_mds):>3} files → DELETE")
        print(f"  Dossier exports:   {len(dossier_mds):>3} files → DELETE")
    if soul_state_md.exists():
        print(f"  Soul state MD:       1 file  → DELETE")
    print(f"  + full session GC (--age 0)")

    if not dry and not yes:
        print("\nThis is irreversible. Type 'wipe' to confirm: ", end="", flush=True)
        confirm = input()
        if confirm.strip() != "wipe":
            print("Aborted.")
            return

    if not dry:
        # SQLite wipes
        if MEMORY_DB.exists():
            conn = None
            try:
                conn = sqlite3.connect(str(MEMORY_DB))
                conn.execute("DELETE FROM working_memory")
                conn.execute("DELETE FROM soul_memory")
                if not keep_models:
                    conn.execute("DELETE FROM user_models")
                conn.commit()
                conn.execute("VACUUM")
                conn.close()
                conn = None
            except sqlite3.Error as e:
                print(f"  DB error: {e}", file=sys.stderr)
            finally:
                if conn:
                    conn.close()

        # Truncate streams (with flock for concurrent writer safety)
        for stream in (SOUL_STREAM, WM_STREAM):
            if stream.exists():
                _flock_truncate(stream)

        # Delete memory exports
        if not keep_models:
            for f in user_mds:
                _safe_unlink(f)
            for f in dossier_mds:
                _safe_unlink(f)
        if soul_state_md.exists():
            _safe_unlink(soul_state_md)

        # Git cleanup in memory dir
        if (MEMORY_DIR / ".git").exists():
            try:
                r = subprocess.run(
                    ["git", "add", "-A"],
                    cwd=str(MEMORY_DIR), capture_output=True, timeout=10
                )
                if r.returncode == 0:
                    r2 = subprocess.run(
                        ["git", "commit", "-m", "Mind wipe: reset soul memory"],
                        cwd=str(MEMORY_DIR), capture_output=True, timeout=10
                    )
                    if r2.returncode == 0:
                        subprocess.run(
                            ["git", "gc"],
                            cwd=str(MEMORY_DIR), capture_output=True, timeout=30
                        )
            except subprocess.TimeoutExpired:
                pass

    # Also run full GC
    print()
    cmd_gc(age_days=0, dry=dry, yes=True)

    if not dry:
        print("\nMind wiped. Soul personality (soul.md) is untouched.")


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="claudicle-gc",
        description="Garbage collection and mind wipe for Claudicle.",
    )
    sub = parser.add_subparsers(dest="mode")

    # status
    sub.add_parser("status", help="Show data sizes and counts")

    # gc
    gc_p = sub.add_parser("gc", help="Prune session data by age")
    gc_p.add_argument("--age", type=int, default=7, help="Days to keep (default: 7)")
    gc_p.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    gc_p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")

    # wipe
    wipe_p = sub.add_parser("wipe", help="Reset soul memory")
    wipe_p.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    wipe_p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    wipe_p.add_argument("--keep-models", action="store_true", help="Preserve user models")

    args = parser.parse_args()

    if args.mode == "status":
        cmd_status()
    elif args.mode == "gc":
        cmd_gc(age_days=args.age, dry=args.dry_run, yes=args.yes)
    elif args.mode == "wipe":
        cmd_wipe(dry=args.dry_run, yes=args.yes, keep_models=args.keep_models)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
