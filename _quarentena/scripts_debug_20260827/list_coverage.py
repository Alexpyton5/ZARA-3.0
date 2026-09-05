import json
with open(r'C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\coverage.json') as f:
    data = json.load(f)
files = data.get('files', {})
results = []
for fpath, info in files.items():
    cov = info['summary']['percent_covered']
    results.append((fpath, cov))
results.sort(key=lambda x: x[1])
for fpath, cov in results:
    print(f'{fpath}: {cov:.2f}%')