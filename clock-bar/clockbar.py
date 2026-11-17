# clockbar.py - oven-timer bars for Claude Code: a countdown bar per task and per sub-agent.
# Builds on eta-bar by DrEvil (MIT). Stdlib only.
# State: ~/.claude/clockbar/<session_id>.json, one file per session. Each task has a budget and an
# ACTIVE clock: pausing stops it, resuming restarts it, so waiting never counts as "overdue".
#  hooks  : brief | busy | tick | wait | ready | agent-queue | agent-start | agent-stop   (stdin JSON from Claude Code)
#  model  : set "note" 8 [--id ID] | push "note" 8 | done [--id ID] | pause "why" | resume   (needs CLAUDE_CODE_SESSION_ID)
#  bar    : line <session_id>
#  other  : watch <session_id> (detached toaster, started by the hooks) | selftest
import sys, os, json, time, re, argparse, contextlib, subprocess, shutil
from pathlib import Path
if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

D = Path(os.environ.get('CLOCKBAR_DIR') or Path.home() / '.claude' / 'clockbar')
D.mkdir(parents=True, exist_ok=True)
E = '\x1b['
GREEN, YELLOW, RED, ORANGE, GREY = '32', '33', '1;31', '38;5;208', '90'
WAITING = 'waiting on you'
STEPS = [0, 30, 60, 120, 240]      # overdue check-ins: at the deadline, +30 s, +1 min, +2 min, +4 min, then every 8 min
AGENT_MIN = {'Explore': 3, 'Plan': 4, 'general-purpose': 8, 'web-fetch': 2}
HOOK_SECS = 5
NUDGE_AFTER, NUDGE_EVERY = 30, 120   # no ETA posted this long into a turn -> remind Claude, then every 2 min


# ---------- state ----------
def _path(sid): return D / f'{sid}.json'

def load(sid):
    try:
        return json.load(open(_path(sid), encoding='utf-8'))
    except Exception:
        return {}

def save(sid, s):
    s['updated'] = time.time()
    tmp = D / f'{sid}.{os.getpid()}.tmp'
    json.dump(s, open(tmp, 'w', encoding='utf-8'))
    os.replace(tmp, _path(sid))

@contextlib.contextmanager
def locked(sid):
    lock, t0 = D / f'{sid}.lock', time.time()
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL)); break
        except FileExistsError:
            if time.time() - t0 > 2:       # stale lock from a killed process
                with contextlib.suppress(OSError): lock.unlink()
                t0 = time.time()
            time.sleep(0.02)
    try:
        s = load(sid); yield s; save(sid, s)
    finally:
        with contextlib.suppress(OSError): lock.unlink()


# ---------- tasks ----------
def new_task(s, tid, kind, note, budget, now):
    t = dict(id=tid, kind=kind, note=note, budget=budget, acc=0.0, run_since=now, state='running',
             reason='', by='', ctx_n=0, main_n=0, usr_n=0, toast_n=0, created=now)
    s['tasks'] = [x for x in s.get('tasks', []) if x['id'] != tid] + [t]
    return t

def elapsed(t, now): return t['acc'] + ((now - t['run_since']) if t.get('run_since') else 0)
def left(t, now): return t['budget'] - elapsed(t, now)
def live(s): return [t for t in s.get('tasks', []) if t['state'] in ('running', 'paused')]
def find(s, tid): return next((t for t in live(s) if t['id'] == tid), None)

def pause(t, now, reason, by=''):
    if t['state'] == 'running':
        t.update(acc=elapsed(t, now), run_since=None, state='paused', reason=reason, by=by)

def resume(t, now):
    if t['state'] == 'paused':
        t.update(run_since=now, state='running', reason='', by='')

def finish(s, t, now):
    pause(t, now, '')
    t['state'] = 'done'
    for o in live(s):                       # whatever this task preempted gets its clock back
        if o['by'] == t['id']: resume(o, now)

