# gh-claude-costs

> **Disclaimer:** This was heavily vibecoded. It works on my machine. PRs welcome, sympathy also welcome.

A [GitHub CLI](https://cli.github.com/) extension that reads your local Claude Code session logs and opens a cost breakdown dashboard in your browser.

No external dependencies — pure Python stdlib and vanilla JS, no build step, no npm.

## Quick start

```bash
# Step 1: Install the extension (one-time)
gh extension install joelisfar/gh-claude-costs

# Step 2: Run it
gh claude-costs
```

This is a two-step process — `gh extension install` sets up the command, then `gh claude-costs` runs it. The server stays running until you Ctrl+C.

**Requirements:** `python3` (stdlib only, no pip packages), macOS or Linux, [GitHub CLI](https://cli.github.com/), and [Claude Code](https://claude.ai/code) session logs at `~/.claude/projects/`.

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
3. Injects the JSON summary into an HTML template, serves it on localhost, and opens your browser

## Uninstall

```bash
gh extension remove gh-claude-costs
```
