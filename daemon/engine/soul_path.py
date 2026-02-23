"""
Soul profile resolution — finds the active soul.md path.

Resolution order:
1. CLAUDICLE_SOUL_PROFILE env var (per-session override)
2. soul/active symlink (if valid, points into profiles/)
3. soul/soul.md (always exists — backward compat)

Single-soul installations work identically: if profiles/ doesn't exist,
resolve_soul_path returns soul/soul.md exactly as before.
"""

import os


def resolve_soul_path(claudicle_home: str) -> str:
    """Resolve the active soul.md path.

    Returns an absolute path to the soul file to use for this session.
    """
    soul_dir = os.path.join(claudicle_home, "soul")

    # 1. Env var override (per-session profile)
    profile_name = os.environ.get("CLAUDICLE_SOUL_PROFILE", "").strip()
    if profile_name:
        profile_path = os.path.join(soul_dir, "profiles", f"{profile_name}.md")
        if os.path.isfile(profile_path):
            return profile_path

    # 2. Symlink (set by soul-profiles.py switch)
    active_link = os.path.join(soul_dir, "active")
    if os.path.islink(active_link):
        target = os.path.realpath(active_link)
        if os.path.isfile(target):
            return target

    # 3. Default (backward compat)
    return os.path.join(soul_dir, "soul.md")


def get_active_soul_name(claudicle_home: str) -> str:
    """Return the name of the active soul profile, or 'default'."""
    path = resolve_soul_path(claudicle_home)
    basename = os.path.basename(path)
    if basename == "soul.md":
        return "default"
    return os.path.splitext(basename)[0]
