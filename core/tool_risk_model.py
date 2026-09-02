"""
Tool Risk Model — Unified risk classification and policies.

Maps tools to risk levels and defines execution policies without
replacing existing confirmation system.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["RiskLevel", "Capability", "ToolRiskProfile", "risk_profile"]


class RiskLevel:
    """Risk classification levels."""
    SAFE = "SAFE"  # No confirmation needed, can execute immediately
    CONFIRM = "CONFIRM"  # Confirmation recommended/required
    HIGH_RISK = "HIGH_RISK"  # High impact, always confirmation required
    BLOCKED = "BLOCKED"  # Not available, cannot execute


class Capability:
    """Tool capability levels."""
    READ_ONLY = "READ_ONLY"  # Read information only
    LOCAL_PC_CONTROL = "LOCAL_PC_CONTROL"  # Local deterministic control (volume, brightness, etc.)
    PC_CONTROL = "PC_CONTROL"  # Remote/centralized PC control (apps, files, power)
    REMOTE_PC_CONTROL = "REMOTE_PC_CONTROL"  # Remote execution (future)
    AGENTIC_PC_CONTROL = "AGENTIC_PC_CONTROL"  # Autonomous/compound actions (macro, scheduler)
    FILES_MUTATE = "FILES_MUTATE"  # File system mutation
    CODE_EXECUTION = "CODE_EXECUTION"  # Execute arbitrary code
    SYSTEM_POWER = "SYSTEM_POWER"  # System power management


@dataclass
class ToolRiskProfile:
    """Risk profile for a tool."""

    name: str
    category: str
    risk_level: str  # SAFE | CONFIRM | HIGH_RISK | BLOCKED
    capability: str
    requires_confirmation: bool
    requires_superbrain: bool
    rationale: str = ""

    # Policy guidance
    execution_policy: str = ""  # e.g., "EXECUTE_IMMEDIATE", "ASK_FOR_CONFIRMATION", "ESCALATE_TO_SUPERBRAIN"
    verification_required: bool = False
    timeout_ms: int = 30000
    max_retries: int = 1

    # Risk factors (checklist for classification)
    mutates_state: bool = False
    accesses_sensitive_data: bool = False
    requires_confirmation_gate: bool = False
    depends_on_superbrain: bool = False
    may_block_ui: bool = False
    may_hang: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "category": self.category,
            "risk_level": self.risk_level,
            "capability": self.capability,
            "requires_confirmation": self.requires_confirmation,
            "requires_superbrain": self.requires_superbrain,
            "execution_policy": self.execution_policy,
            "verification_required": self.verification_required,
        }


def risk_profile(
    name: str,
    category: str,
    risk_level: str = RiskLevel.SAFE,
    capability: str = Capability.READ_ONLY,
    requires_confirmation: bool = False,
    requires_superbrain: bool = False,
    rationale: str = "",
    mutates_state: bool = False,
    accesses_sensitive_data: bool = False,
    may_block_ui: bool = False,
    may_hang: bool = False,
) -> ToolRiskProfile:
    """Create a risk profile for a tool."""

    # Determine execution policy
    if risk_level == RiskLevel.BLOCKED:
        execution_policy = "BLOCKED"
    elif risk_level == RiskLevel.HIGH_RISK:
        execution_policy = "ESCALATE_TO_SUPERBRAIN_CONFIRMATION"
    elif risk_level == RiskLevel.CONFIRM or requires_confirmation:
        execution_policy = "ASK_FOR_CONFIRMATION"
    else:
        execution_policy = "EXECUTE_IMMEDIATE"

    # Determine if verification is required
    verification_required = mutates_state or accesses_sensitive_data

    return ToolRiskProfile(
        name=name,
        category=category,
        risk_level=risk_level,
        capability=capability,
        requires_confirmation=requires_confirmation,
        requires_superbrain=requires_superbrain,
        rationale=rationale,
        execution_policy=execution_policy,
        verification_required=verification_required,
        mutates_state=mutates_state,
        accesses_sensitive_data=accesses_sensitive_data,
        may_block_ui=may_block_ui,
        may_hang=may_hang,
    )


# Pre-computed risk profiles for all action categories
RISK_PROFILES: dict[str, ToolRiskProfile] = {}


def register_risk_profile(profile: ToolRiskProfile):
    """Register a risk profile."""
    RISK_PROFILES[profile.name] = profile


def get_risk_profile(name: str) -> ToolRiskProfile | None:
    """Get risk profile by tool name."""
    return RISK_PROFILES.get(name)


# Initialize default risk profiles for common action categories

# READ-ONLY: Information queries, lists, searches
for action in [
    "system_info", "system_time", "system_metrics", "system_processes",
    "file_exists", "file_list", "file_read", "file_size",
    "clipboard_read", "clipboard_history",
    "app_list", "app_status", "task_list",
    "browser_screenshot", "browser_read_page",
    "vision_screenshot", "vision_ocr",
]:
    register_risk_profile(risk_profile(
        name=action,
        category="info",
        risk_level=RiskLevel.SAFE,
        capability=Capability.READ_ONLY,
        rationale="Read-only information access",
    ))

# LOCAL_PC_CONTROL: Deterministic local controls
for action in [
    "os_volume", "os_brightness", "os_night_light",
    "audio_mute", "audio_unmute", "audio_status",
    "os_wifi", "os_bluetooth", "os_vpn",
    "window_minimize", "window_maximize", "window_close", "window_focus",
    "input_type_text", "input_hotkey",
]:
    register_risk_profile(risk_profile(
        name=action,
        category="control",
        risk_level=RiskLevel.SAFE,
        capability=Capability.LOCAL_PC_CONTROL,
        rationale="Deterministic local PC control",
        mutates_state=True,
    ))

# PC_CONTROL: Remote/centralized controls
for action in [
    "app_open", "app_close", "app_launch",
    "browser_open", "browser_navigate", "browser_search",
    "youtube_play", "youtube_pause", "youtube_next",
    "file_copy", "file_move", "file_create",
    "os_clipboard_write",
]:
    register_risk_profile(risk_profile(
        name=action,
        category="control",
        risk_level=RiskLevel.CONFIRM,
        capability=Capability.PC_CONTROL,
        rationale="Remote PC control, requires Supercérebro gate",
        requires_superbrain=True,
        mutates_state=True,
    ))

# HIGH_RISK: Destructive or dangerous operations
for action in [
    "file_delete", "file_delete_permanent",
    "os_power_shutdown", "os_power_restart", "os_power_sleep",
    "terminal_execute", "code_execute",
    "registry_write", "registry_delete",
    "service_stop", "service_restart",
]:
    register_risk_profile(risk_profile(
        name=action,
        category="dangerous",
        risk_level=RiskLevel.HIGH_RISK,
        capability=Capability.PC_CONTROL,
        requires_confirmation=True,
        requires_superbrain=True,
        rationale="Destructive operation, always requires confirmation",
        mutates_state=True,
        accesses_sensitive_data=True,
    ))
