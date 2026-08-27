"""
Action Registry — Decorator-based action system for ZARA 3.0.
Actions are the atomic units of automation (terminal, files, web, code, OS, etc.).
"""
from __future__ import annotations

import asyncio
import inspect
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.action_confirmation import (
    ConfirmationBroker,
    ConfirmationCapacityError,
    ConfirmationProof,
    ConfirmationSerializationError,
    build_confirmation_summary,
)


@dataclass
class ActionResult:
    """Result of an action execution."""
    success: bool
    output: str = ""
    error: str = ""
    data: Any = None
    duration_ms: float = 0
    # ZARA-NAO-VERIFICADO-001
    #
    # Alex: *"tente deixar ela sem mentiras e sem chutes; se não souber, ela deve
    # ser sempre transparente"*. E a regra que saiu da pesquisa da Apple:
    # **ação executada mas não confirmada nunca aparece verde**.
    #
    # Até aqui só existiam dois estados: deu certo ou deu errado. Faltava o
    # terceiro, que é o mais honesto e o mais comum na prática — *fiz, e não
    # tenho como provar*. Mandar uma mensagem, apertar uma tecla num app de
    # terceiro, disparar um atalho: nada disso devolve confirmação.
    #
    # Sem este campo, essas ações viravam sucesso liso, e "sucesso liso" sem
    # prova é exatamente o falso sucesso que este projeto inteiro combate.
    #
    # `True`  = houve postcondição observada (releitura, estado do Windows).
    # `False` = despachou e não deu para conferir. Não é falha: é incerteza,
    #           e ela precisa aparecer como incerteza para Alex.
    verificado: bool = True

    @property
    def incerto(self) -> bool:
        """Deu certo até onde deu para ver, mas ninguém confirmou."""
        return bool(self.success) and not self.verificado

    def __bool__(self) -> bool:
        return self.success

    def __str__(self) -> str:
        return self.output or self.error or "OK"


@dataclass
class ActionSpec:
    """Action specification (metadata)."""
    name: str
    description: str
    parameters: dict  # JSON Schema
    category: str = "general"
    requires_confirmation: bool = False
    async_execution: bool = False
    tags: list[str] = field(default_factory=list)
    risk: str = "LOW"  # LOW | MEDIUM | HIGH (ZARA-PC-CONTROL-FOUNDATION-001)
    capability: str = "READ_ONLY"  # execution domain; risk remains independent


