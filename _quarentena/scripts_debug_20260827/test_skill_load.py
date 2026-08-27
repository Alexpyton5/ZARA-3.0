#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.plugin_loader import discover_plugins
from pathlib import Path

skills_dir = Path('./skills')
core_tool_names = set()

def logger(msg):
    print(msg)

registry = discover_plugins(skills_dir, core_tool_names, logger)

print('\n=== All loaded skills ===')
for name, rec in registry._plugins.items():
    print(f'  {name}: valid={rec.valid}')

print('\n=== All records (including rejected) ===')
for rec in registry._all_records:
    print(f'  {rec.name}: valid={rec.valid}, error={rec.error[:80] if rec.error else ""}')