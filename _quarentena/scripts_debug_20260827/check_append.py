import sys
sys.path.insert(0, '.')
from memory.project_memory import ProjectMemory
pm = ProjectMemory()
print('Current documents:', pm.list_docs())
if 'decisions' in pm.list_docs():
    doc = pm.get_doc('decisions')
    print('Current decisions length:', len(doc['content']) if doc else 0)
else:
    print('Decisions document not found.')
# Append a test decision
pm.append_decision('TEST: Verifying append_decision method works')
doc2 = pm.get_doc('decisions')
print('After append, content:')
print(doc2['content'] if doc2 else 'None')
# Check if our test decision is in the content
if doc2 and 'TEST: Verifying append_decision method works' in doc2['content']:
    print('SUCCESS: Decision appended.')
else:
    print('FAILURE: Decision not found in content.')