import ast, os

# Check the largest files for class definitions and their methods/attributes
files_to_check = ['core/ipc_handlers.py', 'core/model_router.py', 'core/aprendizado.py', 'core/zara_orchestrator.py', 'core/autonomy_engine.py']

for filepath in files_to_check:
    if not os.path.exists(filepath):
        continue
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    print(f"\n=== {os.path.relpath(filepath)} ===")
    
    # Count top-level def statements
    tree = ast.parse(content)
    methods = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    
    print(f"  Top-level functions: {len(methods)}")
    print(f"  Classes: {len(classes)}")
    
    for cls in classes:
        # Get methods in this class
        class_methods = []
        class_attrs = []
        for node in ast.walk(cls):
            if isinstance(node, ast.FunctionDef):
                class_methods.append(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        class_attrs.append(target.id)
        
        print(f"  Class {cls.name}: {len(class_methods)} methods, {len(class_attrs)} attr references in init")
        if class_methods:
            print(f"    Methods: {class_methods[:10]}...")