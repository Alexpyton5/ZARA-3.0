import asyncio
import time
from unittest.mock import patch, AsyncMock
import pytest
from core.ipc_handlers import IPCHandler, IPCMessage
from core.action_registry import ActionResult

def create_handler():
    """Create and configure an IPCHandler for testing voice commands."""
    handler = IPCHandler(AsyncMock())
    # Basic initialization to avoid AttributeError
    handler._initialized = True
    handler._tts_initialized = False
    handler.gemini_live_voice = None
    handler.voice_mode = "off"
    handler.voice_pipeline = None
    handler.tts_manager = None
    handler.memory = None
    handler.orchestrator = None
    handler.model_router = None
    handler.hermes = None
    handler.conversation_history = None
    handler.reminder_engine = None
    handler.user_memory = None
    handler.project_memory = None
    handler.lab = None
    handler._event_loop = asyncio.get_event_loop()
    # Allow PC control (Supercerebro active) so that PC intents are not blocked
    handler.supercerebro_active = True
    # Set a fake window handle for window actions
    handler._last_window_hwnd = 12345
    # Set a fake volume level for volume actions (if needed)
    handler._last_volume_level = 50
    # Set operational context to make window context available
    handler._operational_context_updated_at = time.monotonic()
    handler._operational_context_turns = 3
    handler._operational_context = {
        "action_type": "window",
        "canonical_target": "some_window",
        "pid": 1234,
        "hwnd": 12345,
        "verified_value": "some_value",
        "timestamp": handler._operational_context_updated_at,
        "created_by_zara": False,
    }
    return handler

@pytest.mark.asyncio
async def test_browser_read_page_e2e():
    """Test browser_read_page via voice command with latency measurement."""
    handler = create_handler()
    
    # Mock the action function
    with patch('core.action_registry.execute_action') as mock_execute:
        mock_execute.return_value = ActionResult(success=True, output="Resumo da página: exemplo de conteúdo.")
        
        # Measure latency
        start_time = time.perf_counter()
        await handler._process_voice_message("Zara, resuma esta página")
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000
        
        # Verify action was called with correct action name
        mock_execute.assert_called_once()
        args, kwargs = mock_execute.call_args
        assert args[0] == "browser_read_page"
        
        # Verify that a message event was sent with the expected content
        message_sent = False
        for call in handler.send.call_args_list:
            msg = call[0][0]
            if hasattr(msg, 'type') and msg.type == 'message' and hasattr(msg, 'message'):
                if isinstance(msg.message, dict) and 'Resumo da página' in msg.message.get('content', ''):
                    message_sent = True
                    break
        assert message_sent, "Expected a message event with content containing 'Resumo da página'"
        
        # Store latency for reporting
        test_browser_read_page_e2e.latency_ms = latency_ms

@pytest.mark.asyncio
async def test_window_move_e2e():
    """Test window_move via voice command with latency measurement."""
    handler = create_handler()
    handler._last_window_hwnd = 12345  # fake hwnd
    
    with patch('core.action_registry.execute_action') as mock_execute:
        mock_execute.return_value = ActionResult(success=True, output="Janela movida para a direita.")
        
        # Measure latency
        start_time = time.perf_counter()
        await handler._process_voice_message("Zara, mova a janela para o lado direito")
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000
        
        mock_execute.assert_called_once()
        args, kwargs = mock_execute.call_args
        assert args[0] == "window_move"
        assert kwargs["side"] == "right"  # The detector returns "right" for "direito"
        
        # Verify that a message event was sent with the expected content
        message_sent = False
        for call in handler.send.call_args_list:
            msg = call[0][0]
            if hasattr(msg, 'type') and msg.type == 'message' and hasattr(msg, 'message'):
                if isinstance(msg.message, dict) and 'Janela movida' in msg.message.get('content', ''):
                    message_sent = True
                    break
        assert message_sent, "Expected a message event with content containing 'Janela movida'"
        
        # Store latency for reporting
        test_window_move_e2e.latency_ms = latency_ms

