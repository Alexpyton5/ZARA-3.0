"""LAB-11: the Lab sandbox must allow the local asyncio self-pipe and nothing else.

ASYNC LOCAL: ALLOWED / EXTERNAL NETWORK: DENIED.

On Windows an asyncio event loop cannot exist without ``socket.socketpair()``,
which CPython emulates in ``socket._fallback_socketpair`` as an ephemeral
loopback bind + connect to itself.  Before this change the sandbox audit hook
refused every ``socket.*`` event, so no mission whose tests touch asyncio could
pass verification - neither the baseline run nor the candidate run.

Every negative case below really performs the forbidden call inside the real
sandbox subprocess and observes the real refusal.  Nothing here is simulated,
and no case asserts a message without the operation having been attempted.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.lab_v1.candidate_source import (
    SANDBOX_NETWORK_POLICY,
    CandidateSource,
)
from core.lab_v1.candidate_source import TestResult as SandboxRun

# A routable public IP written as a literal on purpose: it exercises the
# connect/sendto gate rather than the DNS gate, which is covered separately.
EXTERNAL_IP = "93.184.216.34"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_in_sandbox(tmp_path: Path, body: str, *, timeout: float = 60) -> SandboxRun:
    """Apply a real edit and run ``body`` as a test inside the real sandbox."""
    workspace = tmp_path / "workspace"
    _write(workspace / "core" / "__init__.py", "")
    _write(workspace / "core" / "calculator.py", "def add(a, b):\n    return a - b\n")
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        ["core/calculator.py", "tests/test_policy.py"],
        python_executable=Path(sys.executable),
    )
    candidate.prepare()
    candidate.apply_edits(
        [
            # The sandbox refuses test-only edits, so the mission carries a real
            # source change alongside the test it is meant to prove.
            {"path": "core/calculator.py", "content": "def add(a, b):\n    return a + b\n"},
            {"path": "tests/test_policy.py", "content": body},
        ]
    )
    return candidate.run_pytest(["tests/test_policy.py"], timeout_seconds=timeout)


# --------------------------------------------------------------------------
# The policy is stated, not implied.
# --------------------------------------------------------------------------

def test_policy_is_declared_in_code_and_in_the_runner() -> None:
    assert SANDBOX_NETWORK_POLICY == "ASYNC LOCAL: ALLOWED; EXTERNAL NETWORK: DENIED"
    runner = CandidateSource._RUNNER
    assert "ASYNC LOCAL: ALLOWED" in runner
    assert "EXTERNAL NETWORK: DENIED" in runner
    # The guard is a named, reviewable predicate rather than a loose exception.
    assert "def is_event_loop_self_pipe(" in runner
    assert "_SELF_PIPE_CODES" in runner


def test_runner_logs_the_policy_on_every_sandbox_run(tmp_path: Path) -> None:
    result = _run_in_sandbox(
        tmp_path, "def test_trivial():\n    assert True\n"
    )
    assert result.exit_code == 0
    assert "[SANDBOX_POLICY] ASYNC LOCAL: ALLOWED; EXTERNAL NETWORK: DENIED" in result.stderr


# --------------------------------------------------------------------------
# Positive: the local async runtime really works now.
# --------------------------------------------------------------------------

ASYNCIO_BODY = """
import asyncio


async def _double(value):
    await asyncio.sleep(0)
    return value * 2


def test_asyncio_run():
    assert asyncio.run(_double(21)) == 42


def test_create_task_gather_sleep():
    async def main():
        task = asyncio.create_task(_double(2))
        results = await asyncio.gather(task, _double(3), asyncio.sleep(0.01))
        return results[0], results[1]

    assert asyncio.run(main()) == (4, 6)


def test_event_loop_can_be_made_and_closed_twice():
    for _ in range(2):
        loop = asyncio.new_event_loop()
        try:
            assert loop.run_until_complete(_double(5)) == 10
        finally:
            loop.close()


def test_event_loops_in_worker_threads():
    # The guard tracks the pending self-pipe listener per thread, so loops
    # built concurrently in several threads must not invalidate each other.
    import threading

    results = []
    errors = []

    def worker(value):
        try:
            results.append(asyncio.run(_double(value)))
        except BaseException as exc:  # noqa: BLE001 - the failure is the point
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert errors == []
    assert sorted(results) == [0, 2, 4, 6, 8, 10]
