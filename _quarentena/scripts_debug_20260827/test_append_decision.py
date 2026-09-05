import sys
import tempfile
from pathlib import Path
from datetime import datetime

# We are in the ZARA root, so we can import memory.project_memory directly
from memory.project_memory import ProjectMemory

def test_append_decision():
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        pm = ProjectMemory(base_dir=base_dir)
        
        # Append first decision
        pm.append_decision("Test decision 1")
        # Append second decision
        pm.append_decision("Test decision 2")
        
        # Retrieve the decisions document
        doc = pm.get_doc("decisions")
        print("Title:", doc["title"] if doc else "None")
        print("Content:")
        print(doc["content"] if doc else "None")
        
        # Check that the vault file exists and has the content
        vault_file = base_dir / "vault" / "decisions.md"
        if vault_file.exists():
            print("\nVault file content:")
            print(vault_file.read_text(encoding="utf-8"))
        else:
            print("\nVault file not found!")
            
        # Verify the content contains our decisions with timestamps
        if doc:
            content = doc["content"]
            # Check for two lines with our decisions and timestamps
            assert "Test decision 1" in content
            assert "Test decision 2" in content
            # Check for timestamp format (simple check for brackets and colon)
            import re
            timestamp_pattern = r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'
            timestamps = re.findall(timestamp_pattern, content)
            assert len(timestamps) >= 2, f"Expected at least 2 timestamps, found {len(timestamps)}: {timestamps}"
            print("\nSUCCESS: Decisions appended with timestamps.")
        else:
            print("\nFAILURE: Decisions document not found.")
            raise AssertionError("Decisions document not found")

if __name__ == "__main__":
    test_append_decision()
