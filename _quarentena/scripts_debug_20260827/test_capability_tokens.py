"""Test token savings from capability registry."""

import json
import sys
import os

# Insert project root to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from core.action_registry import get_registry
from core.capability_registry import load_fundamentals, get_loaded_actions

def count_tokens_approx(text: str) -> int:
    """Very rough token approximation: 4 chars per token."""
    return len(text) // 4

def main():
    reg = get_registry()
    
    # Scenario 1: Load all actions (current behavior without lazy loading)
    # We need to simulate loading all actions by importing core.actions
    # But we can't unload actions easily. Instead, we'll compute the spec size
    # for all actions by getting them from the registry after a full import.
    # We'll do a fresh import in a subprocess? Simpler: we can compute the
    # spec size from the registry after we load all actions (which happens
    # when we import core.actions). However, we already have some actions
    # loaded due to earlier imports. Let's just load all actions by importing
    # the actions package (which triggers @action decorators).
    import core.actions  # noqa: F401
    all_specs = reg.get_all_specs()
    all_functions = reg.get_openai_functions()
    all_json = json.dumps(all_functions, ensure_ascii=False)
    all_tokens = count_tokens_approx(all_json)
    print(f"All actions: {len(all_specs)} actions")
    print(f"All functions JSON size: {len(all_json)} chars")
    print(f"All approx tokens: {all_tokens}")
    
    # Scenario 2: Load only fundamental actions
    # We need to reset the registry? Not possible. Instead, we'll create a new
    # registry instance? The registry is a singleton. We'll cheat by
    # computing the specs for fundamental actions only by filtering.
    # But we want to measure the token savings of having only fundamental
    # actions loaded in the context (i.e., the functions sent to the LLM).
    # We'll simulate by creating a temporary registry? Too complex.
    # Instead, we'll compute the functions for fundamental actions only,
    # assuming that's what would be sent if we only had those loaded.
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
    fundamental_json = json.dumps(fundamental_functions, ensure_ascii=False)
    fundamental_tokens = count_tokens_approx(fundamental_json)
    print(f"\nFundamental actions: {len(fundamental_specs)} actions")
    print(f"Fundamental functions JSON size: {len(fundamental_json)} chars")
    print(f"Fundamental approx tokens: {fundamental_tokens}")
    
    savings = all_tokens - fundamental_tokens
    savings_percent = (savings / all_tokens) * 100 if all_tokens else 0
    print(f"\nToken savings: {savings} tokens (~{savings_percent:.1f}%)")
    
    # Also test lazy loading: after loading fundamentals, load one non-fundamental on demand
    from core.capability_registry import load_capability
    # Ensure only fundamentals are loaded? We can't unload, but we can check
    # that loading a non-fundamental works.
    print("\n--- Testing lazy loading ---")
    # Load fundamentals (they are already loaded due to import, but we'll call load_fundamentals anyway)
    load_fundamentals()
    loaded = get_loaded_actions()
    print(f"Loaded actions after load_fundamentals: {len(loaded)} (should be <= total)")
    # Try to load a non-fundamental action
    action_to_load = 'code_analyze'
    success = load_capability(action_to_load)
    print(f"Loading '{action_to_load}' success: {success}")
    print(f"Loaded actions after: {len(get_loaded_actions())}")
    
    return 0

def get_fundamental_actions():
    """Return set of fundamental action names."""
    return {
        'system_time',
        'system_info',
        'system_metrics',
        'audio_status',
        'audio_mute',
        'audio_unmute',
        'media_play_pause',
        'media_next',
        'media_previous',
        'os_volume',
        'os_brightness',
        'os_brightness_up',
        'os_brightness_down',
        'os_clipboard_read',
        'os_clipboard',
        'window_minimize',
        'window_maximize',
        'window_restore',
        'web_search',
        'web_fetch',
        'files_list',
        'files_read',
        'files_search',
    }

if __name__ == '__main__':
    sys.exit(main())