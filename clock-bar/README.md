# Clock Bar

Oven-timer bars for Claude Code, in the status line. Extends the `/clock` skill. Built on [eta-bar](https://github.com/DrEvil-TitaniumHelix/eta-bar) by DrEvil (MIT).

![Clock bar in the status line: green running, orange paused, red overdue, yellow sub-agent](preview.svg)

- **One bar per task, one per sub-agent**, all on the same status line. A sub-agent's bar is named after its description (`Write the parser`), not its type, so two general-purpose agents never look alike.
- **Paused = the clock stops.** Claude pauses when it waits on something (`pause "why"`), a more urgent task takes over (`push`), or a permission prompt / question is open (automatic, "waiting on you"). Waiting never counts as overdue.
- **Overdue check-ins** at the deadline, +30 s, +1 min, +2 min, +4 min, then every 8 min. You see a `clock bar:` line in the chat (hook `systemMessage`, any platform) plus a desktop notification (Windows toast, `notify-send` on Linux) from a detached watcher. Claude gets an `OVERDUE` note at its next tool call: the main agent for its own task and for sub-agents, each sub-agent for itself, so a note is never swallowed by the wrong agent.
- Forgot to post an ETA? After 30 s of work a hook reminds Claude, then every 2 min.
- A turn ending does not wipe the bars while a background job or a sub-agent is still running.

## Commands (Claude runs these)
`set "note" 8 [--id ID]` · `push "note" 8` · `done [--id ID]` · `pause "why" [--id ID]` · `resume [--id ID]`
Time accepts `8` (minutes), `90s`, `2h` or `07:48`.

## Install
1. Copy this folder anywhere, e.g. `~/.claude/clock-bar/`.
2. Add the hooks from `hooks/hooks.json` to `~/.claude/settings.json`, replacing `${CLAUDE_PLUGIN_ROOT}` with the real path.
3. Add the status line: `"statusLine": {"type": "command", "command": "python <path>/statusline.py", "refreshInterval": 5}`. Already have one? Append the output of `python clockbar.py line <session_id>`.
4. Use the updated `clock/SKILL.md` so Claude knows the commands.

Check: `python clockbar.py selftest`. State lives in `~/.claude/clockbar/<session_id>.json`. Python 3, stdlib only. Notifications are Windows only; the bars work anywhere.
