import re
import ast
import sys

# Read the backend file
with open(r'core/ipc_handlers.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the handler_map dictionary inside the handle_message function
# We'll look for the line that starts with 'handler_map = {' and then capture until the closing brace
# However, the dictionary might span multiple lines. We'll use a simple approach: extract between 'handler_map = {' and the next '}' that is at the same indentation level?
# Instead, let's try to parse the file with ast and find the function and then the dictionary.

# But given the complexity, we can use a regex to capture the content of the handler_map assignment.
# We look for: handler_map = { ... } and we assume it ends with a closing brace on its own line or at the end of the line.
# However, the dictionary is large and spans many lines.

# Let's try to extract the entire handle_message function and then parse the dictionary within it.

# First, find the handle_message function
func_match = re.search(r"async def handle_message\(self, msg: IPCMessage\):.*?handler_map = \{.*?\}", content, re.DOTALL)
if not func_match:
    print("Could not find handle_message function or handler_map")
    sys.exit(1)

handler_map_block = func_match.group(0)
# Now we want to extract the dictionary part after 'handler_map = {'
# We can do: split on 'handler_map = {' and then take the rest, then balance braces.
after_equal = handler_map_block.split('handler_map = {', 1)[1]
# Now we need to balance braces to get the entire dictionary.
# We'll count opening and closing braces until we reach zero.
brace_count = 1
dict_str = ''
for ch in after_equal:
    dict_str += ch
    if ch == '{':
        brace_count += 1
    elif ch == '}':
        brace_count -= 1
        if brace_count == 0:
            break

# Now dict_str contains the dictionary as a string, but note that it might have trailing comma and then the closing brace we already counted.
# We have the entire dictionary string including the outer braces? Actually we started after the opening brace of the dictionary.
# So we have the inner content. We'll add the braces back to make it a valid dict string.
dict_str = '{' + dict_str + '}'

# Now we can use ast.literal_eval to convert the string to a dictionary.
# However, the dictionary values are function references (like self.handle_engine_change) which are not literals.
# So we cannot use ast.literal_eval.

# Instead, we can extract the keys which are strings. We can look for patterns like 'key': value.
# We'll use a regex to find all string literals that are keys in the dictionary.
# The pattern: '\\s*'([^']+)'\\s*:'
key_pattern = re.compile(r"\\s*'([^']+)'\\s*:")
keys = key_pattern.findall(dict_str)

print("Backend handler keys (from handler_map):")
for key in sorted(keys):
    print(f"  {key}")
print(f"\nTotal backend handler keys: {len(keys)}")