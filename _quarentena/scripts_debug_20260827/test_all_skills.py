import sys
sys.path.insert(0, '.')
from core.trust_gate import trust_gate
from pathlib import Path
import json

manifest_path = Path('config/skill_manifest.json')
with open(manifest_path, 'r') as f:
    manifest = json.load(f)

for skill in ['malicious_skill', 'hello_skill', 'web_search', 'system_control']:
    print(f'\n--- Testing {skill} ---')
    skill_path = Path(f'skills/{skill}.py')
    approved, errors = trust_gate(skill, skill_path, manifest)
    print(f'Approved: {approved}')
    print(f'Errors: {errors}')