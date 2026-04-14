#!/usr/bin/env python3
"""Extract Claude Code usage data from local JSONL session files.

Reads ~/.claude/projects/**/*.jsonl, deduplicates by requestId,
classifies human turns as warm/cold_start/cold_expired, and outputs
a JSON blob suitable for the dashboard template.

Usage:
    python3 extract.py [--since YYYY-MM-DD]
"""

import argparse
import glob
import json
import os
import sys
from collections import defaultdict


PRICING = {
    "claude-opus-4-6":   {"base": 5.00, "cache_write": 6.25, "cache_read": 0.50, "output": 25.00},
    "claude-opus-4-5":   {"base": 5.00, "cache_write": 6.25, "cache_read": 0.50, "output": 25.00},
    "claude-opus-4":     {"base": 15.00, "cache_write": 18.75, "cache_read": 1.50, "output": 75.00},
    "claude-sonnet-4-6": {"base": 3.00, "cache_write": 3.75, "cache_read": 0.30, "output": 15.00},
    "claude-sonnet-4-5": {"base": 3.00, "cache_write": 3.75, "cache_read": 0.30, "output": 15.00},
    "claude-sonnet-4":   {"base": 3.00, "cache_write": 3.75, "cache_read": 0.30, "output": 15.00},
    "claude-haiku-4-5":  {"base": 0.80, "cache_write": 1.00, "cache_read": 0.08, "output": 4.00},
    "claude-haiku-3-5":  {"base": 0.80, "cache_write": 1.00, "cache_read": 0.08, "output": 4.00},
}


def normalize_model(model_id):
    """Normalize model IDs like 'claude-haiku-4-5-20251001' to 'claude-haiku-4-5'."""
    if model_id.startswith("<"):
        return None  # skip <synthetic> etc
    # Strip date suffixes (e.g., -20251001)
    import re
    return re.sub(r"-\d{8,}$", "", model_id)


def is_human_turn(obj):
    """Check if a user-type entry represents an actual human turn."""
    if obj.get("isCompactSummary"):
        return False
    content = obj.get("message", {}).get("content", "")
    if isinstance(content, str) and content.strip():
        return True
    if isinstance(content, list):
        has_text = any(
            isinstance(c, dict) and c.get("type") == "text"
            for c in content
        )
        all_tool_results = all(
            isinstance(c, dict) and c.get("type") == "tool_result"
            for c in content
        )
        return has_text and not all_tool_results
    return False


def find_jsonl_files():
    """Find all JSONL files under ~/.claude/projects/."""
    base = os.path.expanduser("~/.claude/projects")
    return glob.glob(os.path.join(base, "**", "*.jsonl"), recursive=True)