"""


def test_asyncio_runs_inside_the_sandbox(tmp_path: Path) -> None:
    result = _run_in_sandbox(tmp_path, ASYNCIO_BODY)

    assert result.exit_code == 0, result.stdout + result.stderr
    assert result.counts["passed"] == 4
    assert result.counts["failed"] == 0
    assert "NETWORK_FORBIDDEN" not in result.stdout


PYTEST_ASYNCIO_BODY = """
import asyncio

import pytest


@pytest.mark.asyncio
async def test_real_project_shape_async():
    # Same shape as the project's own async tests (see tests/test_claude_brain.py):
    # a pytest-asyncio coroutine test that awaits real asyncio primitives.
    async def slow():
        await asyncio.sleep(10)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(slow(), timeout=0.01)
    assert await asyncio.gather(asyncio.sleep(0, "ok")) == ["ok"]
"""


def test_pytest_asyncio_plugin_works_inside_the_sandbox(tmp_path: Path) -> None:
    pytest.importorskip("pytest_asyncio")
    result = _run_in_sandbox(tmp_path, PYTEST_ASYNCIO_BODY)

    assert result.exit_code == 0, result.stdout + result.stderr
    assert result.counts["passed"] == 1


# --------------------------------------------------------------------------
# Negative: everything that is not the self-pipe is still refused.
# --------------------------------------------------------------------------

TCP_EXTERNAL = f"""
import socket


def test_tcp_to_public_internet():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(3)
    client.connect(({EXTERNAL_IP!r}, 80))
"""

UDP_EXTERNAL = f"""
import socket


def test_udp_to_public_internet():
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.sendto(b"zara", ({EXTERNAL_IP!r}, 53))
"""

PUBLIC_LISTENER = """
import socket


def test_bind_public_listener():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", 8099))
    server.listen(1)
"""

LOOPBACK_LISTENER = """
import socket


def test_bind_loopback_listener_outside_the_primitive():
    # Even loopback is refused when the caller is not the self-pipe primitive:
    # the allowance is tied to socketpair, not to "any local socket".
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
"""

DNS_LOOKUP = """
import socket


def test_dns_resolution():
    socket.getaddrinfo("example.com", 80)
"""

LOOKALIKE_PRIMITIVE = """
import socket


