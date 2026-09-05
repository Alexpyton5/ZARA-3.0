import ast

with open('/c/Users/alexp/Downloads/ZARA 3.0 CLEAN 002/core/ipc_handlers.py') as f:
    tree = ast.parse(f.read())

funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
print(f'Functions: {len(funcs)}')

classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
print(f'Classes: {len(classes)}')

for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef):
        num_lines = node.end_lineno - node.lineno + 1 if hasattr(node, "end_lineno") else "?"
        print(f'Class: {node.name}, lines: {num_lines}')