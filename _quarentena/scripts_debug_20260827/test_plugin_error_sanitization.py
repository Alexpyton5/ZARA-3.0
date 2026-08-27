#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.plugin_loader import discover_plugins
from pathlib import Path

# Load the skills
skills_dir = Path('./skills')
core_tool_names = set()

def logger(msg):
    pass  # suppress

registry = discover_plugins(skills_dir, core_tool_names, logger)

# Get the hello_skill module
hello_record = registry._plugins.get('hello_skill')
if hello_record is None:
    print("ERROR: hello_skill not found")
    sys.exit(1)

# Import the module to monkey-patch
import importlib.util
spec = importlib.util.spec_from_file_location("hello_skill", hello_record.file)
module = importlib.util.module_from_spec(spec)
sys.modules["hello_skill"] = module
spec.loader.exec_module(module)

# Store the original run function
original_run = module.run

# Define a patched run that leaks a secret
def leaky_run(parameters, context=None):
    raise Exception("sk_live_1234567890abcdef is compromised")

# Monkey-patch
module.run = leaky_run

# Now test the plugin loader's run method
try:
    result = registry.run('hello_skill', {})
    print(f"Result: {result}")
    # Check that the secret is not in the result
    if "sk_live_1234567890abcdef" in result:
        print("FAIL: Secret leaked in error message")
        sys.exit(1)
    else:
        print("PASS: Secret redacted from error message")
except Exception as e:
    print(f"Unexpected exception: {e}")
    sys.exit(1)
finally:
    # Restore the original run function
    module.run = original_run