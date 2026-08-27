import sys
sys.path.insert(0, 'C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002')
from core.capability_registry import load_mapping_from_init, FUNDAMENTAL_ACTIONS, load_fundamentals, get_loaded_actions
from core.action_registry import get_registry

print("Mapping sample:", dict(list(load_mapping_from_init().items())[:5]))
print("Fundamental actions:", sorted(FUNDAMENTAL_ACTIONS))
print("Number of fundamentals:", len(FUNDAMENTAL_ACTIONS))

# Load fundamentals
load_fundamentals()
loaded = get_loaded_actions()
print("Loaded after fundamentals:", len(loaded))
print("Loaded actions:", sorted(loaded))

# Now load all actions by importing all modules
from core import actions  # noqa: F401
all_loaded = get_loaded_actions()
print("All actions loaded:", len(all_loaded))
print("All actions:", sorted(all_loaded))

# Compute difference
not_loaded = set(all_loaded) - set(loaded)
print("Not loaded (non-fundamental):", len(not_loaded))
print("Sample not loaded:", sorted(list(not_loaded))[:10])