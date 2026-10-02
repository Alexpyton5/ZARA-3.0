import sys
sys.path.insert(0, ".")
import core.action_registry as ar
loaded = ar.load_advanced_action_exports()
specs = ar.get_registry().get_all_specs()
ks = sorted(k for k in specs if k.startswith("computer_"))
print("LOADED:", len(loaded))
print("COMPUTER_ACTIONS:", ks)
print("N_COMPUTER:", len(ks), "TOTAL:", len(specs))
