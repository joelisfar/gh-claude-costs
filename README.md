# gh-claude-costs

A [GitHub CLI](https://cli.github.com/) extension that reads your local Claude Code session logs and opens a cost breakdown dashboard in your browser.

No external dependencies — pure Python stdlib and vanilla JS, no build step, no npm.

![Dashboard screenshot showing spend by model, session counts, cache hit rates, and per-bucket cost tables](https://github.com/joelisfar/gh-claude-costs/assets/screenshot.png)

## Install

```bash
gh extension install joelisfar/gh-claude-costs
```

**Requirements:** `python3` (stdlib only, no pip packages), macOS or Linux, [Claude Code](https://claude.ai/code) installed (provides `~/.claude/projects/`).

## Usage

```bash
# Current month (default)
gh claude-costs

# Since a specific date
gh claude-costs --since 2026-04-01
```

The dashboard opens automatically in your default browser. Nothing is sent anywhere — all data stays local.

## What it shows

**Summary cards** — total spend, session starts, warm vs cold cache turns, compaction count.

**Human turns table** — input costs (base input, cache write, cache read) broken down by model and cache bucket (session start / warm / cold).

**LLM actions table** — agent output costs and subagent costs (input + output) per model.

**Grand total** — human-turn input costs + agent output + all subagent costs.

## How it works

1. Globs `~/.claude/projects/**/*.jsonl` (session logs written by Claude Code)
2. Deduplicates API calls by `requestId`, classifies each turn as warm/cold/session-start based on cache token ratios
3. Injects the JSON summary into an HTML template and opens it

## Uninstall

```bash
gh extension remove gh-claude-costs
```
