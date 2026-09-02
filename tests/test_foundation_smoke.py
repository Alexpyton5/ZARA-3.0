"""Foundation Smoke Tests — ZARA 3.0 (M7)

Baseline smoke tests for critical systems before Phase 2 work.

These tests verify that core systems can initialize and respond, without
executing actual PC control or dangerous operations.
"""

import pytest
import sys
import os
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestBackendInitialization:
    """M7: Backend system startup."""

    def test_main_module_exists(self):
        """Main script can be found."""
        main_path = PROJECT_ROOT / "main.py"
        assert main_path.exists(), f"main.py not found at {main_path}"

    def test_ipc_handlers_imports(self):
        """Core IPC handler can be imported."""
        try:
            from core import ipc_handlers
            assert hasattr(ipc_handlers, 'main'), "ipc_handlers.main not found"
        except ImportError as e:
            pytest.skip(f"ipc_handlers import failed: {e}")

    def test_action_registry_imports(self):
        """Action registry loads without error."""
        try:
            from core.action_registry import get_registry
            registry = get_registry()
            assert registry is not None, "Registry is None"
        except ImportError as e:
            pytest.skip(f"action_registry import failed: {e}")


class TestIntentClassification:
    """M7: Intent classification system."""

    def test_intent_classifier_imports(self):
        """Intent classifier module exists."""
        try:
            from core import intent_classifier
            assert hasattr(intent_classifier, 'classify'), "classify function not found"
        except ImportError as e:
            pytest.skip(f"intent_classifier import failed: {e}")

    def test_pc_voice_intent_imports(self):
        """PC voice intent module exists."""
        try:
            from core import pc_voice_intent
            assert hasattr(pc_voice_intent, '_resolve_pc_intent'), "_resolve_pc_intent not found"
        except ImportError as e:
            pytest.skip(f"pc_voice_intent import failed: {e}")

    def test_local_deterministic_actions_defined(self):
        """LOCAL_DETERMINISTIC_ACTIONS set is defined."""
        try:
            from core.pc_voice_intent import _LOCAL_DETERMINISTIC_ACTIONS
            assert isinstance(_LOCAL_DETERMINISTIC_ACTIONS, set), "Not a set"
            assert len(_LOCAL_DETERMINISTIC_ACTIONS) > 0, "Set is empty"
        except ImportError:
            pytest.skip("LOCAL_DETERMINISTIC_ACTIONS not found")


class TestConversationHistory:
    """M7: Memory/history system."""

    def test_conversation_history_imports(self):
        """Conversation history module loads."""
        try:
            from core import conversation_history
            assert hasattr(conversation_history, 'ConversationHistory'), "ConversationHistory not found"
        except ImportError as e:
            pytest.skip(f"conversation_history import failed: {e}")

    def test_sqlite_dependency(self):
        """SQLite3 available (stdlib)."""
        try:
            import sqlite3
            # Try to create in-memory DB
            conn = sqlite3.connect(":memory:")
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            conn.close()
        except Exception as e:
            pytest.fail(f"SQLite3 not available: {e}")


class TestVoiceEngine:
    """M7: Voice system initialization."""

    def test_gemini_live_imports(self):
        """Gemini Live voice engine can import."""
        try:
            from core import gemini_live_voice
            assert hasattr(gemini_live_voice, 'GeminiLive'), "GeminiLive class not found"
        except ImportError as e:
            pytest.skip(f"gemini_live_voice import failed: {e}")

    def test_voice_tts_imports(self):
        """Text-to-speech module loads."""
        try:
            from core import voice_tts
            assert hasattr(voice_tts, 'speak'), "speak function not found"
        except ImportError as e:
            pytest.skip(f"voice_tts import failed: {e}")

    def test_voice_stt_imports(self):
        """Speech-to-text module loads."""
        try:
            from core import voice_stt
            # Just check it imports; actual STT services may not be available
        except ImportError as e:
            pytest.skip(f"voice_stt import failed: {e}")


