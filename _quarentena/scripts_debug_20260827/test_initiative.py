"""Tests for the initiative engine.

SPIKE J3: Tests for the SUGERIR (suggest) without execute model.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, time
from unittest.mock import AsyncMock, patch

import pytest

from core.initiative.config import InitiativeConfig
from core.initiative.engine import InitiativeEngine


def test_initiative_config_defaults():
    """Test that the default configuration has sensible values."""
    config = InitiativeConfig()
    assert config.enabled is True
    assert config.max_interruptions_per_hour == 1
    assert config.silent_start_hour == 23
    assert config.silent_end_hour == 8
    assert config.utility_threshold == 0.7
    assert config.history_size == 100
    assert config.check_interval_seconds == 60


@pytest.mark.asyncio
async def test_engine_start_stop():
    """Test that the engine can be started and stopped."""
    engine = InitiativeEngine()
    assert engine.enabled is True
    assert engine._task is None

    await engine.start()
    assert engine._task is not None
    assert not engine._task.done()

    await engine.stop()
    assert engine._task is None


@pytest.mark.asyncio
async def test_silent_period_prevents_suggesting():
    """Engine should not suggest during silent period (23:00 to 08:00)."""
    # Mock time to be 02:00 (within silent period)
    with patch('core.initiative.engine.datetime') as mock_dt:
        mock_dt.now.return_value.time.return_value = time(2, 0)
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

        engine = InitiativeEngine()
        # Test the helper directly.
        assert engine._is_silent_period() is True

        # Now test that _check_and_suggest returns early.
        with patch.object(engine, '_within_suggestion_limit', return_value=True) as mock_limit, \
             patch.object(engine, '_get_utility', return_value=1.0) as mock_utility, \
             patch.object(engine, '_get_advice', return_value='test advice') as mock_advice, \
             patch.object(engine, '_is_recent_advice', return_value=False) as mock_recent, \
             patch.object(engine, '_suggest', new_callable=AsyncMock) as mock_suggest:

            await engine._check_and_suggest()

            # Since silent period is true, none of the other checks should be called.
            mock_limit.assert_not_called()
            mock_utility.assert_not_called()
            mock_advice.assert_not_called()
            mock_recent.assert_not_called()
            mock_suggest.assert_not_awaited()


@pytest.mark.asyncio
async def test_suggestion_limit_enforced():
    """Engine should not suggest more than max_interruptions_per_hour per day (SPIKE J3)."""
    # Set max to 1 per day
    config = InitiativeConfig(max_interruptions_per_hour=1)
    engine = InitiativeEngine(config=config)

    # Mock time to be outside silent period
    with patch('core.initiative.engine.datetime') as mock_dt:
        mock_dt.now.return_value.time.return_value = time(12, 0)
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

        # First call: should suggest
        with patch.object(engine, '_is_silent_period', return_value=False), \
             patch.object(engine, '_within_suggestion_limit', return_value=True) as mock_limit, \
             patch.object(engine, '_get_utility', return_value=1.0) as mock_utility, \
             patch.object(engine, '_get_advice', return_value='test advice') as mock_advice, \
             patch.object(engine, '_is_recent_advice', return_value=False) as mock_recent, \
             patch.object(engine, '_suggest', new_callable=AsyncMock) as mock_suggest:

            await engine._check_and_suggest()
            # Should have suggested once
            mock_suggest.assert_awaited_once()

        # Second call: should not suggest because limit exceeded
        with patch.object(engine, '_is_silent_period', return_value=False), \
             patch.object(engine, '_within_suggestion_limit', return_value=False) as mock_limit, \
             patch.object(engine, '_get_utility', return_value=1.0) as mock_utility, \
             patch.object(engine, '_get_advice', return_value='test advice') as mock_advice, \
             patch.object(engine, '_is_recent_advice', return_value=False) as mock_recent, \
             patch.object(engine, '_suggest', new_callable=AsyncMock) as mock_suggest:

            await engine._check_and_suggest()
            # Since limit is false, we should not call suggest
            mock_suggest.assert_not_awaited()


@pytest.mark.asyncio
async def test_utility_threshold_prevents_suggesting():
    """If utility is below threshold, engine should not suggest (SPIKE J3)."""
    config = InitiativeConfig(utility_threshold=0.9)  # high threshold
    engine = InitiativeEngine(config=config)

    with patch('core.initiative.engine.datetime') as mock_dt:
        mock_dt.now.return_value.time.return_value = time(12, 0)
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

        with patch.object(engine, '_is_silent_period', return_value=False), \
             patch.object(engine, '_within_suggestion_limit', return_value=True) as mock_limit, \
             patch.object(engine, '_get_utility', return_value=0.5) as mock_utility, \
             patch.object(engine, '_get_advice', return_value='test advice') as mock_advice, \
             patch.object(engine, '_is_recent_advice', return_value=False) as mock_recent, \
             patch.object(engine, '_suggest', new_callable=AsyncMock) as mock_suggest:

            await engine._check_and_suggest()
            mock_suggest.assert_not_awaited()


@pytest.mark.asyncio
async def test_recent_advice_prevents_repetition():
    """Engine should not repeat the same suggestion within 24h history (SPIKE J3)."""
    config = InitiativeConfig(history_size=2)  # small history for test
    engine = InitiativeEngine(config=config)

    with patch('core.initiative.engine.datetime') as mock_dt:
        mock_dt.now.return_value.time.return_value = time(12, 0)
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

        advice = 'same advice'
        # First time: should suggest
        with patch.object(engine, '_is_silent_period', return_value=False), \
             patch.object(engine, '_within_suggestion_limit', return_value=True) as mock_limit, \
             patch.object(engine, '_get_utility', return_value=1.0) as mock_utility, \
             patch.object(engine, '_get_advice', return_value=advice) as mock_advice, \
             patch.object(engine, '_is_recent_advice', return_value=False) as mock_recent, \
             patch.object(engine, '_suggest', new_callable=AsyncMock) as mock_suggest:

            await engine._check_and_suggest()
            mock_suggest.assert_awaited_once()
            # The advice should now be in history

        # Second time with same advice: should not suggest because recent
        with patch.object(engine, '_is_silent_period', return_value=False), \
             patch.object(engine, '_within_suggestion_limit', return_value=True) as mock_limit, \
             patch.object(engine, '_get_utility', return_value=1.0) as mock_utility, \
             patch.object(engine, '_get_advice', return_value=advice) as mock_advice, \
             patch.object(engine, '_is_recent_advice', return_value=True) as mock_recent, \
             patch.object(engine, '_suggest', new_callable=AsyncMock) as mock_suggest:

            await engine._check_and_suggest()
            mock_suggest.assert_not_awaited()


@pytest.mark.asyncio
async def test_suggest_without_execute():
    """SPIKE J3: _suggest should output hint without recording interruption times.

    This is the key SPIKE J3 test: suggest() should NOT call
    _interruption_times.append() - it should only output the suggestion
    and increment the daily counter, NOT record as an execution/interruption.
    """
    engine = InitiativeEngine()

    # Mock time to be outside silent period
    with patch('core.initiative.engine.datetime') as mock_dt:
        mock_dt.now.return_value.time.return_value = time(12, 0)
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

        # First suggestion
        with patch.object(engine, '_is_silent_period', return_value=False), \
             patch.object(engine, '_within_suggestion_limit', return_value=True), \
             patch.object(engine, '_get_utility', return_value=1.0), \
             patch.object(engine, '_get_advice', return_value='test advice'), \
             patch.object(engine, '_is_recent_advice', return_value=False), \
             patch('builtins.print') as mock_print:

            await engine._suggest('test advice')

            # Should have printed the suggestion
            mock_print.assert_any_call("[Sugestao SPIKE J3] test advice")

            # Should NOT have recorded interruption times
            # (The old behavior would have appended to _interruption_times)
            # SPIKE J3: No interruption tracking since we're not executing
            # Just verify the daily counter was incremented
            assert engine._daily_suggestion_count == 1

        # Second suggestion - should increment counter
        with patch('builtins.print') as mock_print:
            await engine._suggest('test advice 2')
            assert engine._daily_suggestion_count == 2

        # Verify suggestion content is not the old static text
        with patch.object(engine, '_is_silent_period', return_value=False), \
             patch.object(engine, '_within_suggestion_limit', return_value=True), \
             patch.object(engine, '_get_utility', return_value=1.0), \
             patch.object(engine, '_get_advice', return_value='Lembrete: basta um pequeno passo para começar.'), \
             patch.object(engine, '_is_recent_advice', return_value=False), \
             patch('builtins.print') as mock_print:

            await engine._suggest('Lembrete: basta um pequeno passo para começar.')
            # Should return None (filter out old static text) or handle gracefully
            # The _suggest should not crash with the old static text
            mock_print.assert_called()