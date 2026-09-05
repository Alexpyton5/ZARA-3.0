import shutil
import os

backup_path = 'core/gemini_live_voice.py.bak'
target_path = 'core/gemini_live_voice.py'

# Step 1: Restore from backup
shutil.copy2(backup_path, target_path)

# Step 2: Read the file
with open(target_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Step 3: Fix the print line in _check_wake_word.
for i, line in enumerate(lines):
    if \"print(f'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}')\" in line:
        # If the line ends with a backslash (and then newline), remove the backslash.
        if line.rstrip().endswith('\\\\'):
            lines[i] = line.rstrip('\\\\') + '\\n'
        break

# Step 4: Remove the duplicate staticmethod block and the misplaced code.
# We'll find the second occurrence of '@staticmethod' that is followed by 'def _merge_fragment' (the duplicate).
# We'll then remove from that line until we reach a line that is at the module level (i.e., starts with no whitespace) 
# and that is not part of the function (i.e., we stop before the async def _emit_state).

# We'll do: find the index of the second '@staticmethod' that is followed by 'def _merge_fragment' (the duplicate).
second_static_index = -1
static_count = 0
for i, line in enumerate(lines):
    if line.strip().startswith('@staticmethod'):
        static_count += 1
        if static_count == 2:
            # Check that the next line is the definition of _merge_fragment
            if i+1 < len(lines) and lines[i+1].strip().startswith('def _merge_fragment'):
                second_static_index = i
                break

if second_static_index != -1:
    # Now, we want to remove from second_static_index until we reach a line that is at the module level (i.e., starts with no whitespace) 
    # and that is not part of the function. We'll look for the next line that starts with no whitespace (after the duplicate block).
    # We'll skip lines that are indented (i.e., start with whitespace).
    # We know that the duplicate block includes the @staticmethod, the def, and the function body until the misplaced _pcm_level code and then the async def _emit_state.
    # We want to keep the async def _emit_state and everything after it.
    # So we will remove from second_static_index until we find a line that starts with no whitespace (and is not empty) and that is the async def _emit_state.
    # But note: there might be blank lines. We'll skip blank lines.

    # Let's find the line index of the async def _emit_state after the second_static_index.
    emit_state_index = -1
    for i in range(second_static_index, len(lines)):
        if lines[i].strip().startswith('async def _emit_state'):
            emit_state_index = i
            break

    if emit_state_index != -1:
        # We want to keep from emit_state_index onward.
        # We will remove lines from second_static_index to emit_state_index-1.
        del lines[second_static_index:emit_state_index]
    else:
        # If we didn't find it, we'll remove from second_static_index until we find a line that is not indented (i.e., starts with no whitespace) 
        # and that is not empty? We'll just remove until we find a line that starts with no whitespace (and is not a blank line?).
        for i in range(second_static_index + 1, len(lines)):
            stripped = lines[i].strip()
            if stripped == '':
                continue
            if not lines[i][0].isspace():
                # We found a line that starts with non-whitespace.
                # We want to keep this line and everything after it.
                # So we remove from second_static_index to i-1.
                del lines[second_static_index:i]
                break

# Step 5: Write the file back.
with open(target_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Fixed gemini_live_voice.py')