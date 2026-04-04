<div align="center">

# ⏱ Claude Clock

**A Claude Code skill that gives Claude a sense of time.**

[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-orange?style=flat-square&logo=anthropic)](https://claude.ai/code)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

</div>

---

## The Problem

Claude Code is brilliant at writing and running code — but it has no concept of time.

It will happily run `npm run dev` and wait forever. It will SSH into a server and hang. It will launch a Docker build and block the entire session. When a timeout *does* fire, it often assumes the process failed and tells you something is broken — when in reality it just needed 10 more seconds.

**Claude Clock fixes this.**

---

## What It Does

Install this skill and invoke `/clock` once at the start of a session. From that point on, Claude will:

- **Always set timeouts** on Bash calls — no more infinite hangs
- **Use realistic timeouts** based on what the command actually does (installing packages gets 180s, not 30s)
- **Never blame a process** for a timeout — it always tells you "timed out, may just need more time"
- **Run dev servers in background** and poll for readiness instead of blocking
- **Report progress** on long tasks halfway through
- **Auto-activate** when it detects you're about to run a server, build, install, or SSH command

---

## Timeout Reference

The skill teaches Claude this table:

| Category | Examples | Timeout |
|---|---|---|
| Package install | `npm install`, `pip install`, `composer install` | 180s |
| Light build | `tsc`, `esbuild`, `vite build` | 120s |
| Heavy build | `next build`, `webpack`, `cargo build`, `docker build` | 360s |
| Dev server | `npm run dev`, `next dev`, `vite`, `flask run` | background + poll |
| Unit tests | `jest --testPathPattern`, `pytest test_single.py` | 120s |
| Full test suite | `jest`, `pytest`, `cargo test`, `rspec` | 300s |
| SSH command | any `ssh host command` | 30s |
| HTTP / curl | `curl`, `wget`, API calls | 30s |
| DB migration | `prisma migrate`, `knex migrate`, `alembic upgrade` | 120s |
| Docker Compose | `docker compose up/down/build` | 180s |
| Git clone | `git clone` | 120s |
| Git operations | `git pull`, `git push`, `git fetch` | 30s |
| Generic shell | anything not in the list | 30s |

When in doubt, Claude rounds **up** — it is always better to wait a little longer than to kill a working process.

---

## Install

```bash
# Clone the repo
git clone https://github.com/AntonioGison/claude-clock.git

# Copy the skill to your Claude skills directory
cp -r claude-clock/clock ~/.claude/skills/
```

> **Requirements:** [Claude Code](https://claude.ai/code) with skills support.

---

## Usage

Type `/clock` at the start of any session where you'll be running servers, builds, installs, or SSH commands:

```
/clock
```

That's it. Claude will apply the rules to every Bash call for the rest of the session.

You can also just start working — if Claude detects you're about to run a potentially blocking command, it will activate time-aware mode automatically.

---

## How It Works

`/clock` is a [Claude Code skill](https://claude.ai/code) — a markdown prompt loaded into the session context. It gives Claude a structured set of rules and a reference table it uses when deciding how long to wait for any given command.

The key insight is specificity: instead of a blanket "use timeouts", the skill gives Claude concrete values per command category, a pattern for non-blocking server startup, and explicit language to use when a timeout fires so it doesn't mislead you.

---

## Honest Timeout Behavior

When a timeout fires, Claude will never say *"the command failed"* or *"something is wrong"*. Instead it will say:

> *"Timed out after Xs — the process may just need more time, not necessarily broken. Options: (a) run in background and monitor, (b) you run it manually and tell me when it's done, (c) retry with a longer timeout."*

Then it waits for your instruction.

---

## License

MIT — use it, fork it, share it.
