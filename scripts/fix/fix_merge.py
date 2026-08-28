import sys
with open('core/gemini_live_voice.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
# lines are 0-indexed
# we want to replace lines 1169 to 1183 (since line numbers in editor start at 1)
# line 1170 is index 1169
# line 1184 is index 1183
new_lines = lines[:1169]  # up to line 1169 (exclusive)
new_lines.append('    @staticmethod\\n')
new_lines.append('    def _merge_fragment(current: str, fragment: str) -> str:\\n')
new_lines.append('        fragment = fragment or \"\"\\n')
new_lines.append('        if not fragment:\\n')
new_lines.append('            return current\\n')
new_lines.append('        if not current:\\n')
new_lines.append('            return fragment\\n')
new_lines.append('        if fragment.startswith(current):\\n')
new_lines.append('            return fragment\\n')
new_lines.append('        if current.endswith(fragment):\\n')
new_lines.append('            return current\\n')
new_lines.append('        separator = \"\" if current.endswith((\" \", \"\\n\")) or fragment.startswith((\" \", \"\\n\", \".\", \",\", \"!\", \"?\", \":\", \";\")) else \" \"\\n')
new_lines.append('        return current + separator + fragment\\n')
new_lines.extend(lines[1184:])  # from line 1185 onward (index 1184)
with open('core/gemini_live_voice.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)