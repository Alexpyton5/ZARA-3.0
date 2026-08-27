import json
import sys

with open(r'coverage.json') as f:
    d = json.load(f)

areas = ['voice', 'ipc', 'telegram', 'security', 'init']
for file_path, data in d['files'].items():
    cov = data['summary']['percent_covered']
    if cov < 90:
        lower_path = file_path.lower()
        if any(area in lower_path for area in areas):
            print(f'{file_path}: {cov:.2f}%')