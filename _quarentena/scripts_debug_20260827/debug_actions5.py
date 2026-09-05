# Let's trace exactly what load_capability does step by step
from core.capability_registry import load_fundamentals, load_capability, _DEFERRED_ACTIONS
from core.action_registry import get_registry
import core.action_registry as action_registry_module

# Monkey-patch to trace
original_remember = action_registry_module.ActionRegistry.register
def traced_register(self, name, *args, **kwargs):
    print(f"  [REGISTER] {name}")
    return original_remember(self, name, *args, **kwargs)
action_registry_module.ActionRegistry.register = traced_register

# Also trace _remember_new_registrations
import core.capability_registry as cap_reg
original_remember_new = cap_reg._remember_new_registrations
def traced_remember_new(before, requested):
    print(f"  [_remember_new_registrations] before={len(before)}, requested={requested}")
    registry = cap_reg.get_registry()
    added = set(registry.list_actions()) - before
    print(f"    added: {added}")
    result = original_remember_new(before, requested)
    print(f"    after registry: {registry.list_actions()}")
    return result
cap_reg._remember_new_registrations = traced_remember_new

load_fundamentals()

reg = get_registry()
print("\\nFinal actions:", sorted(reg.list_actions()))
print("Deferred actions:", list(_DEFERRED_ACTIONS.keys()))