def due_count(t, now):
    """How many overdue check-ins are due by now (0 if not overdue or not running)."""
    if t['state'] != 'running': return 0
    over, n, at = -left(t, now), 0, 0
    while True:
        at += STEPS[n] if n < len(STEPS) else 480
        if over < at: return n
        n += 1

def minutes(w, now):
    m = re.fullmatch(r'(\d{1,2}):(\d{2})', w)
    if m:
        t = time.localtime(now); eta = time.mktime(t[:3] + (int(m[1]), int(m[2]), 0) + t[6:])
        return (eta + 86400 * (eta < now - 600) - now) / 60
    m = re.fullmatch(r'(\d+(?:\.\d+)?)([smh]?)', w)
    if not m: sys.exit(f'bad time "{w}": use 8, 90s, 2h or 07:48')
    return float(m[1]) * {'s': 1 / 60, 'm': 1, 'h': 60, '': 1}[m[2]]


# ---------- rendering ----------
def fmt(sec):
    sec = int(abs(sec))
    if sec >= 3600: return f'{sec // 3600} h {sec % 3600 // 60:02d} min'
    return f'{sec // 60} min {sec % 60:02d} s' if sec >= 60 else f'{sec} s'

def bar(frac, w):
    f = max(0, min(w, round(frac * w)))
    return '█' * f + '░' * (w - f)

def seg(t, now):
    el, l = elapsed(t, now), left(t, now)
    frac = el / t['budget'] if t['budget'] > 0 else 1
    if t['state'] == 'paused':
        c, tail = ORANGE, f"paused · {t['reason']} · {fmt(l)} {'left' if l >= 0 else 'over'}"
    elif l < 0:
        c, tail = RED, f'OVERDUE {fmt(l)}'
    else:
        c, tail = (YELLOW if l < 0.2 * t['budget'] else GREEN), f'{fmt(l)} left'
    agent = t['kind'] == 'agent'
    name = ('> ' if agent else '') + (t['note'] or 'working')[:28]
    return f"{E}{c}m{name} [{bar(frac, 6 if agent else 12)}] {tail}{E}0m"

def line(sid, now=None):
    now, s = now or time.time(), load(sid)
    if not s: return ''
    ts = sorted(live(s), key=lambda t: t['kind'] == 'agent')
    if ts: return f'  {E}90m│{E}0m  '.join(seg(t, now) for t in ts[:4])
    if s.get('state') == 'ready':
        return f"{E}1;32m✓ ready for you · since {time.strftime('%H:%M', time.localtime(s.get('ready_at', now)))}{E}0m"
    if s.get('state') == 'busy':
        el = int(now - s.get('since', now))
        return f'{E}{GREY}mworking · no ETA yet · {fmt(el)}{E}0m'
    return ''