@pytest.mark.asyncio
async def test_window_resize_larger_e2e():
    """Test window_resize_larger via voice command with latency measurement."""
    handler = create_handler()
    handler._last_window_hwnd = 12345
    
    with patch('core.action_registry.execute_action') as mock_execute:
        mock_execute.return_value = ActionResult(success=True, output="Janela redimensionada para maior.")
        
        # Measure latency
        start_time = time.perf_counter()
        await handler._process_voice_message("Zara, faça a janela maior")
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000
        
        mock_execute.assert_called_once()
        args, kwargs = mock_execute.call_args
        assert args[0] == "window_resize_larger"
        
        # Verify that a message event was sent with the expected content
        message_sent = False
        for call in handler.send.call_args_list:
            msg = call[0][0]
            if hasattr(msg, 'type') and msg.type == 'message' and hasattr(msg, 'message'):
                if isinstance(msg.message, dict) and 'Janela redimensionada' in msg.message.get('content', ''):
                    message_sent = True
                    break
        assert message_sent, "Expected a message event with content containing 'Janela redimensionada'"
        
        # Store latency for reporting
        test_window_resize_larger_e2e.latency_ms = latency_ms

@pytest.mark.asyncio
async def test_window_close_e2e():
    """Test window_close via voice command with latency measurement."""
    handler = create_handler()
    handler._last_window_hwnd = 12345
    
    with patch('core.action_registry.execute_action') as mock_execute:
        mock_execute.return_value = ActionResult(success=True, output="Janela fechada e verificada.")
        
        # Measure latency
        start_time = time.perf_counter()
        await handler._process_voice_message("Zara, feche a janela")
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000
        
        mock_execute.assert_called_once()
        args, kwargs = mock_execute.call_args
        assert args[0] == "window_close"
        
        # Verify that a message event was sent with the expected content
        message_sent = False
        for call in handler.send.call_args_list:
            msg = call[0][0]
            if hasattr(msg, 'type') and msg.type == 'message' and hasattr(msg, 'message'):
                if isinstance(msg.message, dict) and 'Janela fechada' in msg.message.get('content', ''):
                    message_sent = True
                    break
        assert message_sent, "Expected a message event with content containing 'Janela fechada'"
        
        # Store latency for reporting
        test_window_close_e2e.latency_ms = latency_ms

@pytest.mark.asyncio
async def test_os_clipboard_read_e2e():
    """Test os_clipboard_read via voice command with latency measurement."""
    handler = create_handler()
    
    with patch('core.action_registry.execute_action') as mock_execute:
        mock_execute.return_value = ActionResult(success=True, output="A área de transferência contém: texto de exemplo.")
        
        # Measure latency
        start_time = time.perf_counter()
        await handler._process_voice_message("Zara, o que está na área de transferência?")
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000
        
        mock_execute.assert_called_once()
        args, kwargs = mock_execute.call_args
        assert args[0] == "os_clipboard_read"
        
        # Verify that a message event was sent with the expected content
        message_sent = False
        for call in handler.send.call_args_list:
            msg = call[0][0]
            if hasattr(msg, 'type') and msg.type == 'message' and hasattr(msg, 'message'):
                if isinstance(msg.message, dict):
                    content = msg.message.get('content', '').lower()
                    if 'área de transferência' in content:
                        message_sent = True
                        break
        assert message_sent, "Expected a message event with content containing 'área de transferência'"
        
        # Store latency for reporting
        test_os_clipboard_read_e2e.latency_ms = latency_ms

@pytest.mark.asyncio
async def test_aprendizado_resumo_e2e():
    """Test aprendizado_resumo via voice command with latency measurement."""
    handler = create_handler()
    # We need to mock the aprendizado property to avoid AttributeError
    class MockAprendizado:
        def registrar_acao(self, pedido, acao, sucesso, resultado, origem):
            pass
        def observar_reacao(self, fala):
            return None
    handler._aprendizado = MockAprendizado()
    
    with patch('core.action_registry.execute_action') as mock_execute:
        mock_execute.return_value = ActionResult(success=True, output="Hoje você aprendeu sobre controle de janelas e área de transferência.")
        
        # Measure latency
        start_time = time.perf_counter()
        await handler._process_voice_message("Zara, o que você aprendeu?")
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000
        
        mock_execute.assert_called_once()
        args, kwargs = mock_execute.call_args
        assert args[0] == "aprendizado_resumo"
        
        # Verify that a message event was sent with the expected content
        message_sent = False
        for call in handler.send.call_args_list:
            msg = call[0][0]
            if hasattr(msg, 'type') and msg.type == 'message' and hasattr(msg, 'message'):
                if isinstance(msg.message, dict):
                    content = msg.message.get('content', '').lower()
                    if 'aprendeu' in content:
                        message_sent = True
                        break
        assert message_sent, "Expected a message event with content containing 'aprendeu'"
        
        # Store latency for reporting
        test_aprendizado_resumo_e2e.latency_ms = latency_ms