import shutil
import os

backup_path = 'core/gemini_live_voice.py.bak'
target_path = 'core/gemini_live_voice.py'

# Step 1: Restore from backup
shutil.copy2(backup_path, target_path)

# Step 2: Read the file
with open(target_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Step 3: Fix the separator line in the first _merge_fragment.
# We'll look for the line that contains the separator assignment in the _merge_fragment function.
# We know the _merge_fragment function starts with '@staticmethod' and then 'def _merge_fragment'.
# We'll find the first occurrence and then within that function, fix the separator line.
in_merge_fragment = False
brace_count = 0  # We'll use a simple approach: just look for the line and fix it.
for i, line in enumerate(lines):
    if line.strip().startswith('@staticmethod') and i+1 < len(lines) and lines[i+1].strip().startswith('def _merge_fragment'):
        in_merge_fragment = True
    if in_merge_fragment and 'separator = \"\" if current.endswith((\" \", \"' in line:
        # Fix the line: we want to have single backslashes for the newline in the string.
        # The line in the backup is:
        #        separator = \"\" if current.endswith((\" \", \"\\n\")) or fragment.startswith((\" \", \"\\n\", \".\", \",\", \"!\", \"?\", \":\", \";\")) else \" \"\\n
        # We want to change it to:
        #        separator = \"\" if current.endswith((\" \", \"\\n\")) or fragment.startswith((\" \", \"\\n\", \".\", \",\", \"!\", \"?\", \":\", \";\")) else \" \"
        # But note: the backup might have extra backslashes. We'll replace the two occurrences of \"\\n\\\" with \"\\n\".
        corrected_line = line.replace('\"\\n\\\"', '\"\\n\"')
        lines[i] = corrected_line
        # We break after fixing the first occurrence (assuming there is only one in the function)
        break

# Step 4: Fix the print line in _check_wake_word.
# We'll look for the line that contains the print statement for WAKE_WORD_METRIC.
for i, line in enumerate(lines):
    if \"print(f'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}')\" in line:
        # If the line ends with a backslash (and then newline), remove the backslash.
        if line.rstrip().endswith('\\\\'):
            lines[i] = line.rstrip('\\\\') + '\\n'
        break

# Step 5: Remove the duplicate _merge_fragment and the misplaced _pcm_level code.
# We will find the second occurrence of '@staticmethod' that is part of the duplicate _merge_fragment.
# We'll then remove from that line until we reach a line that is not indented (i.e., starts with whitespace that is less than or equal to the indentation of the '@staticmethod'?).
# Actually, we want to remove until we reach a line that is at the module level (i.e., no indentation) or until we reach the next function or class definition that is at the same level as the first @staticmethod.
# We'll do: find the index of the second '@staticmethod' that is followed by 'def _merge_fragment' (the duplicate).
# Then, we'll remove lines from that index until we find a line that starts with whitespace that is not an increase (i.e., the same or less) and that is not part of the function.

# We'll do a simple approach: we know that after the duplicate _merge_fragment, there is a bunch of lines that are actually part of _pcm_level but misplaced, and then we have the async def _emit_state.
# We want to keep the async def _emit_state and everything after it.

# Let's find the line numbers for the second '@staticmethod' that is part of the duplicate.
second_static_index = -1
static_count = 0
for i, line in enumerate(lines):
    if line.strip().startswith('@staticmethod'):
        static_count += 1
        if static_count == 2:
            second_static_index = i
            break

if second_static_index != -1:
    # Now, we want to remove from second_static_index until we reach a line that is at the module level (i.e., starts with no whitespace) or until we reach a line that is a function or class definition at the module level.
    # We'll look for the next line that starts with no whitespace (i.e., begins with a letter or underscore or is empty?).
    # But note: the file might have blank lines. We'll skip blank lines.
    # We'll look for a line that, after stripping, starts with 'def ' or 'class ' or '@' (for decorators) or is empty? Actually, we want to stop before the async def _emit_state.
    # We know that after the duplicate block, we have the async def _emit_state.
    # Let's find the line that starts with 'async def _emit_state' after the second_static_index.
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
        # If we didn't find it, we'll just remove from second_static_index until the end? That would be too much.
        # Instead, we'll remove until we find a line that is not indented (i.e., starts with whitespace that is not a space?).
        # We'll assume that the duplicate block ends before a line that has less indentation than the '@staticmethod'.
        # The '@staticmethod' is at the module level, so it has no leading whitespace.
        # So we look for the next line that has no leading whitespace (after the duplicate block).
        for i in range(second_static_index + 1, len(lines)):
            if lines[i].strip() == '' or not lines[i][0].isspace():
                # We found a line that is either empty or starts with non-whitespace.
                # We want to keep this line and everything after it.
                # So we remove from second_static_index to i-1.
                del lines[second_static_index:i]
                break

# Step 6: Write the file back.
with open(target_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Fixed gemini_live_voice.py')