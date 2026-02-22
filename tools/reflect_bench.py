#!/usr/bin/env python3
"""
Reflection pipeline benchmark — test any model's cognitive step compliance.

Sends a reflection prompt to any provider/model and displays parsed results
with timing, XML compliance scoring, and side-by-side comparison.

Usage:
    # Default (Groq + Kimi-K2):
    python3 tools/reflect_bench.py

    # Specific model:
    python3 tools/reflect_bench.py -p groq -m qwen/qwen3-32b

    # Compare multiple models:
    python3 tools/reflect_bench.py --compare \
        groq:moonshotai/kimi-k2-instruct \
        groq:qwen/qwen3-32b \
        openrouter:google/gemini-2.5-flash-lite

    # Custom exchange:
    python3 tools/reflect_bench.py -u "What's the etymology of Knossos?" \
        -a "From Semitic *kns, meaning gathering place..."

    # Show raw XML:
    python3 tools/reflect_bench.py --raw

    # Show full prompt sent to the model:
    python3 tools/reflect_bench.py --show-prompt

    # List available providers:
    python3 tools/reflect_bench.py --list
"""

import argparse
import os
import sys
import time

# Add daemon to path so imports work from repo root
_DAEMON_DIR = os.path.join(os.path.dirname(__file__), "..", "daemon")
sys.path.insert(0, os.path.abspath(_DAEMON_DIR))

from engine.reflect import (
    _call_llm,
    _PROVIDERS,
    _REFLECTION_STEPS,
    _resolve_api_key,
    build_reflection_prompt,
)
from engine.soul_engine import extract_tag
import config

# -- ANSI colors -------------------------------------------------------------

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
RESET = "\033[0m"

# -- Expected tags -----------------------------------------------------------

_EXPECTED_TAGS = [
    ("internal_monologue", True, "has verb attr"),
    ("user_model_check", True, "true/false"),
    ("user_model_update", False, "only if check=true"),
    ("model_change_note", False, "only if update present"),
    ("soul_state_check", True, "true/false"),
    ("soul_state_update", False, "only if check=true"),
]

DEFAULT_USER = (
    "Let's look at the Claudicle test suite next. I want to make sure "
    "the reflection pipeline has coverage before we ship it."
)
DEFAULT_ASSISTANT = (
    "Good call. The test suite currently has 319 tests across the four "
    "architecture layers but nothing for reflect.py yet. I'll draft test "
    "cases for build_reflection_prompt(), the XML parsing, and the memory "
    "update paths."
)


# -- Parsing & scoring -------------------------------------------------------

def parse_response(raw: str) -> dict:
    """Parse XML tags from raw LLM response."""
    results = {}
    for tag_name, _req, _note in _EXPECTED_TAGS:
        content, verb = extract_tag(raw, tag_name)
        results[tag_name] = {"content": content.strip(), "verb": verb} if content else None
    return results


def score_compliance(results: dict) -> tuple[int, int, list[str]]:
    """Score XML tag compliance. Returns (passed, total, issues)."""
    passed = 0
    total = 0
    issues = []

    for tag_name, required, _note in _EXPECTED_TAGS:
        if not required:
            # Conditional: only score if the corresponding gate was true
            gate_map = {
                "user_model_update": "user_model_check",
                "model_change_note": "user_model_update",
                "soul_state_update": "soul_state_check",
            }
            gate = gate_map.get(tag_name)
            if gate:
                gate_result = results.get(gate)
                gate_true = (
                    gate_result and gate_result["content"].strip().lower() == "true"
                ) if gate != "user_model_update" else (gate_result is not None)
                if gate_true:
                    total += 1
                    if results[tag_name]:
                        passed += 1
                    else:
                        issues.append(f"{gate}=true but no <{tag_name}>")
            continue

        total += 1
        if results.get(tag_name):
            passed += 1
            if tag_name == "internal_monologue" and not results[tag_name].get("verb"):
                issues.append("internal_monologue missing verb attribute")
        else:
            issues.append(f"missing required: <{tag_name}>")

    return passed, total, issues


# -- Display -----------------------------------------------------------------

def display_result(provider: str, model: str, raw: str, elapsed: float,
                   show_raw: bool = False) -> tuple[int, int, float]:
    """Display parsed reflection results."""
    results = parse_response(raw)
    passed, total, issues = score_compliance(results)

    score_color = GREEN if passed == total else (YELLOW if passed >= total - 1 else RED)
    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}{provider}{RESET} / {CYAN}{model}{RESET}")
    print(f"{DIM}{elapsed:.2f}s{RESET}  |  {score_color}{passed}/{total} tags{RESET}")
    print(f"{'='*70}")

    if show_raw:
        print(f"\n{DIM}--- RAW ---{RESET}")
        print(raw)
        print(f"{DIM}--- END ---{RESET}\n")

    # Internal monologue
    mono = results.get("internal_monologue")
    if mono:
        verb = mono.get("verb") or "?"
        print(f"\n{MAGENTA}Internal Monologue{RESET} {DIM}(verb={verb}){RESET}")
        for line in mono["content"].splitlines():
            print(f"  {line[:100]}")
    else:
        print(f"\n{RED}Internal Monologue: MISSING{RESET}")

    # User model check
    check = results.get("user_model_check")
    if check:
        val = check["content"].strip().lower()
        color = GREEN if val in ("true", "false") else RED
        print(f"\n{color}User Model Check: {val}{RESET}")
    else:
        print(f"\n{RED}User Model Check: MISSING{RESET}")

    # Conditional user model sections
    if check and check["content"].strip().lower() == "true":
        upd = results.get("user_model_update")
        if upd:
            lines = upd["content"].splitlines()
            print(f"\n{CYAN}User Model Update{RESET} {DIM}({len(lines)} lines){RESET}")
            for line in lines[:8]:
                print(f"  {line[:100]}")
            if len(lines) > 8:
                print(f"  {DIM}... +{len(lines)-8} more{RESET}")
        else:
            print(f"\n{YELLOW}User Model Update: MISSING (check was true){RESET}")

        note = results.get("model_change_note")
        if note:
            print(f"\n{DIM}Change note: {note['content'][:200]}{RESET}")

    # Soul state check
    state = results.get("soul_state_check")
    if state:
        val = state["content"].strip().lower()
        color = GREEN if val in ("true", "false") else RED
        print(f"\n{color}Soul State Check: {val}{RESET}")
    else:
        print(f"\n{RED}Soul State Check: MISSING{RESET}")

    if state and state["content"].strip().lower() == "true":
        sup = results.get("soul_state_update")
        if sup:
            print(f"\n{CYAN}Soul State Update{RESET}")
            for line in sup["content"].splitlines()[:5]:
                print(f"  {line[:100]}")
        else:
            print(f"\n{YELLOW}Soul State Update: MISSING (check was true){RESET}")

    # Issues
    if issues:
        print(f"\n{RED}Issues:{RESET}")
        for issue in issues:
            print(f"  - {issue}")

    print()
    return passed, total, elapsed


