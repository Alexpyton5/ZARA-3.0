"""Test for capability registry functionality.

This test verifies that:
1. Fundamental actions are loaded at startup
2. Non-fundamental actions can be loaded on demand
3. The registry correctly reports loaded actions
4. Unknown actions are rejected
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

def test_capability_registry():
    from core.capability_registry import (
        load_fundamentals, 
        get_loaded_actions, 
        load_capability, 
        get_fundamental_actions,
        ensure_loaded
    )
    from core.action_registry import get_registry
    
    # Clear any existing actions for clean test (not actually possible with singleton)
    # Instead we'll just work with what we have and make relative checks
    
    reg = get_registry()
    initial_count = len(reg._actions)
    print(f"Initial actions loaded: {initial_count}")
    
    # Load fundamentals
    load_fundamentals()
    after_fundamentals = get_loaded_actions()
    print(f"After loading fundamentals: {len(after_fundamentals)} actions")
    
    # Verify all fundamentals are loaded
    fundamental_set = set(get_fundamental_actions())
    loaded_set = set(after_fundamentals)
    missing_fundamentals = fundamental_set - loaded_set
    extra_loaded = loaded_set - fundamental_set
    
    if missing_fundamentals:
        print(f"ERROR: Missing fundamentals: {missing_fundamentals}")
        return False
    else:
        print("SUCCESS: All fundamental actions loaded")
    
    # Test loading a non-fundamental action
    test_action = 'code_analyze'  # This should not be in fundamentals
    if test_action in fundamental_set:
        print(f"ERROR: {test_action} is incorrectly in fundamental set")
        return False
        
    print(f"Loading non-fundamental action: {test_action}")
    success = load_capability(test_action)
    if not success:
        print(f"ERROR: Failed to load {test_action}")
        return False
        
    print(f"SUCCESS: Loaded {test_action}")
    
    # Verify it's now in loaded actions
    loaded_after = get_loaded_actions()
    if test_action not in loaded_after:
        print(f"ERROR: {test_action} not found in loaded actions after loading")
        return False
    print("SUCCESS: Action correctly appears in loaded actions")
    
    # Test ensure_loaded
    try:
        ensure_loaded('web_search')  # This is fundamental
        ensure_loaded('system_time')  # This is fundamental
        ensure_loaded('code_test')   # This is not fundamental but we loaded code_analyze which imports code module
        print("SUCCESS: ensure_loaded works for known actions")
    except ValueError as e:
        print(f"ERROR: ensure_loaded failed: {e}")
        return False
    
    # Test unknown action rejection
    try:
        ensure_loaded('this_action_does_not_exist')
        print("ERROR: ensure_loaded should have failed for unknown action")
        return False
    except ValueError:
        print("SUCCESS: ensure_loaded correctly rejects unknown actions")
    
    # Test load_capability returns False for unknown action
    if load_capability('another_unknown_action'):
        print("ERROR: load_capability should return False for unknown action")
        return False
    print("SUCCESS: load_capability correctly returns False for unknown action")
    
    print("\n=== CAPABILITY REGISTRY TEST PASSED ===")
    return True

if __name__ == '__main__':
    success = test_capability_registry()
    sys.exit(0 if success else 1)