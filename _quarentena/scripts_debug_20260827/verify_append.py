import sys
sys.path.insert(0, '.')
from memory.project_memory import ProjectMemory
pm = ProjectMemory()
# Append a unique test decision
test_decision = f"UNIQUE_TEST_{hash('test')}"
pm.append_decision(test_decision)
doc = pm.get_doc("decisions")
if doc:
    content = doc['content']
    # Check if the test decision is in the content
    if test_decision in content:
        print("SUCCESS: Test decision found in decisions log.")
        # Show the last few lines
        lines = content.strip().split('\n')
        print("Last 5 lines:")
        for line in lines[-5:]:
            print(line)
    else:
        print("FAILURE: Test decision not found.")
        print("Content (last 500 chars):")
        print(content[-500:])
else:
    print("FAILURE: No decisions document.")