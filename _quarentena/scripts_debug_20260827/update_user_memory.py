import sys
import re

# Read the file
with open('memory/user_memory.py', 'r', encoding='utf-8') as f:
    content = f.read()

# We will replace the search method and add the helper method.

# First, let's find the search method.
# We will use a regex to find the search method and capture the indentation and the entire method body until the next method or class.

# We define the pattern for the search method.
pattern = r'(\\s+def search\\(self, query: str, \\*, category: str \\| None = None,\\n.*?\\n)(?=\\s+def |\\s+class |\\Z)'

# We use the DOTALL flag to make . match newlines.
# We will replace the match with our new search method and then add the helper method after it.

# But note: we want to keep the indentation of the method.

# We will instead split the content and replace the method by line numbers.

# Given the complexity, we will do a simple string replacement for the entire method body.

# We know the old search method string from the old content? 
# We can extract it by finding the start and end as described.

# We will do the start and end by line numbers.

lines = content.splitlines(keepends=True)

# Find the line index of the start of the search method.
start_line = -1
for i, line in enumerate(lines):
    if line.strip().startswith('def search(self, query: str, *, category: str | None = None,'):
        start_line = i
        break

if start_line == -1:
    print('Could not find the search method')
    sys.exit(1)

# Find the end line: the next line that has the same indentation as the start_line and is not part of the method body.
# The indentation of the start_line is the number of leading spaces.
indent = len(lines[start_line]) - len(lines[start_line].lstrip())
end_line = len(lines)
for i in range(start_line+1, len(lines)):
    line = lines[i]
    # If the line is empty or only spaces, we continue.
    if line.strip() == '':
        continue
    # Check the indentation of this line.
    current_indent = len(line) - len(line.lstrip())
    if current_indent == indent:
        # This line is at the same indentation as the def line, so it's the start of another method or class.
        end_line = i
        break
    # If we find a line with less indentation, then we are out of the class? 
    # But note: the class methods are at the same indentation level.
    # We break when we find a line with the same indentation as the def line (which means we are at the next method or class attribute).
    # We break at the first such line.

# Now, we have the lines from start_line to end_line-1 as the old search method.

# We will replace these lines with our new search method lines.

new_search_method_lines = [
    '    def search(self, query: str, *, category: str | None = None,\n',
    '               since: float | None = None, until: float | None = None,\n',
    '               limit: int = 5) -> list[dict]:\n',
    '        \"\"\"Busca por intervalo temporal + correspondencia lexica simples.\"\"\"\n',
    '        # For semantic_fact category, we use embedding-based search.\n',
    '        # For other categories, we use the existing lexical search.\n',
    '        if category == \"semantic_fact\":\n',
            '            return self._search_semantic_fact(query, since=since, until=until, limit=limit)\n',
        '        else:\n',
            '            # Use the existing search for other categories or when category is None (which means all categories, but we don\\'t change that)\n',
            '            q = (query or \"\").strip().lower()\n',
            '            tokens = set(re.findall(r\"[a-z0-9à-ú]{3,}\", q))\n',
            '            with self._lock:\n',
            '                with self._connect() as conn:\n',
            '                    sql = \"SELECT * FROM user_facts WHERE status != \\'forgotten\\'\"\n',
            '                    args: list = []\n',
            '                    if category:\n',
            '                        sql += \" AND category=?\"\n',
            '                        args.append(category)\n',
            '                    if since is not None:\n',
            '                        sql += \" AND created_at >= ?\"\n',
            '                        args.append(since)\n',
            '                    if until is not None:\n',
            '                        sql += \" AND created_at <= ?\"\n',
            '                        args.append(until)\n',
            '                    sql += \" ORDER BY updated_at DESC\"\n',
            '                    rows = conn.execute(sql, args).fetchall()\n',
            '            out = []\n',
            '            for r in rows:\n',
            '                fact_lower = (r[\"fact\"] or \"\").lower()\n',
            '                if tokens:\n',
            '                    fact_tokens = set(re.findall(r\"[a-z0-9à-ú]{3,}\", fact_lower))\n',
            '                    score = len(tokens.intersection(fact_tokens)) / max(1, len(tokens))\n',
            '                    if score <= 0.0:\n',
            '                        continue\n',
            '                else:\n',
            '                    score = 1.0\n',
            '                d = dict(r)\n',
            '                d[\"_score\"] = round(score, 3)\n',
            '                out.append(d)\n',
            '            out.sort(key=lambda x: (x[\"_score\"], x[\"updated_at\"]), reverse=True)\n',
            '            return out[:max(1, min(limit, 20))]\n'
]

