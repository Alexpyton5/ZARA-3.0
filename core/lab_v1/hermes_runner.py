"""Private child entrypoint: call installed Hermes file tools, never an agent loop.

Input is a bounded, validated file operation from the backend. This process has
an isolated HERMES_HOME and no provider credentials. No model controls a shell.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path


def main():
    request = json.loads(sys.stdin.read(100000))
    root = Path(request['hermes_root']).resolve()
    pin = json.loads(Path(__file__).with_name('hermes_pin.json').read_text())
    for name, digest in pin['files'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError('HERMES_VERSION_MISMATCH')
    sys.path.insert(0, str(root))
    from tools.file_operations import ShellFileOperations
    from tools.environments.local import LocalEnvironment

    # No LSP process or package installation belongs to the V0 file capability.
    class ScopedFileOperations(ShellFileOperations):
        def _lsp_service(self):
            return None

    env = LocalEnvironment(cwd=request['sandbox'], timeout=request['timeout_s'])
    try:
        ops = ScopedFileOperations(env)
        path = Path(request['path']).as_posix()
        if request['capability'] == 'files.write':
            result = ops.write_file(path, request['content'])
        elif request['capability'] == 'files.delete':
            result = ops.delete_file(path)
        else:
            raise ValueError('UNSUPPORTED_CAPABILITY')
        return {'ok': not bool(result.error), 'executor': 'hermes-agent',
                'version': pin['version'], 'error': 'HERMES_FILE_ERROR' if result.error else None}
    finally:
        env.cleanup()


if __name__ == '__main__':
    # Third-party diagnostics must not leak environment/config into artifacts.
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            outcome = main()
    except Exception as exc:
        outcome = {'ok': False, 'error': 'HERMES_RUNNER_' + type(exc).__name__}
    print(json.dumps(outcome))
