import sys
sys.path.insert(0, '.')
from memory.project_memory import ProjectMemory
pm = ProjectMemory()
print("Has append_decision:", hasattr(pm, 'append_decision'))
if hasattr(pm, 'append_decision'):
    pm.append_decision("Test decision from script")
    doc = pm.get_doc("decisions")
    if doc:
        print("Decisions content length:", len(doc['content']))
        print("First 200 chars:", doc['content'][:200])
    else:
        print("No decisions doc")
else:
    print("Method not found")