"""
Action Registry — Decorator-based action system for ZARA 3.0.
Actions are the atomic units of automation (terminal, files, web, code, OS, etc.).
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
import threading
import time
import types
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Union, get_args, get_origin, get_type_hints

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
    verificado: bool = True

    @property
    def incerto(self) -> bool:
        """An action was dispatched but its postcondition was not observed."""
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
    capability: str = "READ_ONLY"  # READ_ONLY | PC_CONTROL | FILES_MUTATE | CODE_EXECUTION | SYSTEM_POWER


def _json_schema_type(annotation) -> str:
    """Map a type annotation to a JSON Schema type name.

    Handles string annotations (modules with `from __future__ import
    annotations`), Optional[X], X | None, and builtin generics.
    Unknown annotations fall back to "string" (legacy default).
    """
    if isinstance(annotation, str):
        text = annotation.strip().strip("'\"")
        inner = text
        m = re.match(r"(?i)^(?:optional|union)\[(.+)\]$", text)
        if m:
            inner = m.group(1).split(",")[0]
        elif "|" in text:  # "int | None"
            inner = text.split("|")[0]
        name = inner.strip().lower()
        if name in ("int", "integer"):
            return "integer"
        if name in ("float", "number"):
            return "number"
        if name in ("bool", "boolean"):
            return "boolean"
        if name.startswith("list") or name == "array":
            return "array"
        if name.startswith("dict") or name == "object":
            return "object"
        return "string"
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(annotation) if a is not type(None)]
        return _json_schema_type(args[0]) if args else "string"
    if origin is list:
        return "array"
    if origin is dict:
        return "object"
    return {
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }.get(annotation, "string")


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
        # Capability gate (ZARA-PC-CONTROL-CAPABILITY-GATE-001): while False,
        # no PC_CONTROL action may run, even LOW risk. Set True by Supercérebro.
        # Alex retired the manual Supercerebro key on 2026-09-29. Retain this
        # legacy field for callers, but PC_CONTROL no longer depends on it.
        self.pc_control_allowed = True

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
        # Legacy action modules use this older name for the same guarded
        # PC-control capability. Store only the canonical value so the
        # existing Supercerebro gate still applies.
        if normalized_capability == "LOCAL_PC_CONTROL":
            normalized_capability = "PC_CONTROL"
        valid_capabilities = {
            "READ_ONLY",
            "PC_CONTROL",
            "FILES_MUTATE",
            "CODE_EXECUTION",
            "SYSTEM_POWER",
        }
        if normalized_capability not in valid_capabilities:
            raise ValueError(f"Invalid action capability: {capability!r}")

        if name in self._actions:
            print(f"[ActionRegistry] Warning: Overwriting action '{name}'")

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
        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls", "context"):
                continue

            annotation = hints.get(param_name, param.annotation)
            param_type = _json_schema_type(annotation)

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
    ) -> tuple[ActionResult | None, dict[str, Any]]:
        """Apply capability and risk gates before any action function runs.

        FRENTE B (GIGANTE 3, ZARA-AUTONOMIA-001 + ZARA-FRONTEIRA-DINHEIRO-001):
        retorna (blocked, decision).
          - blocked: ActionResult|None — None = liberado, segue p/ execução.
          - decision: dict {action, autonomous: bool, why: str, grant: str,
            money: str} — alimenta a auditoria.
        Ordem rígida dos portões:
          1. Fronteira de dinheiro — BLOQUEADA sempre, antes de tudo
             (nem confirmação, nem modo autônomo, nem desafio contornam).
          2. Controle do PC: exige autorização do Alex via WhatsApp
             (ordem direta dele, 02/10/2026; fail-closed, sem bypass).
          3. Autonomia ligada (padrão, "sim sempre"): ação direta, sem
             desafio e sem exigir confirm.
          4. Modo legado (ZARA_AUTONOMY=perguntar): desafios como antes.
        """
        decision: dict[str, Any] = {
            "action": name,
            "autonomous": False,
            "why": "",
            "grant": "",
            "money": "",
        }
        if spec is None:
            return (
                ActionResult(success=False, error="ACTION_POLICY_METADATA_MISSING"),
                decision,
            )

        # --- 1. FRONTEIRA DE DINHEIRO (antes de tudo, sem exceção) ---
        try:
            from core.money_boundary import is_money_action

            money_blocked, money_reason = is_money_action(name, params)
        except Exception:
            # A failed policy check must never become permission to move money.
            money_blocked, money_reason = True, "politica-indisponivel"
        if money_blocked:
            decision["money"] = money_reason
            decision["why"] = "bloqueio:dinheiro"
            if isinstance(proof, ConfirmationProof):
                try:
                    self._confirmation_broker.cancel(proof.confirmation_id)
                except Exception:
                    pass
            return (
                ActionResult(
                    success=False,
                    error=(
                        f"Ação '{name}' BLOQUEADA pela fronteira de dinheiro "
                        f"({money_reason}). A ZARA nunca movimenta dinheiro."
                    ),
                    duration_ms=0.0,
                    verificado=False,
                ),
                decision,
            )

        # --- 2. CONTROLE DO PC (ordem direta do Alex, 02/10/2026) ---
        # PC_CONTROL exige autorização do Alex via WhatsApp, com prazo curto.
        # Arquivo ausente/expirado/malformado ou erro na checagem = NEGAR
        # (fail-closed). Sem bypass: nem chave manual, nem autonomia, nem
        # confirmação contornam este portão.
        if spec.capability == "PC_CONTROL":
            grant_ok = False
            grant_reason = ""
            try:
                from core import supercerebro_grant as _sg

                grant_ok, grant_reason, _info = _sg.check_whatsapp_grant()
            except Exception:
                grant_ok, grant_reason = False, "grant-check-error"
            decision["grant"] = grant_reason or ""
            if not grant_ok:
                if isinstance(proof, ConfirmationProof):
                    try:
                        self._confirmation_broker.cancel(proof.confirmation_id)
                    except Exception:
                        pass
                decision["why"] = "trava:whatsapp-grant"
                return (
                    ActionResult(
                        success=False,
                        error=(
                            f"Ação '{name}' BLOQUEADA pela trava do Supercérebro: "
                            "controle do PC exige autorização do Alex via WhatsApp "
                            f"({grant_reason or 'sem grant válido'})."
                        ),
                        duration_ms=0.0,
                        verificado=False,
                    ),
                    decision,
                )

        # --- 3. AUTONOMIA (diretriz do Alex: "sim sempre") ---
        # Ação direta: sem desafio one-shot, sem exigir confirm. A fronteira
        # de dinheiro já foi aplicada acima.
        try:
            from core.autonomy_policy import autonomy_enabled

            _auto = autonomy_enabled()
        except Exception:
            _auto = False
        if _auto:
            if isinstance(proof, ConfirmationProof):
                try:
                    self._confirmation_broker.cancel(proof.confirmation_id)
                except Exception:
                    pass
            params.pop("confirm", None)
            decision["autonomous"] = True
            decision["why"] = "autonomia:acao-direta"
            return None, decision

        # --- 4. MODO LEGADO (ZARA_AUTONOMY=perguntar): desafios como antes ---
        # Legacy confirmation remains valid only for MEDIUM actions. HIGH
        # always requires a one-shot proof from the separate confirmation IPC.
        medium_confirmed = params.pop("confirm", False) is True
        if spec.risk == "HIGH":
            if proof is not None and not isinstance(proof, ConfirmationProof):
                return (
                    ActionResult(
                        success=False,
                        error="CONFIRMATION_INVALID",
                        data={"status": "CONFIRMATION_INVALID"},
                    ),
                    decision,
                )

            metadata = self._confirmation_metadata(spec)
            if proof is None:
                summary = build_confirmation_summary(name, params)
                if summary is None:
                    return (
                        ActionResult(
                            success=False,
                            error="CONFIRMATION_POLICY_MISSING",
                            data={"status": "CONFIRMATION_POLICY_MISSING"},
                        ),
                        decision,
                    )
                try:
                    challenge = self._confirmation_broker.issue(
                        action=name,
                        metadata=metadata,
                        params=params,
                        summary=summary,
                    )
                except (ConfirmationCapacityError, ConfirmationSerializationError, RuntimeError):
                    return (
                        ActionResult(
                            success=False,
                            error="CONFIRMATION_UNAVAILABLE",
                            data={"status": "CONFIRMATION_UNAVAILABLE"},
                        ),
                        decision,
                    )
                return (
                    ActionResult(
                        success=False,
                        error="CONFIRMATION_REQUIRED",
                        data={
                            "status": "CONFIRMATION_REQUIRED",
                            "confirmation": challenge.to_dict(),
                        },
                    ),
                    decision,
                )

            allowed, status = self._confirmation_broker.consume(
                proof,
                action=name,
                metadata=metadata,
                params=params,
            )
            if not allowed:
                return (
                    ActionResult(
                        success=False,
                        error=status,
                        data={"status": status},
                    ),
                    decision,
                )
            return None, decision

        if isinstance(proof, ConfirmationProof):
            self._confirmation_broker.cancel(proof.confirmation_id)
            return (
                ActionResult(
                    success=False,
                    error="CONFIRMATION_NOT_APPLICABLE",
                    data={"status": "CONFIRMATION_NOT_APPLICABLE"},
                ),
                decision,
            )

        if spec.risk == "MEDIUM" and not self.medium_risk_open and not medium_confirmed:
            return (
                ActionResult(
                    success=False,
                    error=(
                        f"Action '{name}' é MEDIUM risk e exige confirmação "
                        "(confirm=true) ou política MEDIUM explícita."
                    ),
                    duration_ms=0.0,
                ),
                decision,
            )
        return None, decision

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
        blocked, decision = self._check_action_gates(name, spec, kwargs, proof)
        if blocked is not None:
            self._audit_block(name, spec, blocked, decision)
            return blocked

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
                self._audit_with_decision(name, spec, result, decision)
                return result
            elif isinstance(result, dict):
                out = ActionResult(success=True, output=json.dumps(result), data=result, duration_ms=duration)
                self._audit_with_decision(name, spec, out, decision)
                return out
            else:
                out = ActionResult(success=True, output=str(result), duration_ms=duration)
                self._audit_with_decision(name, spec, out, decision)
                return out

        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=duration)

    def _audit_action(
        self,
        name: str,
        spec: ActionSpec | None,
        result: ActionResult,
        decision: dict[str, Any] | None = None,
    ) -> None:
        """Audit executions without raw parameters (no secrets).

        FRENTE B3: audita TODOS os riscos (LOW inclusive — o teste
        anti-vazamento exige linha de auditoria mesmo p/ LOW), com
        autonomous (0/1) e why (motivo curto). Bloqueios de dinheiro
        e da trava vão por _audit_block.
        """
        try:
            from core.audit_log import audit_log

            decision = decision or {}
            audit_log().record(
                action=name,
                risk=spec.risk if spec else "LOW",
                outcome="success" if result.success else "error",
                error=None if result.success else str(result.error)[:200],
                autonomous=bool(decision.get("autonomous")),
                why=str(decision.get("why") or ""),
            )
        except Exception:
            pass

    def _audit_block(
        self,
        name: str,
        spec: ActionSpec | None,
        blocked: ActionResult,
        decision: dict[str, Any] | None = None,
    ) -> None:
        """Audit a gate block. Money blocks are ALWAYS audited (any risk);
        other blocks follow the MEDIUM/HIGH rule. Never logs raw params."""
        try:
            from core.audit_log import audit_log

            decision = decision or {}
            why = str(decision.get("why") or "")
            risk = spec.risk if spec else "LOW"
            if why == "bloqueio:dinheiro" or risk in ("MEDIUM", "HIGH"):
                audit_log().record(
                    action=name,
                    risk=risk,
                    outcome="blocked",
                    error=str(blocked.error)[:200] if blocked else "",
                    autonomous=False,
                    why=why,
                )
        except Exception:
            pass

    def _audit_with_decision(
        self,
        name: str,
        spec: ActionSpec | None,
        result: ActionResult,
        decision: dict[str, Any] | None,
    ) -> None:
        """Chama _audit_action tolerando o monkeypatch de 3 args dos testes.

        Os testes antigos fazem `registry._audit_action = lambda _n,_s,_r: None`.
        Tenta a assinatura nova (4 args); se o mock nao aceitar, cai para 3.
        """
        try:
            self._audit_action(name, spec, result, decision)  # type: ignore[call-arg]
        except TypeError:
            try:
                self._audit_action(name, spec, result)  # type: ignore[call-arg]
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
        blocked, decision = self._check_action_gates(name, spec, kwargs, proof)
        if blocked is not None:
            self._audit_block(name, spec, blocked, decision)
            return blocked

        # Teto global de tempo por categoria de risco (M2-corujão 2026-10-02):
        # uma action travada não pode segurar a corrotina para sempre.
        risk = (spec.risk if spec else "LOW").upper()
        timeout = {"LOW": 30, "MEDIUM": 120, "HIGH": 300}.get(risk, 30)

        async def _run() -> Any:
            if inspect.iscoroutinefunction(func):
                return await func(**kwargs)
            # Run sync function in thread pool
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: func(**kwargs))

        try:
            result = await asyncio.wait_for(_run(), timeout=timeout)

            duration = (time.perf_counter() - start) * 1000

            if isinstance(result, ActionResult):
                result.duration_ms = duration
                return result
            elif isinstance(result, dict):
                return ActionResult(success=True, output=json.dumps(result), data=result, duration_ms=duration)
            else:
                return ActionResult(success=True, output=str(result), duration_ms=duration)

        except asyncio.TimeoutError:
            duration = (time.perf_counter() - start) * 1000
            return ActionResult(
                success=False,
                error=f"TIMEOUT: action '{name}' excedeu o limite de {timeout}s (risco {risk})",
                data={"timeout_s": timeout, "risk": risk, "action": name},
                duration_ms=duration,
            )
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
        return func
    return decorator


def get_registry() -> ActionRegistry:
    """Get the global action registry."""
    return registry


ADVANCED_ACTION_MODULES = (
    "core.actions.system_advanced",
    "core.actions.macro_actions",
    "core.actions.vision_actions",
)


def load_advanced_action_exports() -> tuple[str, ...]:
    """Import advanced modules explicitly; decorators populate this registry."""
    import importlib

    loaded = []
    for module_name in ADVANCED_ACTION_MODULES:
        importlib.import_module(module_name)
        loaded.append(module_name)
    return tuple(loaded)


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
