import hashlib, json, os

# Read ULTIMO_CANDIDATO.json
with open('ULTIMO_CANDIDATO.json', 'r') as f:
    data = json.load(f)

exe_path = data['EXE_PATH']
build_id = data.get('BUILD_ID', '')
sha256_from_json = data.get('EXE_SHA256', '')

# Compute SHA256 of the executable
full_path = exe_path.replace('/', chr(92))
if not os.path.isabs(full_path):
    full_path = os.path.join(os.getcwd(), full_path)
with open(full_path, 'rb') as f:
    exe_content = f.read()
computed_sha256 = hashlib.sha256(exe_content).hexdigest()

result = {
    'EXE_PATH': exe_path,
    'SHA256_COMPUTED': computed_sha256,
    'BUILD_ID': build_id,
    'SHA256_FROM_JSON': sha256_from_json,
    'MATCH': computed_sha256 == sha256_from_json
}

with open('compute_result.json', 'w') as f:
    json.dump(result, f, indent=2)

print(json.dumps(result, indent=2))