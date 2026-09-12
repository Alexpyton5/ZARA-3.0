"""Deterministic artifact postconditions; pure Python is interpreted, never executed on the host."""
import ast
import json
import operator

from core.tool_verifier import ToolVerifier, VerificationState
from core.tool_result import ToolVerificationResult


class PureFunctions:
    """Small bounded capability for pure functions, deliberately without imports or host access."""
    def __init__(self, source):
        if not isinstance(source, str) or len(source.encode()) > 32768: raise ValueError('SOURCE_LIMIT')
        tree = ast.parse(source)
        self.functions = {}
        for item in tree.body:
            if isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str): continue
            if not isinstance(item, ast.FunctionDef) or item.decorator_list or item.name.startswith('_'):
                raise ValueError('UNSUPPORTED_PYTHON: only public pure functions')
            if item.name in self.functions: raise ValueError('DUPLICATE_FUNCTION')
            if item.args.vararg or item.args.kwarg or item.args.kwonlyargs or item.args.posonlyargs:
                raise ValueError('UNSUPPORTED_SIGNATURE')
            self.functions[item.name] = item
        if not self.functions or len(list(ast.walk(tree))) > 1500: raise ValueError('AST_LIMIT')
        self.steps = 0

    def bounded(self, value):
        self.steps += 1
        if self.steps > 10000: raise ValueError('OPERATION_LIMIT')
        if len(json.dumps(value, ensure_ascii=True)) > 16384: raise ValueError('VALUE_LIMIT')
        if isinstance(value, (int, float)) and abs(value) > 1e12: raise ValueError('NUMBER_LIMIT')
        return value

    def call(self, name, args):
        self.bounded(args)
        fn = self.functions.get(name)
        if fn is None or len(args) != len(fn.args.args): raise ValueError('FUNCTION_SIGNATURE')
        scope = dict(zip((a.arg for a in fn.args.args), args))
        returned, value = self.statements(fn.body, scope)
        return self.bounded(value if returned else None)

    def statements(self, body, scope):
        for node in body:
            self.bounded(None)
            if isinstance(node, ast.Return): return True, self.expr(node.value, scope) if node.value else None
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant): continue
            if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets):
                value = self.expr(node.value, scope)
                for target in node.targets: scope[target.id] = value
            elif isinstance(node, ast.If):
                returned, value = self.statements(node.body if self.expr(node.test, scope) else node.orelse, scope)
                if returned: return True, value
            else: raise ValueError('UNSUPPORTED_STATEMENT:' + type(node).__name__)
        return False, None

    def expr(self, node, scope):
        self.bounded(None)
        if isinstance(node, ast.Constant): result = node.value
        elif isinstance(node, ast.Name):
            if node.id not in scope: raise ValueError('UNKNOWN_VARIABLE')
            result = scope[node.id]
        elif isinstance(node, (ast.List, ast.Tuple)):
            result = [self.expr(n, scope) for n in node.elts]
        elif isinstance(node, ast.Dict):
            result = {self.expr(k, scope): self.expr(v, scope) for k, v in zip(node.keys, node.values)}
        elif isinstance(node, ast.BinOp):
            operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                          ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
            left, right = self.expr(node.left, scope), self.expr(node.right, scope)
            if type(node.op) not in operations: raise ValueError('UNSUPPORTED_OPERATOR')
            if isinstance(node.op, ast.Mult) and (isinstance(left, (str, list)) or isinstance(right, (str, list))):
                count, sequence = (right, left) if isinstance(left, (str, list)) else (left, right)
                if type(count) is not int or len(sequence) * max(0, count) > 4096: raise ValueError('VALUE_LIMIT')
            if isinstance(node.op, ast.Mod) and isinstance(left, str): raise ValueError('UNSUPPORTED_FORMAT')
            result = operations[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp):
            functions = {ast.Not: operator.not_, ast.USub: operator.neg, ast.UAdd: operator.pos}
            if type(node.op) not in functions: raise ValueError('UNSUPPORTED_OPERATOR')
            result = functions[type(node.op)](self.expr(node.operand, scope))
        elif isinstance(node, ast.BoolOp):
            result = self.expr(node.values[0], scope)
            for child in node.values[1:]:
                if isinstance(node.op, ast.And) and not result: break
                if isinstance(node.op, ast.Or) and result: break
                result = self.expr(child, scope)
        elif isinstance(node, ast.IfExp):
            result = self.expr(node.body if self.expr(node.test, scope) else node.orelse, scope)
        elif isinstance(node, ast.Compare):
            operations = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.Gt: operator.gt,
                          ast.LtE: operator.le, ast.GtE: operator.ge, ast.Is: operator.is_, ast.IsNot: operator.is_not,
                          ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}
            left = self.expr(node.left, scope); result = True
            for op, other in zip(node.ops, node.comparators):
                right = self.expr(other, scope)
                if type(op) not in operations: raise ValueError('UNSUPPORTED_OPERATOR')
                result = result and operations[type(op)](left, right); left = right
        elif isinstance(node, ast.Call):
            if node.keywords: raise ValueError('UNSUPPORTED_KEYWORDS')
            args = [self.expr(n, scope) for n in node.args]
            functions = {'str': str, 'int': int, 'float': float, 'bool': bool, 'len': len,
                         'abs': abs, 'round': round, 'min': min, 'max': max, 'sum': sum, 'sorted': sorted}
            if isinstance(node.func, ast.Name) and node.func.id in functions:
                result = functions[node.func.id](*args)
            elif isinstance(node.func, ast.Attribute):
                obj = self.expr(node.func.value, scope)
                allowed = {'strip', 'lstrip', 'rstrip', 'lower', 'upper', 'casefold', 'title', 'capitalize',
                           'startswith', 'endswith', 'split', 'join', 'replace', 'count', 'find', 'isdigit', 'isalpha'}
                if not isinstance(obj, str) or node.func.attr not in allowed: raise ValueError('UNSUPPORTED_METHOD')
                if node.func.attr == 'replace' and len(obj) * (1 + sum(len(str(a)) for a in args)) > 16384:
                    raise ValueError('VALUE_LIMIT')
                result = getattr(obj, node.func.attr)(*args)
            else: raise ValueError('HOST_ACCESS_FORBIDDEN')
        elif isinstance(node, ast.Subscript):
            value = self.expr(node.value, scope)
            index = (slice(self.expr(node.slice.lower, scope) if node.slice.lower else None,
                           self.expr(node.slice.upper, scope) if node.slice.upper else None,
                           self.expr(node.slice.step, scope) if node.slice.step else None)
                     if isinstance(node.slice, ast.Slice) else self.expr(node.slice, scope))
            result = value[index]
        else: raise ValueError('UNSUPPORTED_EXPRESSION:' + type(node).__name__)
        return self.bounded(result)


