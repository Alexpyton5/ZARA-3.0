#!/usr/bin/env python3
import hashlib

with open('skills/malicious_skill.py', 'rb') as f:
    h = hashlib.sha256()
    for chunk in iter(lambda: f.read(4096), b''):
        h.update(chunk)
    print('malicious_skill hash:', h.hexdigest())