import sys

with open('core/ipc_handlers.py', 'r') as f:
    lines = f.readlines()

# Find the class IPCHandler
class_idx = None
for i, line in enumerate(lines):
    if line.rstrip() == 'class IPCHandler:':
        class_idx = i
        break

if class_idx is None:
    print('Class IPCHandler not found')
    sys.exit(1)

# Find the __init__ method after the class
def_idx = None
for i in range(class_idx, len(lines)):
    if lines[i].strip().startswith('def __init__(self, send_callback:'):
        def_idx = i
        break

if def_idx is None:
    print('__init__ method not found')
    sys.exit(1)

# We'll now collect the method body lines until we find a line that is not indented more than the def line.
def_indent = len(lines[def_idx]) - len(lines[def_idx].lstrip())
body_start = def_idx + 1
body_end = body_start
while body_end < len(lines):
    line = lines[body_end]
    stripped = line.lstrip()
    if not stripped:  # empty line, we still include it in the body? We'll include it and decide later.
        body_end += 1
        continue
    indent = len(line) - len(stripped)
    if indent <= def_indent:
        # We've hit a line with less or equal indentation that is not empty -> end of method
        break
    body_end += 1

# Now we have the method lines from def_idx to body_end-1 (inclusive of def line and body)
method_lines = lines[def_idx:body_end]

# The def line is the first line of method_lines
# We want to keep the def line as is (it should be at def_indent).
# For the body lines (method_lines[1:]), we want to set the base indent to def_indent + 4.
# But we want to keep the relative indentation inside the body.

body_lines = method_lines[1:]  # exclude the def line
if not body_lines:
    # Nothing to do
    new_method_lines = method_lines
else:
    # Determine the current base indentation of the body (the minimum indent among non-empty lines)
    non_empty_body = [l for l in body_lines if l.strip() != '']
    if non_empty_body:
        base_body_indent = min(len(l) - len(l.lstrip()) for l in non_empty_body)
    else:
        base_body_indent = 0

    desired_base = def_indent + 4

    new_body_lines = []
    for l in body_lines:
        if l.strip() == '':
            # Empty line: we set it to the desired base indentation (or we could keep it empty? We'll set to desired_base spaces and then newline)
            new_body_lines.append(' ' * desired_base + '\n')
        else:
            current_indent = len(l) - len(l.lstrip())
            extra = current_indent - base_body_indent
            new_indent = desired_base + extra
            new_body_lines.append(' ' * new_indent + l.lstrip())

    new_method_lines = [method_lines[0]] + new_body_lines

# Replace the method in the lines
new_lines = lines[:def_idx] + new_method_lines + lines[body_end:]

with open('core/ipc_handlers.py', 'w') as f:
    f.writelines(new_lines)

print('Fixed __init__ method indentation')
