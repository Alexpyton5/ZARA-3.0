import sys
sys.path.insert(0, '.')
from memory.episodic_memory import _embed
from array import array
vec = _embed('teste de embeddng')
print('Vector type:', type(vec))
print('Vector length:', len(vec))
print('First 5 values:', list(vec[:5]))