def extract(since_date):
    """Extract and classify usage data."""
    files = find_jsonl_files()
    if not files:
        print("No JSONL files found in ~/.claude/projects/", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {len(files)} JSONL files...", file=sys.stderr)

    # Parse all entries
    all_entries = []
    compactions = {"auto": 0, "manual": 0}
    for fpath in files:
        with open(fpath, "r") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    ts = obj.get("timestamp", "")
                    if ts < since_date:
                        continue
                    entry_type = obj.get("type", "")
                    if entry_type in ("user", "assistant"):
                        all_entries.append(obj)
                    elif entry_type == "system" and obj.get("subtype") == "compact_boundary":
                        trigger = obj.get("compactMetadata", {}).get("trigger", "auto")
                        compactions[trigger] = compactions.get(trigger, 0) + 1
                except (json.JSONDecodeError, KeyError):
                    continue

    print(f"Parsed {len(all_entries)} entries since {since_date}", file=sys.stderr)

    # Deduplicate assistant entries by requestId
    seen_requests = {}
    for obj in all_entries:
        if obj.get("type") != "assistant":
            continue
        rid = obj.get("requestId", "")
        stop = obj.get("message", {}).get("stop_reason")
        if rid:
            if rid not in seen_requests or stop is not None:
                seen_requests[rid] = id(obj)

    # Build session timelines
    sessions = defaultdict(list)
    for obj in all_entries:
        sid = obj.get("sessionId", "")
        ts = obj.get("timestamp", "")
        entry_type = obj.get("type", "")
        agent_id = obj.get("agentId")
        is_subagent = agent_id is not None

        if entry_type == "user" and is_human_turn(obj):
            sessions[sid].append(
                ("human", ts, None, None, None, None, None, is_subagent, agent_id)
            )
        elif entry_type == "assistant":
            rid = obj.get("requestId", "")
            include = (rid and seen_requests.get(rid) == id(obj)) or not rid
            if include:
                usage = obj.get("message", {}).get("usage", {})
                raw_model = obj.get("message", {}).get("model", "")
                model = normalize_model(raw_model) if raw_model else None
                if usage and model:
                    sessions[sid].append((
                        "assistant", ts, model,
                        usage.get("cache_creation_input_tokens", 0),
                        usage.get("cache_read_input_tokens", 0),
                        usage.get("output_tokens", 0),
                        usage.get("input_tokens", 0),
                        is_subagent, agent_id,
                    ))

    # Classify turns
    stats = defaultdict(
        lambda: defaultdict(
            lambda: {"input": 0, "cache_write": 0, "cache_read": 0,
                     "output": 0, "human_turns": 0, "messages": 0}
        )
    )
    active_days = set()
    main_sessions = set()

    subagent_session_count = 0

    for sid, msgs in sessions.items():
        msgs.sort(key=lambda x: x[1])
        first_human_seen_main = False
        first_human_seen_agents = set()  # track per agentId
        bucket = None

        for i, m in enumerate(msgs):
            if m[0] == "human":
                is_sub = m[7]
                agent_id = m[8]
                source = "subagent" if is_sub else "main"

                if not is_sub:
                    main_sessions.add(sid)
                    active_days.add(m[1][:10])

                is_first = False
                if not is_sub and not first_human_seen_main:
                    is_first = True
                    first_human_seen_main = True
                elif is_sub and agent_id and agent_id not in first_human_seen_agents:
                    is_first = True
                    first_human_seen_agents.add(agent_id)
                    subagent_session_count += 1

                bucket = None
                for j in range(i + 1, len(msgs)):
                    if msgs[j][0] == "human":
                        break
                    if msgs[j][0] == "assistant" and msgs[j][2]:
                        creation = msgs[j][3] or 0
                        read = msgs[j][4] or 0
                        total_cache = creation + read
                        model = msgs[j][2]
                        key = f"{model}|{source}"

                        if is_first:
                            bucket = "cold_start"
                        elif total_cache > 0 and read / total_cache > 0.9:
                            bucket = "warm"
                        else:
                            bucket = "cold_expired"

                        stats[key][bucket]["human_turns"] += 1
                        break

            elif m[0] == "assistant" and bucket and m[2]:
                source = "subagent" if m[7] else "main"
                model = m[2]
                key = f"{model}|{source}"
                stats[key][bucket]["input"] += m[6] or 0
                stats[key][bucket]["cache_write"] += m[3] or 0
                stats[key][bucket]["cache_read"] += m[4] or 0
                stats[key][bucket]["output"] += m[5] or 0
                stats[key][bucket]["messages"] += 1

    # Build output
    sections = {}
    for key in sorted(stats.keys()):
        section = {}
        for b in ("warm", "cold_start", "cold_expired"):
            d = stats[key].get(b)
            section[b] = dict(d) if d else {
                "input": 0, "cache_write": 0, "cache_read": 0,
                "output": 0, "human_turns": 0, "messages": 0,
            }
        sections[key] = section

    # Only include pricing for models actually seen
    seen_models = set(k.split("|")[0] for k in sections)
    pricing = {m: PRICING[m] for m in seen_models if m in PRICING}

    result = {
        "meta": {
            "totalSessions": len(main_sessions),
            "subagentSessions": subagent_session_count,
            "activeDays": len(active_days),
            "dateRange": [min(active_days), max(active_days)] if active_days else [],
            "compactions": compactions,
        },
        "pricing": pricing,
        "sections": sections,
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="Extract Claude Code usage data")
    parser.add_argument(
        "--since",
        default=None,
        help="Start date (YYYY-MM-DD). Defaults to first of current month.",
    )
    args = parser.parse_args()

    if args.since:
        since_date = args.since
    else:
        from datetime import date
        today = date.today()
        since_date = today.replace(day=1).isoformat()

    data = extract(since_date)
    print(json.dumps(data))


if __name__ == "__main__":
    main()