class ActionRegistry:
    """Central registry for all ZARA actions."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._actions: dict[str, Callable] = {}
        self._specs: dict[str, ActionSpec] = {}
        self._categories: dict[str, list[str]] = {}
        self._confirmation_broker = ConfirmationBroker()
        # Independent risk gate: MEDIUM actions require confirmation while
        # false. Supercérebro changes capabilities, not this policy.
        self.medium_risk_open = False
        # Remote/agentic capability gate. Local deterministic actions remain
        # usable without Hermes; risk gates below are always independent.
        self.pc_control_allowed = False

        # Register core actions
        self._register_core_actions()

    def _register_core_actions(self):
        """Register built-in core actions."""
        # Actions are auto-registered via @action decorator on import

    def register(
        self,
        name: str,
        func: Callable,
        description: str = "",
        parameters: dict = None,
        category: str = "general",
        requires_confirmation: bool = False,
        async_execution: bool = False,
        tags: list[str] = None,
        risk: str = "LOW",
        capability: str = "READ_ONLY",
    ):
        """Register an action."""
        normalized_risk = str(risk).strip().upper()
        if normalized_risk not in {"LOW", "MEDIUM", "HIGH"}:
            raise ValueError(f"Invalid action risk: {risk!r}")

        normalized_capability = str(capability).strip().upper()
        valid_capabilities = {
            "READ_ONLY",
            "LOCAL_PC_CONTROL",
            "PC_CONTROL",
            "REMOTE_PC_CONTROL",
            "AGENTIC_PC_CONTROL",
            "FILES_MUTATE",
            "CODE_EXECUTION",
            "SYSTEM_POWER",
        }
        if normalized_capability not in valid_capabilities:
            raise ValueError(f"Invalid action capability: {capability!r}")

        if name in self._actions:
            print(f"[ActionRegistry] Warning: Overwriting action '{name}'")

        # Validate capability-category combinations
        # LOCAL_PC_CONTROL must be in a recognized OS/action category
        # Reject "general" and "mcp" - they are not valid OS categories
        if normalized_capability == "LOCAL_PC_CONTROL" and category in {"general", "mcp"}:
            raise ValueError(
                f"Capability LOCAL_PC_CONTROL requires a valid category (os, audio, window, etc.), not '{category}'"
            )

        self._actions[name] = func

        # Build parameter schema from function signature if not provided
        if parameters is None:
            parameters = self._infer_parameters(func)

        spec = ActionSpec(
            name=name,
            description=description or func.__doc__ or "",
            parameters=parameters,
            category=category,
            requires_confirmation=requires_confirmation,
            async_execution=async_execution,
            tags=tags or [],
            risk=normalized_risk,
            capability=normalized_capability,
        )
        self._specs[name] = spec

        if category not in self._categories:
            self._categories[category] = []
        if name not in self._categories[category]:
            self._categories[category].append(name)

        print(f"[ActionRegistry] Registered: {name} ({category})")

    def _infer_parameters(self, func: Callable) -> dict:
        """Infer JSON Schema from function signature."""
        sig = inspect.signature(func)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls", "context"):
                continue

            param_type = "string"
            if param.annotation != inspect.Parameter.empty:
                if param.annotation is int:
                    param_type = "integer"
                elif param.annotation is float:
                    param_type = "number"
                elif param.annotation is bool:
                    param_type = "boolean"
                elif param.annotation is list:
                    param_type = "array"
                elif param.annotation is dict:
                    param_type = "object"

            properties[param_name] = {"type": param_type}

            if param.default == inspect.Parameter.empty:
                required.append(param_name)
            else:
                properties[param_name]["default"] = param.default

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def unregister(self, name: str):
        """Unregister an action."""
        if name in self._actions:
            spec = self._specs.pop(name, None)
            self._actions.pop(name, None)
            if spec and spec.category in self._categories:
                self._categories[spec.category] = [
                    a for a in self._categories[spec.category] if a != name
                ]

    def get(self, name: str) -> Callable | None:
        """Get action by name."""
        return self._actions.get(name)

    def get_spec(self, name: str) -> ActionSpec | None:
        """Get action spec by name."""
        return self._specs.get(name)

    def list_actions(self, category: str = None) -> list[str]:
        """List all registered actions, optionally filtered by category."""
        if category:
            return self._categories.get(category, []).copy()
        return list(self._actions.keys())

    def list_categories(self) -> list[str]:
        """List all categories."""
        return list(self._categories.keys())

    def get_all_specs(self) -> dict[str, ActionSpec]:
        """Get all action specs (for LLM function calling)."""
        return self._specs.copy()

    @staticmethod
    def _confirmation_metadata(spec: ActionSpec) -> dict[str, Any]:
        """Return the policy metadata bound into a confirmation fingerprint."""
        return {
            "risk": spec.risk,
            "capability": spec.capability,
            "category": spec.category,
            "requires_confirmation": spec.requires_confirmation,
            "parameters": spec.parameters,
        }

    def cancel_confirmation(self, confirmation_id: str) -> bool:
        """Cancel an in-memory confirmation without exposing its parameters."""
        return self._confirmation_broker.cancel(confirmation_id)

    def _check_action_gates(
        self,
        name: str,
        spec: ActionSpec | None,
        params: dict[str, Any],
        proof: Any = None,
    ) -> ActionResult | None:
        """Apply capability and risk gates before any action function runs."""
        if spec is None:
            return ActionResult(success=False, error="ACTION_POLICY_METADATA_MISSING")

        # Capability is checked before issuing or consuming a challenge.
        superbrain_required = spec.capability not in {"READ_ONLY", "LOCAL_PC_CONTROL"}
        if superbrain_required and not self.pc_control_allowed:
            if isinstance(proof, ConfirmationProof):
                self._confirmation_broker.cancel(proof.confirmation_id)
            return ActionResult(
                success=False,
                error=(
                    f"Action '{name}' exige permissão de controle do PC "
                    f"(capability={spec.capability}, Supercérebro OFF). "
                    "Para controlar o computador, ative o Supercérebro."
                ),
                duration_ms=0.0,
            )

        # Legacy confirmation remains valid only for MEDIUM actions. HIGH
        # always requires a one-shot proof from the separate confirmation IPC.
        medium_confirmed = params.pop("confirm", False) is True
        if spec.risk == "HIGH":
            if proof is not None and not isinstance(proof, ConfirmationProof):
                return ActionResult(
                    success=False,
                    error="CONFIRMATION_INVALID",
                    data={"status": "CONFIRMATION_INVALID"},
                )

            metadata = self._confirmation_metadata(spec)
            if proof is None:
                summary = build_confirmation_summary(name, params)
                if summary is None:
                    return ActionResult(
                        success=False,
                        error="CONFIRMATION_POLICY_MISSING",
                        data={"status": "CONFIRMATION_POLICY_MISSING"},
                    )
                try:
                    challenge = self._confirmation_broker.issue(
                        action=name,
                        metadata=metadata,
                        params=params,
                        summary=summary,
                    )
                except (ConfirmationCapacityError, ConfirmationSerializationError, RuntimeError):
                    return ActionResult(
                        success=False,
                        error="CONFIRMATION_UNAVAILABLE",
                        data={"status": "CONFIRMATION_UNAVAILABLE"},
                    )
                return ActionResult(
                    success=False,
                    error="CONFIRMATION_REQUIRED",
                    data={
                        "status": "CONFIRMATION_REQUIRED",
                        "confirmation": challenge.to_dict(),
                    },
                )

            allowed, status = self._confirmation_broker.consume(
                proof,
                action=name,
                metadata=metadata,
                params=params,
            )
            if not allowed:
                return ActionResult(
                    success=False,
                    error=status,
                    data={"status": status},
                )
            return None

        if isinstance(proof, ConfirmationProof):
            self._confirmation_broker.cancel(proof.confirmation_id)
            return ActionResult(
                success=False,
                error="CONFIRMATION_NOT_APPLICABLE",
                data={"status": "CONFIRMATION_NOT_APPLICABLE"},
            )

        if spec.risk == "MEDIUM" and not self.medium_risk_open and not medium_confirmed:
            return ActionResult(
                success=False,
                error=(
                    f"Action '{name}' é MEDIUM risk e exige confirmação "
                    "(confirm=true) ou política MEDIUM explícita."
                ),
                duration_ms=0.0,
            )
        return None

    def execute_confirmed(
        self,
        name: str,
        confirmation_id: str,
        action_fingerprint: str,
        **kwargs,
    ) -> ActionResult:
        """Execute using a proof created by the private confirmation IPC."""
        if name not in self._actions:
            self.cancel_confirmation(confirmation_id)
            return ActionResult(success=False, error=f"Action '{name}' not found")
        return self.execute(
            name,
            _zara_confirmation_proof=ConfirmationProof(
                confirmation_id=confirmation_id,
                action_fingerprint=action_fingerprint,
            ),
            **kwargs,
        )

    def execute(self, name: str, **kwargs) -> ActionResult:
        """Execute an action synchronously.

        HIGH-risk actions return a short-lived challenge and never accept the
        legacy confirm boolean. MEDIUM keeps its independent boolean/policy
        gate for compatibility.
        """
        func = self._actions.get(name)
        if not func:
            return ActionResult(success=False, error=f"Action '{name}' not found")

        spec = self._specs.get(name)
        start = time.perf_counter()

        proof = kwargs.pop("_zara_confirmation_proof", None)
        gate_result = self._check_action_gates(name, spec, kwargs, proof)
        if gate_result is not None:
            return gate_result

        try:
            # Check if async
            if spec and spec.async_execution:
                # Run in event loop
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                result = loop.run_until_complete(func(**kwargs))
            else:
                result = func(**kwargs)

            duration = (time.perf_counter() - start) * 1000

            if isinstance(result, ActionResult):
                result.duration_ms = duration
                self._audit_action(name, spec, result)
                return result
            elif isinstance(result, dict):
                out = ActionResult(success=True, output=json.dumps(result), data=result, duration_ms=duration)
                self._audit_action(name, spec, out)
                return out
            else:
                out = ActionResult(success=True, output=str(result), duration_ms=duration)
                self._audit_action(name, spec, out)
                return out

        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)

    def _audit_action(self, name: str, spec: ActionSpec | None, result: ActionResult) -> None:
        """Audit MEDIUM/HIGH executions without raw parameters (no secrets)."""
        try:
            if spec and spec.risk in ("MEDIUM", "HIGH"):
                from core.audit_log import audit_log
                audit_log().record(
                    action=name,
                    risk=spec.risk,
                    outcome="success" if result.success else "error",
                    error=None if result.success else str(result.error)[:200],
                )
        except Exception:
            pass

    async def execute_confirmed_async(
        self,
        name: str,
        confirmation_id: str,
        action_fingerprint: str,
        **kwargs,
    ) -> ActionResult:
        """Async equivalent of execute_confirmed()."""
        if name not in self._actions:
            self.cancel_confirmation(confirmation_id)
            return ActionResult(success=False, error=f"Action '{name}' not found")
        return await self.execute_async(
            name,
            _zara_confirmation_proof=ConfirmationProof(
                confirmation_id=confirmation_id,
                action_fingerprint=action_fingerprint,
            ),
            **kwargs,
        )

    async def execute_async(self, name: str, **kwargs) -> ActionResult:
        """Execute an action asynchronously."""
        func = self._actions.get(name)
        if not func:
            return ActionResult(success=False, error=f"Action '{name}' not found")

        spec = self._specs.get(name)
        start = time.perf_counter()

        proof = kwargs.pop("_zara_confirmation_proof", None)
        gate_result = self._check_action_gates(name, spec, kwargs, proof)
        if gate_result is not None:
            return gate_result

        try:
            if inspect.iscoroutinefunction(func):
                result = await func(**kwargs)
            else:
                # Run sync function in thread pool
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, lambda: func(**kwargs))

            duration = (time.perf_counter() - start) * 1000

            if isinstance(result, ActionResult):
                result.duration_ms = duration
                return result
            elif isinstance(result, dict):
                return ActionResult(success=True, output=json.dumps(result), data=result, duration_ms=duration)
            else:
                return ActionResult(success=True, output=str(result), duration_ms=duration)

        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)

    def get_openai_functions(self) -> list[dict]:
        """Get OpenAI-compatible function definitions for all actions."""
        functions = []
        for name, spec in self._specs.items():
            functions.append({
                "type": "function",
                "function": {
                    "name": f"zara_{name}",
                    "description": spec.description,
                    "parameters": spec.parameters,
                }
            })
        return functions


# Global registry instance
registry = ActionRegistry()


def action(
    name: str = None,
    description: str = "",
    parameters: dict = None,
    category: str = "general",
    requires_confirmation: bool = False,
    async_execution: bool = False,
    tags: list[str] = None,
    risk: str = "LOW",
    capability: str = "READ_ONLY",
):
    """
    Decorator to register an action.

    Usage:
        @action(name="terminal", category="system", description="Run shell command")
        def terminal_action(command: str, cwd: str = ".") -> ActionResult:
            ...
    """
    def decorator(func: Callable):
        action_name = name or func.__name__
        if action_name.endswith("_action"):
            action_name = action_name[:-7]  # Remove _action suffix

        registry.register(
            name=action_name,
            func=func,
            description=description,
            parameters=parameters,
            category=category,
            requires_confirmation=requires_confirmation,
            async_execution=async_execution,
            tags=tags,
            risk=risk,
            capability=capability,
        )

        # Wrap the function so direct calls still go through registry gates
        import functools
        import inspect
        sig = inspect.signature(func)

        def _merge_args(args, kwargs):
            # BUGFIX_2026-08-27: os wrappers abaixo so repassavam **kwargs para
            # registry.execute/execute_async, descartando qualquer argumento
            # posicional de chamada direta (ex.: os_brightness_absolute_action(150)).
            # Isso derrubava 209 testes com "missing 1 required positional argument"
            # e era pre-existente, nao relacionado as correcoes da AUDITORIA_2026-08-27.
            bound = sig.bind_partial(*args, **kwargs)
            return bound.arguments

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return registry.execute(action_name, **_merge_args(args, kwargs))

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await registry.execute_async(action_name, **_merge_args(args, kwargs))

        if async_execution or asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def get_registry() -> ActionRegistry:
    """Get the global action registry."""
    return registry


# Context passed to actions
@dataclass
class ActionContext:
    """Context available to all actions."""
    user_id: str = "local"
    session_id: str = ""
    working_dir: str = ""
    current_file: str = ""
    clipboard: str = ""
    screen_text: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "working_dir": self.working_dir,
            "current_file": self.current_file,
            "clipboard": self.clipboard,
            "screen_text": self.screen_text,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


# Helper to create context-aware actions
def with_context(func: Callable) -> Callable:
    """Decorator to inject ActionContext as first argument."""
    sig = inspect.signature(func)
    params = list(sig.parameters.keys())

    if params and params[0] == "context":
        # Already has context
        return func

    def wrapper(*args, **kwargs):
        context = ActionContext()
        return func(context, *args, **kwargs)

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    wrapper.__annotations__ = func.__annotations__
    return wrapper


async def execute_action(action_name: str, **params) -> Any:
    """Execute a registered action by name with parameters.

    Goes through the registry gates. HIGH returns a one-shot challenge;
    MEDIUM requires its existing boolean or explicit policy.
    """
    registry = get_registry()
    if action_name not in registry._actions:
        raise ValueError(f"Action '{action_name}' not found")

    # Route through registry.execute so the risk gate applies.
    if inspect.iscoroutinefunction(registry._actions[action_name]):
        return await registry.execute_async(action_name, **params)
    else:
        # Run sync function in thread pool (registry.execute is sync-safe)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: registry.execute(action_name, **params))


async def execute_confirmed_action(
    action_name: str,
    confirmation_id: str,
    action_fingerprint: str,
    **params,
) -> Any:
    """Consume a one-shot proof and execute the exact fingerprinted action."""
    registry = get_registry()
    if action_name not in registry._actions:
        registry.cancel_confirmation(confirmation_id)
        raise ValueError(f"Action '{action_name}' not found")

    if inspect.iscoroutinefunction(registry._actions[action_name]):
        return await registry.execute_confirmed_async(
            action_name,
            confirmation_id,
            action_fingerprint,
            **params,
        )

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: registry.execute_confirmed(
            action_name,
            confirmation_id,
            action_fingerprint,
            **params,
        ),
    )