def validate_acceptance(value, capability):
    if not isinstance(value, dict): raise ValueError('ACCEPTANCE_REQUIRED')
    method = value.get('method')
    if capability == 'artifact.python':
        cases = value.get('cases')
        if method != 'python_cases' or not isinstance(cases, list) or not 2 <= len(cases) <= 20:
            raise ValueError('INDEPENDENT_CASES_REQUIRED')
        for case in cases:
            if (not isinstance(case, dict) or not isinstance(case.get('function'), str)
                    or not isinstance(case.get('args'), list) or 'expected' not in case): raise ValueError('INVALID_CASE')
        if len({json.dumps([c['function'], c['args']], sort_keys=True) for c in cases}) != len(cases):
            raise ValueError('DUPLICATE_CASES')
    elif capability in ('artifact.text', 'artifact.json'):
        from core.lab_v1.real_work_contract import _validate_text_constraints, _validate_json_schema
        (_validate_text_constraints if capability == 'artifact.text' else _validate_json_schema)(value)
    else: raise ValueError('UNSUPPORTED_CAPABILITY')
    if len(json.dumps(value)) > 12000: raise ValueError('ACCEPTANCE_LIMIT')


class ArtifactVerifier(ToolVerifier):
    def verify(self, parameters, result_data):
        source = result_data; acceptance = parameters['acceptance']; capability = parameters['capability']
        results = []
        try:
            validate_acceptance(acceptance, capability)
            if capability == 'artifact.python':
                program = PureFunctions(source)
                for case in acceptance['cases']:
                    actual = program.call(case['function'], case['args'])
                    results.append({**case, 'actual': actual, 'passed': actual == case['expected']})
                passed = all(c['passed'] for c in results)
            else:
                if capability == 'artifact.json':
                    import jsonschema
                    jsonschema.validate(json.loads(source), acceptance['schema'])
                    passed = True
                    results = [{'schema_valid': True}]
                else:
                    passed = (acceptance['min_chars'] <= len(source) <= acceptance['max_chars']
                              and all(section in source for section in acceptance.get('required_sections', [])))
                    results = [{'length': len(source), 'constraints_satisfied': passed}]
            return ToolVerificationResult(state=VerificationState.VERIFIED if passed else VerificationState.FAILED,
                                          proof={'method': acceptance['method'], 'checks': results}, confidence=1.0)
        except Exception as exc:
            return ToolVerificationResult(state=VerificationState.FAILED,
                proof={'method': acceptance.get('method'), 'checks': results}, error=str(exc)[:300], confidence=0.0)
