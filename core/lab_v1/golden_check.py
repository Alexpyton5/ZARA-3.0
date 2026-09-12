"""Bounded independent behavioral verifier for a copied ZARA reply classifier.

No imports, loops, filesystem or process access are allowed in model code.
Production is never changed by this verifier.
"""
import ast
import hashlib
import json
from pathlib import Path
import sys

AUTHORIZATION = 'golden:reply-status-sandbox-v1'
CASES = (
    ('Falha ao abrir o YouTube.', 'FALHOU'),
    ('Erro ao iniciar reprodução.', 'FALHOU'),
    ('Não consegui confirmar a janela.', 'FALHOU'),
    ('Nao foi executado.', 'FALHOU'),
    ('', 'FALHOU'),
    (None, 'FALHOU'),
    ('YouTube aberto e verificado.', 'OK'),
    ('Brilho definido para 40% e confirmado.', 'OK'),
    ('Quando?', 'PENDENTE'),
    ('Qual horário devo usar?', 'PENDENTE'),
)


def validate_code(code):
    if not isinstance(code, str) or not 1 <= len(code.encode('utf-8')) <= 6000:
        raise ValueError('Classifier code size outside scope')
    tree = ast.parse(code)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError('One classifier function required')
    fn = tree.body[0]
    if (fn.name != '_jarvis_reply_status' or fn.decorator_list or
            len(fn.args.args) != 1 or fn.args.args[0].arg != 'reply' or
            fn.args.vararg or fn.args.kwarg or fn.args.defaults or fn.args.kwonlyargs):
        raise ValueError('Classifier signature outside scope')
    allowed = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign,
        ast.Name, ast.Load, ast.Store, ast.Constant, ast.Call, ast.Attribute, ast.If,
        ast.BoolOp, ast.Or, ast.And, ast.UnaryOp, ast.Not, ast.Compare, ast.In, ast.NotIn,
        ast.Eq, ast.NotEq, ast.Tuple, ast.List, ast.BinOp, ast.BitOr, ast.IfExp)
    if len(list(ast.walk(tree))) > 500:
        raise ValueError('Classifier AST exceeds scope')
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError('Unsupported classifier syntax: ' + type(node).__name__)
        if isinstance(node, ast.Name) and node.id.startswith('__'):
            raise ValueError('Private names forbidden')
        if isinstance(node, ast.Attribute) and node.attr not in ('strip', 'casefold', 'startswith'):
            raise ValueError('Only string classification methods allowed')
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Attribute) or
                isinstance(node.func, ast.Name) and node.func.id == 'str'):
            raise ValueError('Only str and classification methods allowed')
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 500:
            raise ValueError('Classifier constant exceeds scope')
    return tree


def check(code):
    tree = validate_code(code)
    namespace = {'__builtins__': {'str': str}}
    exec(compile(tree, '<sandbox-classifier>', 'exec'), namespace)
    classify = namespace['_jarvis_reply_status']
    results = [{'input': text, 'expected': expected, 'actual': classify(text)} for text, expected in CASES]
    return {'passed': all(r['expected'] == r['actual'] for r in results),
            'checks': results, 'method': 'independent_behavioral_cases',
            'sha256': hashlib.sha256(code.encode('utf-8')).hexdigest(), 'production_modified': False}


if __name__ == '__main__':
    result = check(Path(sys.argv[1]).read_text(encoding='utf-8'))
    print(json.dumps(result, ensure_ascii=True))
    raise SystemExit(0 if result['passed'] else 1)
