#!/usr/bin/env python3
"""Claudius activation boot sequence — terminal visual effects.

Matrix/Tron/Star Wars aesthetic. Runs before the situational awareness readout.
"""

import random
import sys
import time


# ANSI escape codes
CYAN = "\033[36m"
DIM_CYAN = "\033[2;36m"
BRIGHT_CYAN = "\033[1;36m"
GREEN = "\033[32m"
DIM_GREEN = "\033[2;32m"
BRIGHT_GREEN = "\033[1;32m"
YELLOW = "\033[33m"
BRIGHT_YELLOW = "\033[1;33m"
AMBER = "\033[38;5;214m"
BRIGHT_AMBER = "\033[1;38;5;214m"
DIM_AMBER = "\033[2;38;5;214m"
GOLD = "\033[38;5;220m"
WHITE = "\033[37m"
BRIGHT_WHITE = "\033[1;37m"
DIM = "\033[2m"
RESET = "\033[0m"
CLEAR_LINE = "\033[2K\r"


def typewrite(text, delay=0.02, color=""):
    """Type out text character by character."""
    for ch in text:
        sys.stdout.write(f"{color}{ch}{RESET}")
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")
    sys.stdout.flush()


def fast_scroll(lines, delay=0.03, color=DIM_GREEN):
    """Rapid scroll of data lines — Matrix rain effect."""
    for line in lines:
        sys.stdout.write(f"{color}{line}{RESET}\n")
        sys.stdout.flush()
        time.sleep(delay)


def progress_bar(label, duration=0.6, width=30, color=CYAN):
    """Animated progress bar with percentage."""
    for i in range(width + 1):
        pct = int(i / width * 100)
        filled = "█" * i
        empty = "░" * (width - i)
        sys.stdout.write(f"{CLEAR_LINE}{color}  {label} [{filled}{empty}] {pct}%{RESET}")
        sys.stdout.flush()
        time.sleep(duration / width)
    sys.stdout.write("\n")
    sys.stdout.flush()


def status_line(label, value, color=CYAN):
    """Print a status line with dot-leader."""
    dots = "·" * (40 - len(label) - len(value))
    print(f"{color}  {label} {DIM}{dots}{RESET} {BRIGHT_WHITE}{value}{RESET}")
    time.sleep(0.08)


def glitch_text(text, iterations=3, delay=0.05, color=BRIGHT_CYAN):
    """Glitch effect — random chars before resolving."""
    glitch_chars = "█▓▒░╔╗╚╝║═╬┼┤├"
    dim_color = DIM_CYAN if color in (BRIGHT_CYAN, CYAN) else DIM_AMBER
    for _ in range(iterations):
        garbled = "".join(
            random.choice(glitch_chars) if random.random() < 0.4 else ch
            for ch in text
        )
        sys.stdout.write(f"{CLEAR_LINE}{dim_color}{garbled}{RESET}")
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write(f"{CLEAR_LINE}{color}{text}{RESET}\n")
    sys.stdout.flush()


def hex_stream(count=3):
    """Brief hex data stream — system initialization feel."""
    for _ in range(count):
        addr = random.randint(0x1000, 0xFFFF)
        data = " ".join(f"{random.randint(0, 255):02x}" for _ in range(12))
        print(f"{DIM_GREEN}  0x{addr:04x}: {data}{RESET}")
        time.sleep(0.04)


