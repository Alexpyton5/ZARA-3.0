import sys

def get_indent(line):
    return len(line) - len(line.lstrip())

def find_class(lines, class_name):
    for i, line in enumerate(lines):
        if line.rstrip() == f'class {class_name}:':
            return i
    return None

def find_method(lines, start_idx, method_signature):
    for i in range(start_idx, len(lines)):
        if lines[i].strip().startswith(method_signature):
            return i
    return None

def find_method_end(lines, start_idx):
    # start_idx is the index of the def line
    def_indent = get_indent(lines[start_idx])
    i = start_idx + 1
    while i < len(lines):
        stripped = lines[i].lstrip()
        if not stripped:  # empty line, we continue
            i += 1
            continue
        indent = get_indent(lines[i])
        if indent <= def_indent:
            # We've hit a line with less or equal indentation that is not empty -> end of method
            break
        i += 1
    return i  # exclusive

# Read the backup file
with open('core/ipc_handlers.py.backup', 'r', encoding='utf-8') as f:
    backup_lines = f.readlines()

# Read the current file
with open('core/ipc_handlers.py', 'r', encoding='utf-8') as f:
    current_lines = f.readlines()

# Find the class IPCHandler in both
backup_class_idx = find_class(backup_lines, 'IPCHandler')
current_class_idx = find_class(current_lines, 'IPCHandler')
if backup_class_idx is None or current_class_idx is None:
    print('Could not find class IPCHandler')
    sys.exit(1)

# Find the __init__ method in both
backup_def_idx = find_method(backup_lines, backup_class_idx, 'def __init__(self, send_callback:')
current_def_idx = find_method(current_lines, current_class_idx, 'def __init__(self, send_callback:')
if backup_def_idx is None or current_def_idx is None:
    print('Could not find __init__ method')
    sys.exit(1)

# Find the end of the __init__ method in the backup
backup_method_end = find_method_end(backup_lines, backup_def_idx)
# Find the end of the __init__ method in the current file (we will replace up to this point)
current_method_end = find_method_end(current_lines, current_def_idx)

# Extract the backup method lines (from def line to end-1)
backup_method_lines = backup_lines[backup_def_idx:backup_method_end]
# The backup def line is the first line of backup_method_lines
# The backup body lines are backup_method_lines[1:]

# Extract the current def line (we will keep it)
current_def_line = current_lines[current_def_idx]

# Compute the indentation of the backup def line
backup_def_indent = get_indent(backup_method_lines[0])
# Compute the indentation of the current def line
current_def_indent = get_indent(current_def_line)

# If the backup def line and current def line have the same indentation, we can just replace the body with the backup body.
# But we want to be safe and adjust the backup body to match the current def line's indentation.

# Process the backup body lines
new_body_lines = []
for line in backup_method_lines[1:]:
    if line.strip() == '':
        # Empty line: we set it to the current def line's indentation plus 4 spaces (standard indent for a method body)
        new_body_lines.append(' ' * (current_def_indent + 4) + '\n')
    else:
        # Compute the extra indentation of this line relative to the backup def line
        indent = get_indent(line)
        extra = indent - backup_def_indent
        # The new indent should be current_def_indent + 4 + extra
        new_indent = current_def_indent + 4 + extra
        new_body_lines.append(' ' * new_indent + line.lstrip())

# Now, the new method lines in the current file will be:
#   current_def_line (with its original indentation) + new_body_lines
new_method_lines = [current_def_line] + new_body_lines

# Replace the method in the current lines
new_current_lines = current_lines[:current_def_idx] + new_method_lines + current_lines[current_method_end:]

# Write back to the current file
with open('core/ipc_handlers.py', 'w', encoding='utf-8') as f:
    f.writelines(new_current_lines)

print('Fixed __init__ method indentation using backup')
