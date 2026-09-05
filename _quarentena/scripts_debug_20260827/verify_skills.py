#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.plugin_loader import discover_plugins
from pathlib import Path

# Test that all 4 required skills are present and functional
skills_dir = Path('./skills')
core_tool_names = set()

def logger(msg):
    pass  # Suppress logging for clean output

print("=== SKILL VERIFICATION ===")
registry = discover_plugins(skills_dir, core_tool_names, logger)

required_skills = ['system_control', 'file_ops', 'web_search', 'code_helper']
missing_skills = []
working_skills = []

for skill_name in required_skills:
    if skill_name in registry._plugins:
        working_skills.append(skill_name)
        print(f"✓ {skill_name}: FOUND")
    else:
        missing_skills.append(skill_name)
        print(f"✗ {skill_name}: MISSING")

print(f"\n=== SUMMARY ===")
print(f"Required skills: {len(required_skills)}")
print(f"Found skills: {len(working_skills)}")
print(f"Missing skills: {len(missing_skills)}")

if missing_skills:
    print(f"Missing: {missing_skills}")
    sys.exit(1)
else:
    print("All required skills are present and registered!")
    
# Quick functionality test
print("\n=== FUNCTIONALITY TEST ===")
test_results = []

# Test system_control
try:
    result = registry.run('system_control', {'action': 'time'})
    if 'Agora são' in result:
        test_results.append(('system_control', 'PASS'))
    else:
        test_results.append(('system_control', f'FAIL: {result[:50]}'))
except Exception as e:
    test_results.append(('system_control', f'ERROR: {e}'))

# Test file_ops
try:
    result = registry.run('file_ops', {'action': 'list', 'path': '.'})
    if '"name"' in result and 'ABRIR-A-ZARA.bat' in result:
        test_results.append(('file_ops', 'PASS'))
    else:
        test_results.append(('file_ops', f'FAIL: {result[:50]}'))
except Exception as e:
    test_results.append(('file_ops', f'ERROR: {e}'))

# Test web_search
try:
    result = registry.run('web_search', {'query': 'test', 'max_results': 1})
    if 'resultado(s)' in result and 'test' in result:
        test_results.append(('web_search', 'PASS'))
    else:
        test_results.append(('web_search', f'FAIL: {result[:50]}'))
except Exception as e:
    test_results.append(('web_search', f'ERROR: {e}'))

# Test code_helper
try:
    result = registry.run('code_helper', {'action': 'analyze', 'path': './skills'})
    if '"file"' in result and '"imports"' in result:
        test_results.append(('code_helper', 'PASS'))
    else:
        test_results.append(('code_helper', f'FAIL: {result[:50]}'))
except Exception as e:
    test_results.append(('code_helper', f'ERROR: {e}'))

print("\nTest Results:")
all_passed = True
for skill, result in test_results:
    status = "✓ PASS" if result == "PASS" else "✗ FAIL"
    print(f"  {skill}: {status}")
    if result != "PASS":
        all_passed = False
        print(f"    Details: {result}")

if all_passed:
    print("\n🎉 ALL SKILLS ARE WORKING CORRECTLY!")
else:
    print("\n❌ Some skills failed functionality tests")
    sys.exit(1)