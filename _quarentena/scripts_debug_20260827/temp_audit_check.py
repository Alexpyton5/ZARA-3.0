import ast, sys

path = "/c/Users/alexp/Downloads/ZARA 3.0 CLEAN 002/core/model_router.py"
try:
    with open(path) as f:
        tree = ast.parse(f.read())
    # Count top-level defs and classes
    defs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('def ')]
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    imports = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
    print(f'File: {path}')
    print(f'Functions (def/async def): {len(defs)}')
    print(f'Classes: {len(classes)}')
    print(f'ImportFrom modules: {[i.module for i in imports]}')
except Exception as e:
    print(f'Error: {e}')