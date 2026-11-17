# statusline.py - minimal Claude Code status line: directory | model | clock bars. Stdlib only.
# settings.json:  "statusLine": {"type": "command", "command": "python \"<path>/statusline.py\"", "refreshInterval": 5}
# Already have a status line? Append the output of  python clockbar.py line <session_id>  to yours.
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import clockbar
if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')
j = json.load(sys.stdin)
E = '\x1b['
d = j.get('workspace', {}).get('current_dir', '').replace(str(Path.home()), '~')
m = j.get('model', {}).get('display_name', '')
parts = [f'{E}36m{d}{E}0m', f'{E}1;33m{m}{E}0m', clockbar.line(j.get('session_id', ''))]
print(f'  {E}90m|{E}0m  '.join(x for x in parts if x))
