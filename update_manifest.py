import hashlib
from pathlib import Path

exe_path = Path('dist-sidecar/zara-backend.exe')
if not exe_path.exists():
    print(f"ERROR: {exe_path} not found")
    exit(1)

# Compute SHA256
hash_sha256 = hashlib.sha256()
with exe_path.open('rb') as f:
    for chunk in iter(lambda: f.read(4096), b''):
        hash_sha256.update(chunk)
hash_hex = hash_sha256.hexdigest()

print(f"SHA256 of {exe_path}: {hash_hex}")

# Update CLEAN_BUILD_ID.txt (first 8 chars?)
clean_build_id = hash_hex[:8]
Path('CLEAN_BUILD_ID.txt').write_text(clean_build_id + '\n')
print(f"Updated CLEAN_BUILD_ID.txt: {clean_build_id}")

# Update SHA256_MANIFEST.txt
manifest_content = f"{hash_hex}  {exe_path.as_posix()}\n"
Path('SHA256_MANIFEST.txt').write_text(manifest_content, newline='\n')
print("Updated SHA256_MANIFEST.txt")

# Update PATCH_SHA256_MANIFEST.txt (same as SHA256_MANIFEST.txt for now)
Path('PATCH_SHA256_MANIFEST.txt').write_text(manifest_content, newline='\n')
print("Updated PATCH_SHA256_MANIFEST.txt")
