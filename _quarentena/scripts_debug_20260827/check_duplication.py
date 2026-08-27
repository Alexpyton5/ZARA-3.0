import os

# Check for duplicated patterns across core/actions/*.py files
# Look for common patterns: config reading, HTTP client setup, system prompts

actions_dir = 'core/actions'
duplication_findings = []

# Read all action files and look for common patterns
action_files = {}
for f in os.listdir(actions_dir):
    if f.endswith('.py') and f != '__init__.py':
        path = os.path.join(actions_dir, f)
        with open(path) as fh:
            content = fh.read()
        action_files[f] = content

# Look for common config reading patterns
config_patterns = {}
for fname, content in action_files.items():
    # Check for api_keys.json reading
    if 'api_keys' in content.lower() or 'config' in content.lower():
        key = 'config_reading'
        if key not in config_patterns:
            config_patterns[key] = []
        config_patterns[key].append(fname)

print("Files with config/api_keys references:")
for key, files in config_patterns.items():
    print(f"  {key}: {len(files)} files - {files[:5]}")

# Look for HTTP client patterns
http_patterns = {}
for fname, content in action_files.items():
    import_keywords = ['requests', 'urllib', 'httpx', 'aiohttp', 'http.client']
    for kw in import_keywords:
        if kw in content.lower():
            if kw not in http_patterns:
                http_patterns[kw] = []
            http_patterns[kw].append(fname)

print("\nFiles with HTTP client imports:")
for key, files in http_patterns.items():
    print(f"  {key}: {len(files)} files - {files[:5]}")

# Check for system prompt patterns
system_prompt_patterns = {}
for fname, content in action_files.items():
    if 'system' in content.lower() and ('prompt' in content.lower() or 'SYSTEM_PROMPT' in content.upper()):
        if 'system_prompt' not in system_prompt_patterns:
            system_prompt_patterns['system_prompt'] = []
        system_prompt_patterns['system_prompt'].append(fname)

print("\nFiles with system prompt patterns:")
for key, files in system_prompt_patterns.items():
    print(f"  {key}: {len(files)} files - {files[:5]}")

# Check for hardcoded constants
hardcoded_count = 0
for fname, content in action_files.items():
    import re
    # Look for long strings that might be hardcoded prompts
    long_strings = re.findall(r'["\']{3}([^\n]{100,})["\']{3}', content)
    if long_strings:
        hardcoded_count += 1

print(f"\nFiles with hardcoded long strings: {hardcoded_count}")