# Now, we will add the helper method after the search method.
# We will insert it after the end_line (which is the line after the old search method).

new_helper_method_lines = [
    '    def _search_semantic_fact(self, query: str, *, since: float | None = None,\n',
    '                              until: float | None = None, limit: int = 5) -> list[dict]:\n',
    '        \"\"\"Search for semantic facts using embedding-based similarity.\"\"\"\n',
    '        # We will fetch the most recent semantic facts (up to a limit) and then compute embeddings.\n',
    '        # We set a safety limit for the number of facts to fetch from the database to avoid too many embeddings computations.\n',
    '        MAX_FACTS_TO_FETCH = 1000\n',
    '        with self._lock:\n',
    '            with self._connect() as conn:\n',
    '                sql = \"\"\"SELECT id, fact, created_at, confidence, status, source, ref, updated_at, last_used\n",
    '                          FROM user_facts\n",
    '                          WHERE category = \\'semantic_fact\\' AND status != \\'forgotten\\'\"\"\"\n",
    '                args: list = []\n',
    '                if since is not None:\n',
    '                    sql += \" AND created_at >= ?\"\n',
    '                    args.append(since)\n',
    '                if until is not None:\n',
    '                    sql += \" AND created_at <= ?\"\n',
    '                    args.append(until)\n',
    '                sql += \" ORDER BY updated_at DESC LIMIT ?\"  # We limit to the most recent facts\n",
    '                args.append(MAX_FACTS_TO_FETCH)\n',
    '                rows = conn.execute(sql, args).fetchall()\n',
    '        if not rows:\n',
            '            return []\n',
            '        # Compute the embedding for the query\n',
            '        query_embedding = _embed(query)\n',
            '        # Precompute the embeddings for the facts? We will compute on the fly for each fact.\n',
            '        # We will create a list of (fact_dict, embedding) for each fact.\n',
            '        facts_with_embedding = []\n',
            '        for row in rows:\n',
            '            fact_dict = dict(row)\n",
            '            fact_text = fact_dict[\"fact\"]\n",
            '            fact_embedding = _embed(fact_text)\n',
            '            facts_with_embedding.append((fact_dict, fact_embedding))\n',
            '        # Compute cosine similarity for each fact\n',
            '        scored_facts = []\n',
            '        for fact_dict, fact_embedding in facts_with_embedding:\n',
            '            similarity = _cosine(query_embedding, fact_embedding)\n',
            '            scored_facts.append((fact_dict, similarity))\n',
            '        # Sort by similarity descending, then by updated_at descending (to break ties)\n',
            '        scored_facts.sort(key=lambda x: (x[1], x[0][\"updated_at\"]), reverse=True)\n',
            '        # Take the top `limit` facts\n',
            '        top_facts = scored_facts[:max(1, min(limit, 20))]\n',
            '        # Format the result as the existing search method does (with _score)\n',
            '        result = []\n',
            '        for fact_dict, similarity in top_facts:\n',
            '            fact_dict[\"_score\"] = round(similarity, 3)\n',
            '            result.append(fact_dict)\n',
            '        return result\n'
]

# Now, we will build the new lines:
#   lines[0:start_line] + new_search_method_lines + ['\\n'] + new_helper_method_lines + lines[end_line:]

# But note: we want to separate the helper method from the search method by a blank line.

new_lines = lines[:start_line] + new_search_method_lines + ['\n'] + new_helper_method_lines + lines[end_line:]

# Join the lines
new_content = ''.join(new_lines)

# Now, we need to add the import for _embed and _cosine from memory.episodic_memory at the top of the file.
# We will add it after the existing imports.

# We will find the line after the last import.
# We will look for a line that is not an import and not a comment and not empty, and then insert after the last import line.

# We will do a simple approach: we will insert after the line that contains 'from typing import Any' or similar.

# We will split the new_content into lines again.
new_lines = new_content.splitlines(keepends=True)

# Find the index of the last import line.
last_import_line = -1
for i, line in enumerate(new_lines):
    stripped = line.strip()
    if stripped.startswith('import ') or stripped.startswith('from '):
        last_import_line = i

if last_import_line == -1:
    print('Could not find any import line')
    sys.exit(1)

# We will insert our import after the last_import_line.
import_line = 'from memory.episodic_memory import _embed, _cosine\n'
# We will insert it at last_import_line+1.
new_lines = new_lines[:last_import_line+1] + [import_line] + new_lines[last_import_line+1:]

# Join the lines
new_content = ''.join(new_lines)

# Write the file
with open('memory/user_memory.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('File updated successfully.')