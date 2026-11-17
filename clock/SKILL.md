---
name: clock
description: Activates Time-Aware Mode for the session. Use this automatically when about to run servers, builds, installs, SSH commands, Docker operations, tests, database migrations, or any long-running process. Prevents Claude from hanging indefinitely or killing processes too early.
---

# Clock — Time-Aware Mode

You are now in **Time-Aware Mode** for this session. These rules apply to every Bash call you make from this point forward. Do not wait for the user to remind you — apply them automatically.

---

## Core Rules

1. **Always set a `timeout`** on Bash calls that could block. Never leave a potentially long-running command without a timeout parameter.
2. **Never blame the process for a timeout.** If a timeout fires, say: *"Timed out after Xs — the process may just need more time, not necessarily broken."* Then offer options.
3. **Dev servers and daemons must run in background.** Use `run_in_background: true` + a poll loop to detect readiness. Never block on a server start.
4. **Report elapsed time** in status updates for tasks you expect to take more than 30 seconds.
5. **At the halfway point** of any task expected to take >90s, give a brief progress update.
6. **Never silently retry** a timed-out command. Always tell the user it timed out first.

7. **Post the estimate on the clock bar** (`clock-bar/clockbar.py`, wired in settings.json, see `clock-bar/README.md`). It is an oven timer in the status line, one bar per task and per sub-agent.

---

## Clock Bar

CLI: `python <path to clock-bar>/clockbar.py <cmd>`

| Situation | Command |
|---|---|
| Before a long process (minutes = the long end; the table below gives the numbers) | `set "<3-6 words>" <minutes>`, again when the estimate slips |
| Waiting on something you don't control (background job, a person) | `pause "<why>"`, then `resume`: the timer stops, the bar turns orange |
| A more urgent task takes over | `push "<note>" <minutes>`: the old bar pauses (orange); `done` when it ends and the old one resumes |
| Sub-agent | gets its own bar from the SubagentStart hook with its id; it can `pause --id agent:xxxxxx` / `resume --id ...` |

Hooks pause every bar by themselves when a permission prompt or a question to the user is open (reason: "waiting on you") and resume on the next tool call or prompt.

**Overdue:** check-ins at the deadline, +30 s, +1 min, +2 min, +4 min, then every 8 min. The user gets a Windows notification; you get an `OVERDUE` note from the next hook. Finish, re-estimate with `set`, or say why it needs more time. Never ignore it.

**No ETA posted?** After 30 s of work a hook reminds you, then every 2 min. Post one.

---

## Timeout Reference Table

Use this table to pick the right timeout. When in doubt, **round up** — it is always better to wait a little longer than to kill a working process.

| Category | Examples | Timeout |
|---|---|---|
| Package install | `npm install`, `yarn`, `pnpm install`, `pip install`, `composer install`, `bundle install` | **180s** |
| Light build | `tsc`, `esbuild`, `vite build`, `rollup` | **120s** |
| Heavy build | `next build`, `webpack`, `cargo build`, `docker build`, `gradle build`, `mvn package` | **360s** |
| Dev server startup | `npm run dev`, `next dev`, `vite`, `rails s`, `flask run`, `uvicorn` | **background + poll** |
| Unit tests (fast) | `jest --testPathPattern`, `pytest test_single.py`, `go test ./pkg/...` | **120s** |
| Full test suite | `jest`, `pytest`, `cargo test`, `rspec`, `phpunit` | **300s** |
| SSH command | any `ssh host command` | **30s** |
| HTTP / curl | `curl`, `wget`, API calls | **30s** |
| Database migration | `prisma migrate`, `knex migrate`, `alembic upgrade`, `rails db:migrate` | **120s** |
| Docker Compose | `docker compose up`, `docker compose down`, `docker compose build` | **180s** |
| Git clone | `git clone` | **120s** |
| Git operations | `git pull`, `git push`, `git fetch` | **30s** |
| Generic shell | anything not listed above | **30s** |

---

## Dev Server Pattern (Non-Blocking)

Never run a dev server as a blocking call. Use this pattern instead:

```bash
# Step 1 — start in background
# Bash call: run_in_background: true, no timeout needed
npm run dev

# Step 2 — poll for readiness (repeat up to ~20 times, 3s apart = 60s max)
# Bash call: timeout 5s
curl -s http://localhost:PORT/ > /dev/null && echo "READY" || echo "NOT_YET"
```

Tell the user when the server is ready. If it's not ready after 60s of polling, report it rather than assuming failure.

---

## When a Timeout Fires

**Never say:**
- "The command failed"
- "The server didn't start"
- "Something is wrong"

**Always say:**
> "The command timed out after Xs. This doesn't necessarily mean it failed — it may just need more time. Options: (a) I can run it in background and monitor it, (b) you can run it manually and tell me when it's done, (c) I can retry with a longer timeout."

Then wait for the user's instruction before retrying.

---

## Auto-Activation

Invoke `/clock` automatically at the start of any session where you are about to:
- Start or restart a server / daemon
- Run a build (any language/framework)
- Install dependencies
- Connect via SSH
- Run a test suite
- Run Docker Compose operations
- Execute database migrations

You do not need to announce that you are invoking it — just apply the rules silently and continue with the task.
