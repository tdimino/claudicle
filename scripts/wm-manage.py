#!/usr/bin/env python3
"""Working memory management CLI.

Query, inspect, checkpoint, rollback, and selectively delete working memory.

Usage:
    uv run scripts/wm-manage.py query --channel C04ABC --limit 20
    uv run scripts/wm-manage.py stats
    uv run scripts/wm-manage.py stats --channel terminal:abc
    uv run scripts/wm-manage.py checkpoint create PRE_RESET --channel C --thread T
    uv run scripts/wm-manage.py checkpoint at-last-post --target-channel C_ENG_ALDEA --name pre-reset
    uv run scripts/wm-manage.py checkpoint list
    uv run scripts/wm-manage.py rollback pre-reset --channel C --thread T [--restore-soul-state]
    uv run scripts/wm-manage.py delete --channel C --thread T --type internalMonologue
    uv run scripts/wm-manage.py export --channel C --format jsonl
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

DAEMON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "daemon")
sys.path.insert(0, DAEMON_DIR)

from memory import working_memory
from memory import checkpoint as cp_mod


def _ts(epoch):
    """Format epoch timestamp as ISO 8601."""
    if epoch is None:
        return "—"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def cmd_query(args):
    """Query working memory entries."""
    results = working_memory.query(
        channel=args.channel,
        thread_ts=args.thread,
        entry_type=args.type,
        user_id=args.user,
        region=args.region,
        since=args.since,
        until=args.until,
        trace_id=args.trace,
        limit=args.limit,
    )

    if not results:
        print("No entries found.")
        return

    for r in results:
        ts = _ts(r.get("created_at"))
        etype = r.get("entry_type", "?")
        uid = r.get("user_id", "")
        content = r.get("content", "")[:120]
        region = r.get("region", "default")
        rid = r.get("id", "?")
        print(f"  [{rid}] {ts}  {etype:<20} {uid:<15} [{region}] {content}")

    print(f"\n  {len(results)} entries shown (limit={args.limit})")


def cmd_stats(args):
    """Show working memory statistics."""
    s = working_memory.stats(channel=args.channel)

    print(f"  Total entries: {s['total_entries']}")
    print(f"  Archive count: {s['archive_count']}")
    print(f"  Oldest: {_ts(s['oldest_entry'])}")
    print(f"  Newest: {_ts(s['newest_entry'])}")

    if s["by_channel"]:
        print("\n  By channel:")
        for ch, cnt in sorted(s["by_channel"].items()):
            print(f"    {ch:<40} {cnt:>6}")

    if s["by_entry_type"]:
        print("\n  By entry type:")
        for et, cnt in sorted(s["by_entry_type"].items()):
            print(f"    {et:<30} {cnt:>6}")

    if s["by_region"]:
        print("\n  By region:")
        for rg, cnt in sorted(s["by_region"].items()):
            print(f"    {rg:<20} {cnt:>6}")


def cmd_checkpoint_create(args):
    """Create a named checkpoint."""
    meta = json.loads(args.metadata) if args.metadata else None
    cp = cp_mod.create(args.name, args.channel, args.thread, metadata=meta)
    print(f"  Checkpoint '{cp.name}' created at entry id {cp.max_entry_id}")
    print(f"  Soul state keys: {list(cp.soul_state.keys())}")


def cmd_checkpoint_at_last_post(args):
    """Create checkpoint at last post to a target channel."""
    cp = cp_mod.create_at_last_post(
        args.channel, args.thread,
        target_channel=args.target_channel,
        user_id=args.user or "claudicle",
        name=args.name,
    )
    if cp is None:
        print(f"  No post by '{args.user or 'claudicle'}' found on {args.target_channel}")
        sys.exit(1)
    print(f"  Checkpoint '{cp.name}' created at entry id {cp.max_entry_id}")


def cmd_checkpoint_list(args):
    """List all checkpoints."""
    cps = cp_mod.list_checkpoints(channel=args.channel)
    if not cps:
        print("  No checkpoints found.")
        return

    print(f"  {'Name':<30} {'Channel':<25} {'Thread':<20} {'MaxID':>6} {'Created'}")
    print(f"  {'─'*30} {'─'*25} {'─'*20} {'─'*6} {'─'*20}")
    for c in cps:
        print(f"  {c.name:<30} {c.channel:<25} {c.thread_ts:<20} {c.max_entry_id:>6} {_ts(c.created_at)}")


def cmd_rollback(args):
    """Rollback to a named checkpoint."""
    result = cp_mod.rollback(
        args.name, args.channel, args.thread,
        restore_soul_state=args.restore_soul_state,
        archive=not args.no_archive,
    )
    if result["checkpoint"] is None:
        print(f"  Checkpoint '{args.name}' not found.")
        sys.exit(1)

    print(f"  Rolled back to '{args.name}'")
    print(f"  Deleted entries: {result['deleted_count']}")
    print(f"  Soul state restored: {result['soul_state_restored']}")


def cmd_delete(args):
    """Delete entries by filter criteria."""
    deleted = working_memory.delete_by_filter(
        args.channel, args.thread,
        entry_type=args.type,
        since=args.since,
        until=args.until,
        trace_id=args.trace,
        archive=not args.no_archive,
    )
    print(f"  Deleted {deleted} entries (archive={'off' if args.no_archive else 'on'})")


def cmd_export(args):
    """Export working memory entries."""
    results = working_memory.query(
        channel=args.channel,
        thread_ts=args.thread,
        limit=args.limit or 10000,
    )

    if args.format == "jsonl":
        for r in results:
            print(json.dumps(r, default=str))
    elif args.format == "csv":
        print("id,created_at,channel,thread_ts,entry_type,user_id,region,content")
        for r in results:
            content = r.get("content", "").replace('"', '""')[:200]
            print(f'{r.get("id","")},{_ts(r.get("created_at"))},'
                  f'{r.get("channel","")},{r.get("thread_ts","")},{r.get("entry_type","")},{r.get("user_id","")},{r.get("region","default")},"{content}"')


def main():
    parser = argparse.ArgumentParser(
        description="Working memory management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subs = parser.add_subparsers(dest="command", required=True)

    # query
    p_query = subs.add_parser("query", help="Query working memory entries")
    p_query.add_argument("--channel", "-c")
    p_query.add_argument("--thread", "-t")
    p_query.add_argument("--type", help="Entry type filter")
    p_query.add_argument("--user", help="User ID filter")
    p_query.add_argument("--region", "-r")
    p_query.add_argument("--since", type=float, help="Unix timestamp lower bound")
    p_query.add_argument("--until", type=float, help="Unix timestamp upper bound")
    p_query.add_argument("--trace", help="Trace ID filter")
    p_query.add_argument("--limit", "-n", type=int, default=50)
    p_query.set_defaults(func=cmd_query)

    # stats
    p_stats = subs.add_parser("stats", help="Show working memory statistics")
    p_stats.add_argument("--channel", "-c")
    p_stats.set_defaults(func=cmd_stats)

    # checkpoint (subcommands)
    p_cp = subs.add_parser("checkpoint", help="Checkpoint operations")
    cp_subs = p_cp.add_subparsers(dest="cp_command", required=True)

    # checkpoint create
    p_cp_create = cp_subs.add_parser("create", help="Create a named checkpoint")
    p_cp_create.add_argument("name", help="Checkpoint name")
    p_cp_create.add_argument("--channel", "-c", required=True)
    p_cp_create.add_argument("--thread", "-t", required=True)
    p_cp_create.add_argument("--metadata", help="JSON metadata string")
    p_cp_create.set_defaults(func=cmd_checkpoint_create)

    # checkpoint at-last-post
    p_cp_alp = cp_subs.add_parser("at-last-post", help="Checkpoint at last post to target channel")
    p_cp_alp.add_argument("--target-channel", required=True)
    p_cp_alp.add_argument("--channel", "-c", default="slack:default")
    p_cp_alp.add_argument("--thread", "-t", default="default")
    p_cp_alp.add_argument("--name", help="Override checkpoint name")
    p_cp_alp.add_argument("--user", help="User ID (default: claudicle)")
    p_cp_alp.set_defaults(func=cmd_checkpoint_at_last_post)

    # checkpoint list
    p_cp_list = cp_subs.add_parser("list", help="List all checkpoints")
    p_cp_list.add_argument("--channel", "-c")
    p_cp_list.set_defaults(func=cmd_checkpoint_list)

    # rollback
    p_rb = subs.add_parser("rollback", help="Rollback to a named checkpoint")
    p_rb.add_argument("name", help="Checkpoint name")
    p_rb.add_argument("--channel", "-c", required=True)
    p_rb.add_argument("--thread", "-t", required=True)
    p_rb.add_argument("--restore-soul-state", action="store_true")
    p_rb.add_argument("--no-archive", action="store_true", help="Skip archiving deleted entries")
    p_rb.set_defaults(func=cmd_rollback)

    # delete
    p_del = subs.add_parser("delete", help="Delete entries by filter")
    p_del.add_argument("--channel", "-c", required=True)
    p_del.add_argument("--thread", "-t", required=True)
    p_del.add_argument("--type", help="Entry type filter")
    p_del.add_argument("--since", type=float)
    p_del.add_argument("--until", type=float)
    p_del.add_argument("--trace", help="Trace ID filter")
    p_del.add_argument("--no-archive", action="store_true")
    p_del.set_defaults(func=cmd_delete)

    # export
    p_exp = subs.add_parser("export", help="Export working memory entries")
    p_exp.add_argument("--channel", "-c")
    p_exp.add_argument("--thread", "-t")
    p_exp.add_argument("--format", "-f", choices=["jsonl", "csv"], default="jsonl")
    p_exp.add_argument("--limit", "-n", type=int, default=10000)
    p_exp.set_defaults(func=cmd_export)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
