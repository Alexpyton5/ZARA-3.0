"""Tests for TelegramApprovalAdapter."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from core.telegram_approval_adapter import TelegramApprovalAdapter


@pytest.fixture
def mock_ponte():
    """Return a mock ponte with an avisar coroutine."""
    ponte = Mock()
    ponte.avisar = AsyncMock(return_value=True)
    return ponte


@pytest.fixture
def adapter(mock_ponte):
    """Return a TelegramApprovalAdapter instance."""
    return TelegramApprovalAdapter(mock_ponte)


def test_init(adapter, mock_ponte):
    """Adapter stores the ponte."""
    assert adapter._ponte is mock_ponte


@pytest.mark.asyncio
async def test_send_request_success(adapter, mock_ponte):
    """send_request returns True when ponte.avisar succeeds."""
    mock_ponte.avisar.return_value = True
    result = await adapter.send_request("id1", "msg")
    assert result is True
    mock_ponte.avisar.assert_awaited_once_with("msg")


@pytest.mark.asyncio
async def test_send_request_false(adapter, mock_ponte):
    """send_request returns False when ponte.avisar returns False."""
    mock_ponte.avisar.return_value = False
    result = await adapter.send_request("id1", "msg")
    assert result is False
    mock_ponte.avisar.assert_awaited_once_with("msg")


@pytest.mark.asyncio
async def test_send_request_exception(adapter, mock_ponte):
    """send_request returns False when ponte.avisar raises."""
    mock_ponte.avisar.side_effect = Exception("boom")
    result = await adapter.send_request("id1", "msg")
    assert result is False
    mock_ponte.avisar.assert_awaited_once_with("msg")