# ---------- delivery ----------
def toast(title, text):
    if os.name != 'nt':
        if shutil.which('notify-send'):
            subprocess.Popen(['notify-send', '-u', 'critical', title, text], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;$n=New-Object System.Windows.Forms.NotifyIcon;"
          "$n.Icon=[System.Drawing.SystemIcons]::Warning;$n.Visible=$true;"
          "$n.ShowBalloonTip(9000,$env:CB_T,$env:CB_M,'Warning');Start-Sleep 10;$n.Dispose()")
    subprocess.Popen(['powershell', '-NoProfile', '-WindowStyle', 'Hidden', '-Command', ps],
                     env={**os.environ, 'CB_T': title, 'CB_M': text}, creationflags=0x08000000,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def start_watcher(sid, s, now):
    if now - s.get('beat', 0) < 15: return
    s['beat'] = now
    kw = dict(creationflags=0x08000208, close_fds=True) if os.name == 'nt' else dict(start_new_session=True)
    subprocess.Popen([sys.executable, __file__, 'watch', sid], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, **kw)

def watch(sid):
    while True:
        now = time.time()
        with locked(sid) as s:
            s['beat'] = now
            ts = live(s)
            for t in ts:
                n = due_count(t, now)
                if n > t['toast_n']:
                    t['toast_n'] = n
                    toast('Claude is over time', f"{t['note'] or t['id']}: {fmt(left(t, now))} over. Extend, finish or stop?")
            if not ts or now - s.get('updated', now) > 4 * 3600: return
        time.sleep(HOOK_SECS)

def notes(s, now, agent_id=''):
    """-> (for Claude, for the user). The user sees every check-in in the chat; the agent that can act on it is told once."""
    ctx, usr = [], []
    for t in live(s):
        n = due_count(t, now)
        if n == 0: continue
        over, name = fmt(left(t, now)), t['note'] or t['id']
        if n > t.get('usr_n', 0):
            t['usr_n'] = n; usr.append(f"clock bar: '{name}' is {over} over its estimate")
        if t['kind'] == 'agent':
            if agent_id and t['id'] == f'agent:{agent_id[:6]}':
                if n > t.get('ctx_n', 0):
                    t['ctx_n'] = n; ctx.append(f"OVERDUE: you ('{name}') are {over} past your estimate. Wrap up and report, or run `clockbar set --id {t['id']} \"<note>\" <minutes>`.")
            elif not agent_id and n > t.get('main_n', 0):
                t['main_n'] = n; ctx.append(f"OVERDUE: sub-agent '{name}' is {over} past its estimate. Check on it, extend it with `clockbar set --id {t['id']} ...`, and tell the user.")
        elif not agent_id and n > t.get('ctx_n', 0):
            t['ctx_n'] = n; ctx.append(f"OVERDUE: '{name}' is {over} past its estimate (check-in {n}). Finish, re-estimate with `clockbar set`, or tell the user why it needs more time.")
    return ctx, usr

def emit(event, ctx, usr=()):
    out = {}
    if ctx: out['hookSpecificOutput'] = {'hookEventName': event, 'additionalContext': ' '.join(ctx)}
    if usr: out['systemMessage'] = ' | '.join(usr)
    if out: print(json.dumps(out))


# ---------- commands ----------
BRIEF = ("Clock bar is on. Before any batch of work longer than a few seconds run `python \"%(p)s\" set \"<3-6 words>\" <minutes>` "
         "(use the long end; /clock's timeout table gives the numbers) and run it again when the estimate slips. "
         "Waiting on something outside your control (background job, a person)? `python \"%(p)s\" pause \"<why>\"`, and `resume` after: "
         "the timer stops while paused. A more urgent task takes over? `push \"<note>\" <minutes>`, then `done` when it ends and the old one resumes. "
         "If a hook says OVERDUE: finish, re-estimate with `set`, or say why it needs more time.")

def payload():
    try: return json.load(sys.stdin)
    except Exception: return {}

def sid_of(j=None):
    return (j or {}).get('session_id') or os.environ.get('CLAUDE_CODE_SESSION_ID') or sys.exit('no CLAUDE_CODE_SESSION_ID')

def hook(cmd):
    j, now = payload(), time.time()
    sid = j.get('session_id') or os.environ.get('CLAUDE_CODE_SESSION_ID')
    if not sid: return
    ev = j.get('hook_event_name') or 'PostToolUse'
    with locked(sid) as s:
        if cmd == 'busy':
            if s.get('state') != 'busy':
                keep = lambda t: t['kind'] == 'agent' or s.get('bg')
                s['tasks'] = [t for t in live(s) if keep(t) and now - t.get('created', now) < 3600]
                s.update(state='busy', since=now, nudged=0)
            for t in live(s):
                if t['reason'] == WAITING: resume(t, now)
        elif cmd == 'tick':
            for t in live(s):
                if t['reason'] == WAITING: resume(t, now)
        elif cmd == 'wait':
            nt = j.get('notification_type', '')
            msg = (j.get('message') or '').lower()
            if nt and nt not in ('permission_prompt', 'elicitation_dialog') and 'permission' not in msg and 'input' not in msg:
                return
            for t in live(s): pause(t, now, WAITING)
        elif cmd == 'ready':
            # A turn ending is not the work ending: keep bars while a background job or a sub-agent still runs.
            bg = bool(j.get('background_tasks'))
            for t in live(s):
                if t['kind'] == 'main' and not bg: finish(s, t, now)
            s.update(state='ready', ready_at=now, bg=bg)
        elif cmd == 'agent-queue':
            # PreToolUse on the Agent tool: remember its description so the bar gets a name a human can tell apart.
            ti = j.get('tool_input') or {}
            q = [x for x in s.get('pending', []) if now - x['t'] < 120]
            q.append(dict(type=ti.get('subagent_type') or 'general-purpose', desc=ti.get('description') or '', t=now))
            s['pending'] = q
        elif cmd == 'agent-start':
            aid, typ = j.get('agent_id', '?'), j.get('agent_type') or 'agent'
            tid = f'agent:{aid[:6]}'
            q = s.get('pending', [])
            k = next((i for i, x in enumerate(q) if x['type'] == typ), None)
            desc = q.pop(k)['desc'] if k is not None else ''
            new_task(s, tid, 'agent', desc or typ, 60 * float(os.environ.get('CLOCKBAR_AGENT_MIN') or AGENT_MIN.get(typ, 5)), now)
            s.setdefault('state', 'busy'); s.setdefault('since', now)
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SubagentStart', 'additionalContext':
                  f"Your timer bar is `{tid}`. If you must wait on something, run `python \"{Path(__file__).resolve().as_posix()}\" pause --id {tid} \"<why>\"` "
                  f"and `resume --id {tid}` after; re-estimate with `set --id {tid} \"<note>\" <minutes>`."}}))
        elif cmd == 'agent-stop':
            t = find(s, f"agent:{j.get('agent_id', '?')[:6]}")
            if t: finish(s, t, now)
        if cmd in ('busy', 'tick', 'ready'):
            ctx, usr = notes(s, now, j.get('agent_id') or '')
            if cmd == 'ready': ctx = []        # a Stop hook must not feed Claude context: that would keep the turn going
            if (cmd == 'tick' and not j.get('agent_id') and s.get('state') == 'busy'
                    and not any(t['kind'] == 'main' for t in live(s))
                    and now - s.get('since', now) > NUDGE_AFTER and now - s.get('nudged', 0) > NUDGE_EVERY):
                s['nudged'] = now
                ctx.append(f"CLOCK BAR: this turn has run {fmt(now - s['since'])} with no ETA posted. "
                           f"Run `python \"{Path(__file__).resolve().as_posix()}\" set \"<3-6 words>\" <minutes>` now.")
            emit(ev, ctx, usr)
        if any(t['state'] == 'running' for t in live(s)): start_watcher(sid, s, now)

