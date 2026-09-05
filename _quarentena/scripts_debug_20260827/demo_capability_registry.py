"""Demonstration test for capability registry showing token savings.

This test shows:
1. How many actions are loaded at startup (fundamentals only)
2. How many actions are available total
3. Approximate token savings from lazy loading
"""

import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

def count_tokens_approx(text: str) -> int:
    """Very rough token approximation: 4 chars per token."""
    return max(1, len(text) // 4)

def main():
    from core.action_registry import get_registry
    from core.capability_registry import (
        load_fundamentals, 
        get_loaded_actions, 
        get_fundamental_actions
    )
    
    reg = get_registry()
    
    # Load all actions by importing the actions module (this happens automatically)
    # but we'll do it explicitly to ensure we have all actions
    import core.actions  # noqa: F401
    
    # Get all specifications
    all_specs = reg.get_all_specs()
    all_functions = reg.get_openai_functions()
    all_json = json.dumps(all_functions, ensure_ascii=False, indent=2)
    all_tokens = count_tokens_approx(all_json)
    
    # Load only fundamental actions
    # First, we need to simulate having only fundamentals loaded.
    # Since we can't unload actions from the singleton registry, we'll compute
    # what the functions would be for just the fundamental actions.
    fundamental_names = set(get_fundamental_actions())
    fundamental_specs = {name: spec for name, spec in all_specs.items() if name in fundamental_names}
    
    # Build functions for fundamental specs only
    fundamental_functions = []
    for name, spec in fundamental_specs.items():
        fundamental_functions.append({
            "type": "function",
            "function": {
                "name": f"zara_{name}",
                "description": spec.description,
                "parameters": spec.parameters,
            }
        })
    fundamental_json = json.dumps(fundamental_functions, ensure_ascii=False, indent=2)
    fundamental_tokens = count_tokens_approx(fundamental_json)
    
    # Calculate savings
    savings = all_tokens - fundamental_tokens
    savings_percent = (savings / all_tokens) * 100 if all_tokens else 0
    
    print("=== ZARA 3.0 CAPABILITY REGISTRY DEMONSTRATION ===")
    print(f"Total actions available: {len(all_specs)}")
    print(f"Fundamental actions (loaded at startup): {len(fundamental_names)}")
    print()
    print("Token usage comparison:")
    print(f"  All actions: {all_tokens:,} tokens (~{len(all_json):,} characters)")
    print(f"  Fundamentals only: {fundamental_tokens:,} tokens (~{len(fundamental_json):,} characters)")
    print(f"  Savings: {savings:,} tokens ({savings_percent:.1f}%)")
    print()
    print("Fundamental actions loaded:")
    for action in sorted(get_fundamental_actions()):
        print(f"  - {action}")
    print()
    
    # Demonstrate lazy loading
    print("Lazy loading demonstration:")
    print("  Before loading 'code_analyze':", len(get_loaded_actions()), "actions loaded")
    from core.capability_registry import load_capability
    success = load_capability('code_analyze')
    print("  After loading 'code_analyze':", len(get_loaded_actions()), "actions loaded")
    print("  Load successful:", success)
    print()
    
    # Show that loading one action loads related actions from same module
    print("Related actions from 'code' module now loaded:")
    code_related = [name for name in get_loaded_actions() 
                   if name not in get_fundamental_actions() 
                   and name in ['code_analyze', 'code_lint', 'code_format', 'code_test', 'code_generate']]
    for action in sorted(code_related):
        print(f"  - {action}")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())