import json
import urllib.request

# Test direct Ollama API call
url = "http://localhost:11434/api/embeddings"
data = json.dumps({"model": "nomic-embed-text", "prompt": "teste de embeddng"})
data = data.encode('utf-8')
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
response = urllib.request.urlopen(req)
result = json.load(response)
print("Embedding length:", len(result['embedding']))
print("First 5 values:", result['embedding'][:5])
# Check if it's normalized (should be close to 1.0)
norm = sum(x*x for x in result['embedding']) ** 0.5
print("Norm:", norm)