def manual(a):
    now, sid = time.time(), sid_of()
    with locked(sid) as s:
        s.setdefault('state', 'busy'); s.setdefault('since', now)
        tid = getattr(a, 'id', None) or 'main'
        if a.cmd == 'set':
            mins = minutes(a.minutes, now)
            t = find(s, tid)
            if t:
                resume(t, now)
                t.update(note=a.note, budget=elapsed(t, now) + mins * 60, ctx_n=0, main_n=0, usr_n=0, toast_n=0)
            else:
                t = new_task(s, tid, 'agent' if tid.startswith('agent:') else 'main', a.note, mins * 60, now)
            print(f"{t['id']}: {a.note} -> {fmt(mins * 60)} left")
        elif a.cmd == 'push':
            mins = minutes(a.minutes, now)
            tid = f"task{len(s.get('tasks', [])) + 1}"
            for t in live(s):
                if t['kind'] == 'main': pause(t, now, f'preempted by {a.note}', by=tid)
            new_task(s, tid, 'main', a.note, mins * 60, now)
            print(f"{tid}: {a.note} -> {fmt(mins * 60)} left (others paused)")
        elif a.cmd == 'pause':
            for t in ([find(s, a.id)] if a.id else [x for x in live(s) if x['kind'] == 'main']):
                if t: pause(t, now, a.reason)
            print('paused:', a.reason)
        elif a.cmd == 'resume':
            for t in ([find(s, a.id)] if a.id else live(s)):
                if t and not t['by']: resume(t, now)
            print('resumed')
        elif a.cmd == 'done':
            t = find(s, tid)
            if t: finish(s, t, now)
            print('done:', tid)
        if any(t['state'] == 'running' for t in live(s)): start_watcher(sid, s, now)

