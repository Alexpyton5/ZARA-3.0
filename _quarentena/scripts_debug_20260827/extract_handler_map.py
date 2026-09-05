import re

backend_file = r"core/ipc_handlers.py"
with open(backend_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Extract the handler_map dictionary from the handle_message function
# We look for the line with 'handler_map = {' and then capture until the closing brace
# But note: the map might span multiple lines and we have a comment in between.
# Let's do a simpler approach: extract lines between 'handler_map = {' and the next '}' at the same indentation.
# However, we can also just extract the keys by looking for patterns like "'key': self.handle_"

# Pattern to match each entry: "'key': self.handle_", or with double quotes?
pattern = r"'([^']+)':\s*self\.handle_"
matches = re.findall(pattern, content)

print("Handler keys found in handler_map:")
for m in sorted(matches):
    print(f"  {m}")
print(f"Total: {len(matches)}")