import ast
import os
import sys

ACTIONS_DIR = os.path.join(os.path.dirname(__file__), 'core', 'actions')
mapping = {}  # action -> module (without core.actions prefix)

for filename in os.listdir(ACTIONS_DIR):
    if not filename.endswith('.py') or filename == '__init__.py':
        continue
    module_name = filename[:-3]
    filepath = os.path.join(ACTIONS_DIR, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            continue
    for node in ast.walk(tree):
        # Look for decorators
        if isinstance(node, ast.FunctionDef):
            for deco in node.decorator_list:
                # Check if deco is ast.Name with id 'action' or ast.Attribute with attr 'action'
                if isinstance(deco, ast.Name) and deco.id == 'action':
                    # No arguments, we need to get the name from the function name? Actually @action without args uses function name.
                    # We'll assume the action name is the function name (maybe stripped of _action suffix)
                    action_name = node.name
                    if action_name.endswith('_action'):
                        action_name = action_name[:-7]
                    mapping[action_name] = module_name
                elif isinstance(deco, ast.Call):
                    # deco.func could be Name or Attribute
                    func = deco.func
                    if isinstance(func, ast.Name) and func.id == 'action':
                        # keyword arguments
                        for kw in deco.keywords:
                            if kw.arg == 'name':
                                if isinstance(kw.value, ast.Constant):
                                    action_name = kw.value.value
                                    mapping[action_name] = module_name
                                break
                    elif isinstance(func, ast.Attribute) and func.attr == 'action':
                        # e.g., some.decorator.action
                        for kw in deco.keywords:
                            if kw.arg == 'name':
                                if isinstance(kw.value, ast.Constant):
                                    action_name = kw.value.value
                                    mapping[action_name] = module_name
                                break

# Print as Python dict
print('_ACTION_TO_MODULE = {')
for action, module in sorted(mapping.items()):
    print("    '{}': '{}',".format(action, module))
print('}')