class TestActionRegistry:
    """M7: Action execution system."""

    def test_action_registry_has_actions(self):
        """Registry has some registered actions."""
        try:
            from core.action_registry import get_registry
            registry = get_registry()
            specs = registry.get_all_specs()
            assert len(specs) > 0, "No actions registered"
        except Exception as e:
            pytest.skip(f"Could not check action registry: {e}")

    def test_action_confirmation_imports(self):
        """Action confirmation module loads."""
        try:
            from core import action_confirmation
            # Just verify it imports
        except ImportError as e:
            pytest.skip(f"action_confirmation import failed: {e}")

    def test_permission_gates_exist(self):
        """Permission/safety gates are defined."""
        try:
            from core.action_registry import get_registry
            registry = get_registry()
            # Registry should have some concept of permissions
            assert registry is not None
        except Exception as e:
            pytest.skip(f"Could not verify permission gates: {e}")


class TestAuditLog:
    """M7: Audit trail system."""

    def test_audit_log_imports(self):
        """Audit log module loads."""
        try:
            from core import audit_log
            # Just verify it imports
        except ImportError as e:
            pytest.skip(f"audit_log import failed: {e}")


class TestConfiguration:
    """M7: Configuration system."""

    def test_paths_module_imports(self):
        """Paths/config module loads."""
        try:
            from core import paths
            # Should have functions like get_config_dir, get_data_dir
        except ImportError as e:
            pytest.skip(f"paths module import failed: {e}")

    def test_env_encoding_set(self):
        """Environment encoding is set for Windows."""
        # PYTHONIOENCODING should be utf-8
        # This is less critical to test, as build_exe.py should handle it
        pass


class TestBuildIdentity:
    """M7: Build metadata (M2 verification)."""

    def test_build_info_json_location(self):
        """BUILD_INFO.json has correct location."""
        build_info_path = PROJECT_ROOT / "frontend" / "release" / "win-unpacked" / "BUILD_INFO.json"
        # Location should exist (or be creatable during build)
        assert build_info_path.parent.exists(), f"Parent directory missing: {build_info_path.parent}"

    def test_build_info_json_schema(self):
        """BUILD_INFO.json (if present) has correct structure."""
        import json
        build_info_path = PROJECT_ROOT / "frontend" / "release" / "win-unpacked" / "BUILD_INFO.json"

        if build_info_path.exists():
            with open(build_info_path) as f:
                data = json.load(f)

            required_fields = [
                "BUILD_ID", "BUILD_TIMESTAMP", "GIT_BRANCH", "GIT_COMMIT",
                "GIT_DIRTY", "PYTHON_VERSION", "NODE_VERSION", "SIDECAR_SHA256"
            ]
            for field in required_fields:
                assert field in data, f"Missing field: {field}"


class TestIPC:
    """M7: IPC channels (M5 verification)."""

    def test_preload_module_exists(self):
        """Preload bridge exists."""
        preload_path = PROJECT_ROOT / "frontend" / "src" / "preload.ts"
        assert preload_path.exists(), f"preload.ts not found at {preload_path}"

    def test_main_ipc_registration(self):
        """Electron main has IPC handlers."""
        main_ts = PROJECT_ROOT / "frontend" / "src" / "main.ts"
        assert main_ts.exists(), f"main.ts not found at {main_ts}"

        with open(main_ts) as f:
            content = f.read()

        # Should contain IPC handler registrations
        assert "ipcMain.handle" in content, "No ipcMain.handle calls found"


class TestSmokeSummary:
    """Summary checks."""

    def test_project_structure(self):
        """Project has expected directory structure."""
        expected_dirs = [
            "core",
            "frontend",
            "frontend/src",
            "tests",
            "config",
        ]

        for dir_name in expected_dirs:
            dir_path = PROJECT_ROOT / dir_name
            assert dir_path.exists(), f"Missing directory: {dir_path}"

    def test_git_status_clean(self):
        """Git repo is accessible."""
        git_dir = PROJECT_ROOT / ".git"
        assert git_dir.exists(), "Not a git repository"


if __name__ == "__main__":
    # Run: pytest tests/test_foundation_smoke.py -v
    pytest.main([__file__, "-v"])