# -- Test runner -------------------------------------------------------------

def run_test(provider: str, model: str, user_msg: str, assistant_msg: str,
             show_raw: bool = False, show_prompt: bool = False) -> tuple[int, int, float]:
    """Run a single reflection test against a live model."""
    prompt = build_reflection_prompt(
        user_message=user_msg,
        assistant_response=assistant_msg,
        user_id="tom",
        channel="terminal:bench-session",
        thread_ts="bench-session",
        display_name="Tom",
    )

    if show_prompt:
        print(f"\n{DIM}--- PROMPT ({len(prompt)} chars) ---{RESET}")
        print(prompt)
        print(f"{DIM}--- END PROMPT ---{RESET}")

    t0 = time.time()
    try:
        raw = _call_llm(prompt, provider=provider, model=model)
    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n{RED}{'='*70}{RESET}")
        print(f"{RED}{provider} / {model}{RESET}")
        print(f"{RED}FAILED ({elapsed:.2f}s): {e}{RESET}")
        print(f"{'='*70}\n")
        return 0, 1, elapsed

    elapsed = time.time() - t0
    return display_result(provider, model, raw, elapsed, show_raw)


# -- CLI ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark reflection cognitive pipeline against any LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                              # Default model
  %(prog)s -p groq -m qwen/qwen3-32b                   # Specific model
  %(prog)s --compare groq:moonshotai/kimi-k2-instruct groq:meta-llama/llama-4-scout-17b-16e-instruct
  %(prog)s -u "Hello" -a "Hi there"                     # Custom exchange
  %(prog)s --raw                                        # Show raw XML
  %(prog)s --show-prompt                                # Show full prompt
        """,
    )
    parser.add_argument("-p", "--provider", default="", help="Provider (groq, openrouter)")
    parser.add_argument("-m", "--model", default="", help="Model ID")
    parser.add_argument("-c", "--compare", nargs="+", metavar="PROVIDER:MODEL",
                        help="Compare models (format: provider:model)")
    parser.add_argument("-u", "--user", default=DEFAULT_USER, help="User message")
    parser.add_argument("-a", "--assistant", default=DEFAULT_ASSISTANT, help="Assistant response")
    parser.add_argument("--raw", action="store_true", help="Show raw XML response")
    parser.add_argument("--show-prompt", action="store_true", help="Show full prompt")
    parser.add_argument("--list", action="store_true", help="List available providers")

    args = parser.parse_args()

    if args.list:
        print(f"\n{BOLD}Providers:{RESET}")
        for name, (url, key_env, _) in _PROVIDERS.items():
            has_key = bool(_resolve_api_key(key_env))
            status = f"{GREEN}key found{RESET}" if has_key else f"{RED}no key{RESET}"
            print(f"  {CYAN}{name}{RESET}: {url}")
            print(f"    {key_env}: {status}")
        print(f"\n{DIM}Default: {config.REFLECT_PROVIDER} / {config.REFLECT_MODEL}{RESET}\n")
        return

    print(f"\n{BOLD}Claudicle Reflection Benchmark{RESET}")
    print(f"{DIM}Exchange:{RESET}")
    print(f"  {DIM}Tom:{RESET} {args.user[:80]}{'...' if len(args.user) > 80 else ''}")
    print(f"  {DIM}Claudius:{RESET} {args.assistant[:80]}{'...' if len(args.assistant) > 80 else ''}")

    if args.compare:
        results = []
        for spec in args.compare:
            prov, mod = spec.split(":", 1) if ":" in spec else (spec, "")
            p, t, e = run_test(prov, mod, args.user, args.assistant, args.raw, args.show_prompt)
            results.append((spec, p, t, e))

        # Summary table
        print(f"\n{BOLD}{'='*70}{RESET}")
        print(f"{BOLD}COMPARISON{RESET}")
        print(f"{'='*70}")
        print(f"  {'Model':<50} {'Score':>6} {'Time':>7}")
        print(f"  {'-'*50} {'-'*6} {'-'*7}")
        for spec, p, t, e in results:
            color = GREEN if p == t else (YELLOW if p >= t - 1 else RED)
            print(f"  {spec:<50} {color}{p}/{t}{RESET}   {e:.2f}s")
        print()
    else:
        provider = args.provider or config.REFLECT_PROVIDER
        model = args.model or config.REFLECT_MODEL
        run_test(provider, model, args.user, args.assistant, args.raw, args.show_prompt)


if __name__ == "__main__":
    main()
