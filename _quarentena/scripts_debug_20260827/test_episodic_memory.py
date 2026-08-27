import sys
sys.path.insert(0, '.')
from memory.episodic_memory import EpisodicMemory
from array import array

# Test the episodic memory with Ollama embeddings
mem = EpisodicMemory()
# Add an episode
ep_id = mem.add("Alex pediu para abrir o Chrome", kind="conversation")
print(f"Added episode id: {ep_id}")
# Search for it
results = mem.search("Alex pediu para abrir o Chrome", limit=1)
print(f"Search results: {results}")
# Check the vector size
vec = mem._embed("test")
print(f"Vector length: {len(vec)}")
print(f"First 5: {list(vec[:5])}")