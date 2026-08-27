import sys
sys.path.insert(0, '.')
from memory.episodic_memory import _embed
from array import array

# Test the embedding function
vec = _embed('teste de embeddng')
print('Vector type:', type(vec))
print('Vector length:', len(vec))
print('First 5 values:', list(vec[:5]))
# Check that it's normalized (norm ~ 1)
norm = sum(v*v for v in vec) ** 0.5
print('Vector norm:', norm)