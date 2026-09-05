import sys
sys.path.insert(0, '.')

from memory.user_memory import UserMemoryCore
import tempfile
import os

def test_user_memory_semantic_search():
    # Create a temporary database for the test
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name

    try:
        # Initialize the user memory with the temporary database
        mem = UserMemoryCore(db_path=db_path)
        # Add a semantic fact
        fact = "Alex gosta de café preto"
        mem.add(fact, category="semantic_fact", confidence=0.9)
        # Search for the fact
        results = mem.search("Alex gosta de café", category="semantic_fact", limit=1)
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"
        assert results[0]['fact'] == fact, f"Unexpected fact: {results[0]['fact']}"
        # Check that the score is present and reasonable (should be high because it's a direct match)
        assert '_score' in results[0], "Missing _score in result"
        assert results[0]['_score'] > 0.8, f"Score too low: {results[0]['_score']}"
        print("User memory semantic search test passed.")
    finally:
        # Clean up the temporary database
        os.unlink(db_path)

if __name__ == '__main__':
    test_user_memory_semantic_search()
    print("All tests passed.")