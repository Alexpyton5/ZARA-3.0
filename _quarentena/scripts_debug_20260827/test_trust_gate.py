import sys
sys.path.insert(0, '.')
from core.trust_gate import trust_gate
from pathlib import Path
import json

skill_name = 'code_helper'
skill_path = Path('skills/code_helper.py')
manifest_path = Path('config/skill_manifest.json')
with open(manifest_path, 'r') as f:
    manifest = json.load(f)
print('Manifest loaded:', manifest)
print('Skill name:', skill_name)
print('Skill in manifest?', skill_name in manifest)
if skill_name in manifest:
    print('Expected hash:', manifest[skill_name])
approved, errors = trust_gate(skill_name, skill_path, manifest)
print('Approved:', approved)
print('Errors:', errors)