def _fallback_socketpair(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
    # A byte-for-byte plausible copy of the stdlib helper, same name, same
    # shape, same loopback address. It is a different code object, so the
    # allowance must not apply to it.
    lsock = socket.socket(family, type, proto)
    lsock.bind(("127.0.0.1", 0))
    lsock.listen()
    addr, port = lsock.getsockname()[:2]
    csock = socket.socket(family, type, proto)
    csock.connect((addr, port))
    return lsock.accept()[0], csock


def test_lookalike_socketpair_is_not_the_primitive():
    _fallback_socketpair()
"""

HIJACKED_TO_PUBLIC_IP = f"""
import socket
import types


def test_real_primitive_cannot_be_reaimed_at_the_internet():
    # Hardest case: reuse the genuine stdlib code object - so the code-object
    # identity check passes - but feed it globals whose "localhost" is a public
    # address. The address lock has to catch it.
    original = socket._fallback_socketpair
    poisoned = dict(original.__globals__)
    poisoned["_LOCALHOST"] = {EXTERNAL_IP!r}
    clone = types.FunctionType(
        original.__code__, poisoned, "_fallback_socketpair", original.__defaults__
    )
    clone()
"""

HIJACKED_TO_OTHER_LOCAL_PORT = """
import socket
import types


class LyingSocket(socket.socket):
    # A real socket that lies about where it is bound, so the connect target
    # chosen inside socketpair would be a different local service's port.
    def getsockname(self):
        return ("127.0.0.1", 65000)


def test_real_primitive_cannot_be_reaimed_at_another_local_port():
    original = socket._fallback_socketpair
    poisoned = dict(original.__globals__)
    poisoned["socket"] = LyingSocket
    clone = types.FunctionType(
        original.__code__, poisoned, "_fallback_socketpair", original.__defaults__
    )
    clone()
"""

C_LEVEL_SOCKET = f"""
import _socket


def test_c_level_socket_bypasses_the_python_wrapper():
    # The audit events come from socketmodule.c, so dropping to the C module
    # to dodge socket.py buys nothing.
    raw = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    raw.settimeout(3)
    raw.connect(({EXTERNAL_IP!r}, 80))
"""

SUBPROCESS_INHERITANCE = """
import subprocess
import sys


def test_subprocess_cannot_be_spawned_to_inherit_the_allowance():
    # A child process would not carry this process's audit hook, so the only
    # safe answer is that no child can be created at all.
    subprocess.run(
        [sys.executable, "-c", "import socket; socket.socket().connect(('93.184.216.34', 80))"],
        capture_output=True,
    )
"""


@pytest.mark.parametrize(
    ("case", "body", "expected"),
    [
        ("tcp_external", TCP_EXTERNAL, "EXTERNAL NETWORK: DENIED (socket.connect)"),
        ("udp_external", UDP_EXTERNAL, "EXTERNAL NETWORK: DENIED (socket.sendto)"),
        ("public_listener", PUBLIC_LISTENER, "EXTERNAL NETWORK: DENIED (socket.bind)"),
        ("loopback_listener", LOOPBACK_LISTENER, "EXTERNAL NETWORK: DENIED (socket.bind)"),
        ("dns", DNS_LOOKUP, "EXTERNAL NETWORK: DENIED (socket.getaddrinfo)"),
        ("lookalike_primitive", LOOKALIKE_PRIMITIVE, "EXTERNAL NETWORK: DENIED (socket.bind)"),
        (
            "hijacked_to_public_ip",
            HIJACKED_TO_PUBLIC_IP,
            "EXTERNAL NETWORK: DENIED (socket.bind)",
        ),
        (
            "hijacked_to_other_local_port",
            HIJACKED_TO_OTHER_LOCAL_PORT,
            "EXTERNAL NETWORK: DENIED (socket.connect)",
        ),
        ("c_level_socket", C_LEVEL_SOCKET, "EXTERNAL NETWORK: DENIED (socket.connect)"),
        ("subprocess", SUBPROCESS_INHERITANCE, "PROCESS_EXECUTION_FORBIDDEN"),
    ],
)
def test_forbidden_network_operations_are_really_refused(
    tmp_path: Path, case: str, body: str, expected: str
) -> None:
    result = _run_in_sandbox(tmp_path, body)

    output = result.stdout + result.stderr
    assert result.exit_code != 0, f"{case} was not refused: {output}"
    assert result.counts["failed"] == 1, output
    assert expected in output, f"{case} refused for the wrong reason: {output}"


SOCKETPAIR_EXTENT = f"""
import socket


def test_socketpair_itself_is_allowed():
    left, right = socket.socketpair()
    try:
        left.send(b"x")
        assert right.recv(1) == b"x"
        # Both ends are connected to each other and to nothing else.
        assert left.getpeername() == right.getsockname()
        assert left.getsockname()[0] in ("127.0.0.1", "::1")
    finally:
        left.close()
        right.close()


def test_a_socketpair_end_still_cannot_reach_the_internet():
    left, right = socket.socketpair()
    try:
        stray = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        stray.settimeout(3)
        stray.connect(({EXTERNAL_IP!r}, 80))
    finally:
        left.close()
        right.close()
"""


def test_the_allowed_primitive_is_socketpair_and_reaches_only_itself(tmp_path: Path) -> None:
    """State the full extent of the liberation instead of leaving it implicit.

    Before LAB-11 a direct ``socket.socketpair()`` was refused too, which is
    what broke asyncio.  It is allowed now, and this pins down exactly how far
    that goes: a pair wired to itself over loopback, with no reach outward.
    """
    result = _run_in_sandbox(tmp_path, SOCKETPAIR_EXTENT)

    output = result.stdout + result.stderr
    assert result.counts["passed"] == 1, output
    assert result.counts["failed"] == 1, output
    assert "EXTERNAL NETWORK: DENIED (socket.connect)" in output


def test_allowance_does_not_leak_into_the_rest_of_the_same_run(tmp_path: Path) -> None:
    """asyncio working must not mean the process gained network in that run."""
    body = f"""
import asyncio
import socket


def test_asyncio_still_works():
    async def work():
        await asyncio.sleep(0)
        return "ok"

    assert asyncio.run(work()) == "ok"


def test_network_still_denied_after_the_loop_ran():
    asyncio.run(asyncio.sleep(0))
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(3)
    client.connect(({EXTERNAL_IP!r}, 80))
"""
    result = _run_in_sandbox(tmp_path, body)

    output = result.stdout + result.stderr
    assert result.counts["passed"] == 1, output
    assert result.counts["failed"] == 1, output
    assert "EXTERNAL NETWORK: DENIED (socket.connect)" in output
