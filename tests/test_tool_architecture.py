"""
Tool Architecture Tests — Unit and integration tests for new tool framework.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from core.tool_definition import ToolDefinition, ToolState
from core.tool_result import ToolResult, ToolVerificationResult
from core.tool_error_model import ErrorCategory, tool_error
from core.tool_risk_model import RiskLevel, Capability, ToolRiskProfile, risk_profile
from core.tool_registry import ToolRegistry, get_tool_registry
from core.tool_router import ToolRouter, ToolRequest
from core.tool_execution_wrapper import ExecutionWrapper, wrap_executor
from core.tool_verifier import (
    ToolVerifier, AlwaysVerified, FileExistsVerifier, FileDeletedVerifier,
    VerificationState
)


class TestToolDefinition:
    """Tests for ToolDefinition."""

    def test_tool_definition_creates_successfully(self):
        """Create tool definition with all fields."""
        tool = ToolDefinition(
            name="test_tool",
            description="Test tool",
            category="test",
            risk_level=RiskLevel.SAFE,
            capability=Capability.READ_ONLY,
        )
        assert tool.name == "test_tool"
        assert tool.risk_level == RiskLevel.SAFE
        assert tool.available is True

    def test_tool_definition_to_dict(self):
        """Convert tool definition to dict."""
        tool = ToolDefinition(
            name="test_tool",
            description="Test tool",
            category="test",
        )
        d = tool.to_dict()
        assert d["name"] == "test_tool"
        assert "description" in d
        assert "risk_level" in d


class TestToolResult:
    """Tests for ToolResult."""

    def test_tool_result_success(self):
        """Create successful result."""
        result = ToolResult(success=True, output="OK", verificado=True)
        assert result.success is True
        assert bool(result) is True

    def test_tool_result_unverified(self):
        """Unverified result is uncertain."""
        result = ToolResult(success=True, verificado=False)
        assert result.incerto() is True
        assert bool(result) is False

    def test_tool_result_from_dict(self):
        """Create result from dict."""
        result = ToolResult(
            success=True,
            data={"key": "value"},
            output="Done",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["data"] == {"key": "value"}


class TestErrorModel:
    """Tests for error model."""

    def test_tool_error_creation(self):
        """Create structured error."""
        error = tool_error(
            category=ErrorCategory.VALIDATION_ERROR,
            message="Invalid input",
            retryable=False,
        )
        assert error.category == ErrorCategory.VALIDATION_ERROR
        assert error.message == "Invalid input"
        assert error.retryable is False


class TestRiskModel:
    """Tests for risk model."""

    def test_risk_profile_creation(self):
        """Create risk profile."""
        profile = risk_profile(
            name="test_action",
            category="test",
            risk_level=RiskLevel.CONFIRM,
            mutates_state=True,
            requires_confirmation=True,
        )
        assert profile.name == "test_action"
        assert profile.risk_level == RiskLevel.CONFIRM
        assert profile.requires_confirmation is True


class TestToolRegistry:
    """Tests for tool registry."""

    def test_registry_singleton(self):
        """Registry is singleton."""
        r1 = get_tool_registry()
        r2 = get_tool_registry()
        assert r1 is r2

    def test_register_tool(self):
        """Register and retrieve tool."""
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="test_register",
            description="Test",
            category="test",
        )
        registry.register(tool)
        retrieved = registry.get("test_register")
        assert retrieved is not None
        assert retrieved.name == "test_register"

    def test_list_by_category(self):
        """List tools by category."""
        registry = ToolRegistry()
        tool1 = ToolDefinition(name="test1", category="cat1", description="T1")
        tool2 = ToolDefinition(name="test2", category="cat1", description="T2")
        registry.register(tool1)
        registry.register(tool2)

        tools = registry.list_tools(category="cat1")
        assert "test1" in tools
        assert "test2" in tools

    def test_filter_by_risk(self):
        """Filter tools by risk level."""
        registry = ToolRegistry()
        tool_safe = ToolDefinition(
            name="safe", category="test", description="Safe",
            risk_level=RiskLevel.SAFE
        )
        tool_high = ToolDefinition(
            name="high", category="test", description="High",
            risk_level=RiskLevel.HIGH_RISK
        )
        registry.register(tool_safe)
        registry.register(tool_high)

        high_risk = registry.filter_by_risk(RiskLevel.HIGH_RISK)
        assert "high" in high_risk
        assert "safe" not in high_risk


class TestToolRouter:
    """Tests for tool router."""

    def test_request_validation(self):
        """Validate tool request."""
        request = ToolRequest(tool_name="test", parameters={"key": "value"})
        assert request.tool_name == "test"
        assert request.parameters == {"key": "value"}

    def test_router_handles_missing_tool(self):
        """Router handles missing tool."""
        router = ToolRouter()
        request = ToolRequest(tool_name="nonexistent", parameters={})
        result = router.route(request)

        assert result.success is False
        assert result.error_code == ErrorCategory.NOT_FOUND

    def test_router_executes_tool(self):
        """Router executes tool successfully."""
        def mock_executor():
            return {"success": True, "data": "test_output"}

        tool = ToolDefinition(
            name="test_exec",
            description="Test",
            category="test",
            executor=mock_executor,
        )
        registry = ToolRegistry()
        registry.register(tool)

        router = ToolRouter(tool_registry=registry)
        request = ToolRequest(tool_name="test_exec", parameters={})
        result = router.route(request)

        assert result.success is True
        assert result.data == "test_output"


class TestExecutionWrapper:
    """Tests for execution wrapper."""

    def test_wrapper_executes_function(self):
        """Wrapper executes function."""
        def test_func():
            return {"success": True, "output": "wrapped"}

        wrapper = ExecutionWrapper(
            executor=test_func,
            name="test_wrap",
            timeout_ms=5000,
        )
        result = wrapper.execute()

        assert result.success is True
        assert result.output == "wrapped"

    def test_wrapper_normalizes_result(self):
        """Wrapper normalizes different result types."""
        # String result
        wrapper = ExecutionWrapper(executor=lambda: "test_output", name="test")
        result = wrapper.execute()
        assert result.output == "test_output"

        # Bool result
        wrapper = ExecutionWrapper(executor=lambda: True, name="test")
        result = wrapper.execute()
        assert result.success is True

    def test_wrapper_handles_exception(self):
        """Wrapper handles executor exception."""
        def failing_executor():
            raise ValueError("Test error")

        wrapper = ExecutionWrapper(
            executor=failing_executor,
            name="failing",
        )
        result = wrapper.execute()

        assert result.success is False
        assert "Test error" in result.error


class TestToolVerifier:
    """Tests for tool verifiers."""

    def test_always_verified(self):
        """AlwaysVerified always returns VERIFIED."""
        verifier = AlwaysVerified()
        result = verifier.verify({}, None)
        assert result.state == VerificationState.VERIFIED
        assert result.confidence == 1.0

    def test_file_exists_verifier(self):
        """FileExistsVerifier checks file existence."""
        # Create temp file
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            verifier = FileExistsVerifier()
            result = verifier.verify({"path": temp_path}, None)
            assert result.state == VerificationState.VERIFIED
        finally:
            Path(temp_path).unlink()

    def test_file_deleted_verifier(self):
        """FileDeletedVerifier checks file deletion."""
        verifier = FileDeletedVerifier()
        result = verifier.verify({"path": "/nonexistent/file.txt"}, None)
        assert result.state == VerificationState.VERIFIED


class TestToolAdapters:
    """Tests for tool adapters."""

    def test_system_adapter_created(self):
        """System adapter has valid structure."""
        from core.tool_adapters import create_system_adapters
        adapters = create_system_adapters()
        assert len(adapters) > 0
        assert all(isinstance(a, ToolDefinition) for a in adapters)

    def test_file_adapter_created(self):
        """File adapter has valid structure."""
        from core.tool_adapters import create_file_adapters
        adapters = create_file_adapters()
        assert len(adapters) > 0
        # Check that dangerous operations are HIGH_RISK
        delete_adapter = [a for a in adapters if "delete" in a.name]
        assert len(delete_adapter) > 0
        assert delete_adapter[0].risk_level == RiskLevel.HIGH_RISK

    def test_all_adapters_have_names(self):
        """All adapters have names."""
        from core.tool_adapters import create_all_adapters
        adapters = create_all_adapters()
        assert all(a.name for a in adapters)
        assert len(adapters) >= 20  # Should have many adapters


class TestIntegration:
    """Integration tests."""

    def test_full_execution_flow(self):
        """Test full execution flow: request → router → result."""
        # Create tool
        def mock_executor(text: str = ""):
            return {"success": True, "output": f"Echoed: {text}"}

        tool = ToolDefinition(
            name="echo_tool",
            description="Echo text",
            category="test",
            executor=mock_executor,
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
            },
        )

        # Register tool
        registry = ToolRegistry()
        registry.register(tool)

        # Create and route request
        router = ToolRouter(tool_registry=registry)
        request = ToolRequest(
            tool_name="echo_tool",
            parameters={"text": "hello"},
        )
        result = router.route(request)

        # Verify result
        assert result.success is True
        assert "hello" in result.output

    def test_permission_gate(self):
        """Test permission gate in router."""
        tool = ToolDefinition(
            name="protected_tool",
            description="Protected",
            category="test",
            executor=lambda: {"success": True},
            capability=Capability.PC_CONTROL,
        )

        registry = ToolRegistry()
        registry.register(tool)

        # Permission checker that denies access
        def deny_permission(tool_name, params):
            return False

        router = ToolRouter(tool_registry=registry)
        router.set_permission_checker(deny_permission)

        request = ToolRequest(tool_name="protected_tool", parameters={})
        result = router.route(request)

        assert result.success is False
        assert result.error_code == ErrorCategory.PERMISSION_DENIED

    def test_verification_in_flow(self):
        """Test verification in execution flow."""
        def create_file_executor(path: str = ""):
            Path(path).touch()
            return {"success": True}

        tool = ToolDefinition(
            name="create_file",
            description="Create file",
            category="files",
            executor=create_file_executor,
            verifier=FileExistsVerifier(),
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        )

        registry = ToolRegistry()
        registry.register(tool)

        router = ToolRouter(tool_registry=registry)

        # Test with temp file
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = str(Path(tmpdir) / "test.txt")

            request = ToolRequest(
                tool_name="create_file",
                parameters={"path": test_file},
            )
            result = router.route(request)

            assert result.success is True
            assert result.verificado is True
            assert result.verification is not None


@pytest.mark.skip(reason="Requires full ActionRegistry setup")
class TestActionRegistryAdaptor:
    """Tests for ActionRegistry adaptor."""

    def test_adapt_from_action_registry(self):
        """Adapt actions from ActionRegistry to ToolRegistry."""
        # This test would require full ActionRegistry initialization
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
