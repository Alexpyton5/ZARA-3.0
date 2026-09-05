import sys
sys.path.insert(0, '.')
from memory.project_memory import ProjectMemory
pm = ProjectMemory()
print("Documents in project memory:")
for key in pm.list_docs():
    print(f"  - {key}")
    if key == "decisions":
        doc = pm.get_doc(key)
        if doc:
            print(f"    Title: {doc['title']}")
            print(f"    Content: {doc['content'][:200]}...")  # first 200 chars
        else:
            print("    Not found!")
