import sys
sys.path.insert(0, '.')
from core.actions import os_ops, media_apps, browser, files, code, system, terminal, vision, web, scheduler, windows_radios, aprendizado_acoes, ponte_claude
from core.action_registry import get_registry
reg = get_registry()
actions = reg.list_actions()
print(f'Total actions: {len(actions)}')
for a in sorted(actions):
    spec = reg.get_spec(a)
    print(f'  {a}: risk={spec.risk}, capability={spec.capability}, category={spec.category}')