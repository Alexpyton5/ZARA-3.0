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

# Try to run the malicious skill (should be rejected by trust gate, but if it weren't, we'd want sanitized errors)
# Actually, the malicious skill is rejected by trust gate, so we won't get to the run method.
# Let's test with a skill that will cause an error in run (e.g., missing import) to see if error is sanitized.
# We'll create a temporary skill that raises an exception with a secret.

import tempfile
import hashlib

# Create a temporary skill that will leak a secret in its error
skill_content = '''
PLUGIN = {
    "name": "leaky_skill",
    "description": "A skill that leaks secrets in errors",
    "parameters": {"type": "OBJECT", "properties": {}},
    "category": "general",
    "version": "1.0.0",
    "author": "Tester",
}

def run(parameters, context=None):
    raise Exception("sk_live_1234567890abcdef is compromised")
'''

with tempfile.NamedTemporaryDir() as tmpdir:
    # We'll just do it in the current directory for simplicity
    skill_path = Path('./leaky_skill.py')
    skill_path.write_text(skill_content, encoding='utf-8')
    
    # Now try to load it via discover_plugins (but note: it will be rejected by trust gate because not in manifest)
    # Instead, we can directly call the PluginRegistry.run method if we bypass trust gate? 
    # Better to test the _sanitize_observation function directly.
    
    from core.ipc_handlers import _sanitize_observation
    
    test_error = Exception("sk_live_1234567890abcdef is compromised")
    sanitized = _sanitize_observation(str(test_error))
    print(f"Original error: {test_error}")
    print(f"Sanitized error: {sanitized}")
    
    # Check that the secret is redacted
    if "sk_live_1234567890abcdef" in sanitized:
        print("FAIL: Secret not redacted")
        sys.exit(1)
    else:
        print("PASS: Secret redacted")
    
    skill_path.unlink(missing_ok=True)