def selftest():
    import tempfile
    global D
    D = Path(tempfile.mkdtemp()); sid = 'st'; t0 = 1_000_000.0
    s = {}
    t = new_task(s, 'main', 'main', 'build', 600, t0)
    assert abs(left(t, t0 + 100) - 500) < 1e-6
    pause(t, t0 + 100, WAITING)
    assert abs(left(t, t0 + 5000) - 500) < 1e-6 and 'paused' in seg(t, t0 + 5000) and ORANGE in seg(t, t0 + 5000)
    resume(t, t0 + 5000); assert abs(left(t, t0 + 5100) - 400) < 1e-6
    assert due_count(t, t0 + 599) == 0 and due_count(t, t0 + 5000 + 500) == 1
    # check-ins: at deadline, +30 s, +1 min, +2 min, +4 min, then every 8 min
    d = t0 + 5000 + 500
    got = [due_count(t, d + x) for x in (0, 29, 30, 90, 210, 450, 929, 930)]
    assert got == [1, 1, 2, 3, 4, 5, 5, 6], got
    assert RED in seg(t, d + 10) and 'OVERDUE' in seg(t, d + 10)
    # preemption: push pauses main, done resumes it
    s = {}; a = new_task(s, 'main', 'main', 'A', 600, t0)
    b = new_task(s, 'task2', 'main', 'B', 60, t0 + 10); pause(a, t0 + 10, 'preempted by B', by='task2')
    assert a['state'] == 'paused' and abs(left(a, t0 + 999) - 590) < 1e-6
    finish(s, b, t0 + 70); assert a['state'] == 'running' and b['state'] == 'done'
    assert minutes('90s', 0) == 1.5 and minutes('2h', 0) == 120 and minutes('8', 0) == 8
    assert fmt(3720) == '1 h 02 min' and fmt(252) == '4 min 12 s' and fmt(7) == '7 s'
    save(sid, s); assert find(load(sid), 'main') and 'A' in line(sid, t0 + 100)
    # overdue routing: the user sees every check-in; only the right agent gets the note
    s = {}; m = new_task(s, 'main', 'main', 'build', 60, t0); g = new_task(s, 'agent:abc123', 'agent', 'Write parser', 60, t0)
    now = t0 + 100
    c, u = notes(s, now, '')                              # main agent's turn
    assert len(u) == 2 and len(c) == 2 and 'sub-agent' in c[1], (c, u)
    c, u = notes(s, now, 'abc123xyz')                     # the overdue sub-agent's own tool call
    assert u == [] and len(c) == 1 and c[0].startswith("OVERDUE: you"), (c, u)   # user not told twice; the agent itself is
    assert notes(s, now, '') == ([], []) and notes(s, now, 'abc123xyz') == ([], [])  # nothing repeats
    print('clockbar selftest OK')

def main():
    c = sys.argv[1] if len(sys.argv) > 1 else ''
    if c in ('busy', 'tick', 'wait', 'ready', 'agent-queue', 'agent-start', 'agent-stop'): return hook(c)
    if c == 'brief': return print(BRIEF % {'p': Path(__file__).resolve().as_posix()})
    if c == 'line': return print(line(sys.argv[2]))
    if c == 'watch': return watch(sys.argv[2])
    if c == 'selftest': return selftest()
    p = argparse.ArgumentParser(prog='clockbar')
    sp = p.add_subparsers(dest='cmd', required=True)
    for n in ('set', 'push'):
        q = sp.add_parser(n); q.add_argument('note'); q.add_argument('minutes')
        if n == 'set': q.add_argument('--id')
    q = sp.add_parser('pause'); q.add_argument('reason', nargs='?', default='waiting'); q.add_argument('--id')
    for n in ('resume', 'done'):
        q = sp.add_parser(n); q.add_argument('--id')
    manual(p.parse_args())

if __name__ == '__main__':
    main()
