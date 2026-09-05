import sys
with open('core/gemini_live_voice.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the indices of the lines that are exactly "# Log structured metric"
indices = [i for i, line in enumerate(lines) if line.strip() == "# Log structured metric"]
# If there are more than one, we want to keep only the first one and remove the others.
# But note: we have two consecutive? Actually, we saw at lines 418 and 419 (0-indexed) both are the comment.
# We'll keep the first and remove the second.
if len(indices) > 1:
    # Remove the duplicate at indices[1] (the second occurrence)
    del lines[indices[1]]

# Now, we also need to check that the print line is correct.
# Let's find the line that starts with '                print(f"[WAKE_WORD_METRIC"'
for i, line in enumerate(lines):
    if line.strip().startswith('print(f"[WAKE_WORD_METRIC'):
        # We'll leave it as is for now, but we can check if it's correct.
        break

with open('core/gemini_live_voice.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)