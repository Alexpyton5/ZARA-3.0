#!/usr/bin/env python3
"""Test the capability registry."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from core.capability_registry import load_fundamentals, get_loaded_actions, load_capability, get_fundamental_actions
from core.action_registry import get_registry

def test():
    reg = get_registry()
    print("Initial actions loaded:", len(reg._actions))
    # Load fundamentals
    load_fundamentals()
    loaded = get_loaded_actions()
    print("After loading fundamentals:", len(loaded))
    print("Loaded actions:", sorted(loaded))
    # Try to load a non-fundamental action
    action_to_load = 'code_analyze'
    print(f"Loading {action_to_load}...")
    success = load_capability(action_to_load)
    print(f"Success: {success}")
    print("Actions after loading:", len(reg._actions))
    # Check that it's there
    if action_to_load in reg._actions:
        print(f"{action_to_load} is loaded")
    else:
        print(f"{action_to_load} NOT loaded")
    # Try to load an unknown action
    print("Loading unknown action 'xyz'...")
    success = load_capability('xyz')
    print(f"Success: {success}")

if __name__ == '__main__':
    test()