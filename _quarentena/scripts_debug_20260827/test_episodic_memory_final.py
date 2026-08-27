import sys
sys.path.insert(0, '.')

from memory.episodic_memory import _embed
from array import array

def test_embedding():
    vec = _embed("test")
    assert isinstance(vec, array), "Expected array"
    assert len(vec) == 768, f"Expected length 768, got {len(vec)}"
    # Check that the vector is normalized (norm close to 1)
    norm = sum(v*v for v in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-5, f"Vector not normalized: norm={norm}"
    print("Embedding test passed.")

def test_add_and_search():
    from memory.episodic_memory import EpisodicMemory
    mem = EpisodicMemory()
    # Clear any existing episodes (for a clean test)
    mem.clear()
    # Add an episode
    ep_id = mem.add("Alex pediu para abrir o Chrome", kind="conversation")
    assert ep_id is not None, "Failed to add episode"
    # Search for the episode
    results = mem.search("Alex pediu para abrir o Chrome", limit=1)
    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    assert results[0]['content'] == "Alex pediu para abrir o Chrome", f"Unexpected content: {results[0]['content']}"
    print("Add and search test passed.")

if __name__ == '__main__':
    test_embedding()
    test_add_and_search()
    print("All tests passed.")