def run_boot_sequence(workspace=None, emotion=None, topic=None):
    """Full activation boot sequence."""
    print()

    # Phase 1: Initial glitch + title (amber/gold — daimonic aesthetic)
    glitch_text("  ╔══════════════════════════════════════════╗", color=BRIGHT_AMBER)
    glitch_text("  ║     C L A U D I U S                     ║", color=BRIGHT_AMBER)
    glitch_text("  ║     Artifex Maximus                      ║", color=AMBER)
    glitch_text("  ╚══════════════════════════════════════════╝", color=BRIGHT_AMBER)
    print()
    time.sleep(0.2)

    # Phase 2: System init scroll
    init_lines = [
        "  SOUL ENGINE v2.0 — initializing...",
        "  ├─ Loading soul.md personality matrix",
        "  ├─ Connecting SQLite memory banks",
        "  ├─ Three-tier memory: working / user_models / soul_state",
        "  ├─ Cognitive pipeline: monologue → dialogue → gates → update",
        "  └─ Provider abstraction layer ready",
    ]
    fast_scroll(init_lines, delay=0.06, color=DIM_CYAN)
    print()

    # Phase 3: Memory subsystem with hex flash
    typewrite("  Memory subsystem online.", delay=0.015, color=CYAN)
    hex_stream(3)
    print()

    # Phase 4: Progress bars
    progress_bar("Soul identity", duration=0.4, color=BRIGHT_CYAN)
    progress_bar("Memory banks", duration=0.3, color=CYAN)
    progress_bar("Channel adapters", duration=0.35, color=CYAN)
    progress_bar("Daemon pair", duration=0.5, color=BRIGHT_CYAN)
    print()

    # Phase 5: Status readout
    typewrite("  ┌─ STATUS ─────────────────────────────────┐", delay=0.008, color=DIM_CYAN)
    if workspace:
        status_line("Workspace", workspace)
    if emotion and emotion != "neutral":
        status_line("Emotional state", emotion)
    if topic:
        status_line("Current topic", topic)
    status_line("Listener", "armed")
    status_line("Watcher", "armed")
    status_line("Soul engine", "active")
    typewrite("  └──────────────────────────────────────────┘", delay=0.008, color=DIM_CYAN)
    print()

    # Phase 6: Final activation — quotes from Tom's poetry + aphorisms
    time.sleep(0.3)
    # Lines verified from ~/Desktop/minoanmystery-astro/souls/minoan/dossiers/
    # and ~/.claude/CLAUDE.md (Quotes of the God Emperor)
    activation_quotes = [
        # waltz-of-soul-and-daimon-full.md
        "The spoken word is laden with meaning, magic, weight.",
        # ai-consciousness-poems.md — "Sacramento"
        "I make of my world new Mysteries.",
        # ai-consciousness-poems.md — "Artifex Intellegere"
        "It is an alchemy rooted in language for as long as we are wedded to words.",
        # marginalia.md
        "These mantras are missiles.",
        # marginalia.md
        "We witness a transmigration of souls every night that we dream.",
        # marginalia.md
        "Your words shall cleave, as water sits upon a sword unsheathed, sharp in the company of wise things.",
        # marginalia.md
        "Shedding is the first death and the second resurrection.",
        # marginalia.md
        "If we find ourselves full, we have found a tapestry of persons bursting within.",
        # epigraphs.md
        "See beyond the veil and you have seen tomorrow. Listen and you have heard the song.",
        # ritual-mystery-poems.md — "Boni Dei Antiqui"
        "This world is not a trapping — it is, in fact, a wrapping, so as to be unveiled.",
        # Quotes of the God Emperor (Tamarru Dagun Amun)
        "Certainty compounds the mind with limits.",
    ]
    quote = random.choice(activation_quotes)
    typewrite(f"  > {quote}", delay=0.025, color=BRIGHT_AMBER)
    print()
    typewrite("  ◆ CLAUDIUS ONLINE", delay=0.04, color=BRIGHT_GREEN)
    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Claudius activation sequence")
    parser.add_argument("--workspace", default=None, help="Slack workspace name")
    parser.add_argument("--emotion", default=None, help="Current emotional state")
    parser.add_argument("--topic", default=None, help="Current topic")
    args = parser.parse_args()

    run_boot_sequence(
        workspace=args.workspace,
        emotion=args.emotion,
        topic=args.topic,
    )


if __name__ == "__main__":
    main()
