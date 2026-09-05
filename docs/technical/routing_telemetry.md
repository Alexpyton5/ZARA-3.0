# Routing Telemetry in ZARA 3.0

## Overview

The routing telemetry system in ZARA 3.0 records the outcomes of task execution to provide insights into system performance and suggest areas for improvement. Importantly, it only produces review-only suggestions and has no ability to automatically reconfigure the router, ensuring safety.

## Purpose

- Record routing outcomes (which executor/model was used, duration, success/failure, fallback usage)
- Generate review-only suggestions (`ROUTING_CANDIDATE`) for weak routes that need human attention
- Maintain a rolling window of the most recent events (default 1,000 events)
- Provide aggregate statistics by task type, executor, and model
- Operate safely within ZARA's writable data boundary without affecting core functionality

## Key Features

### Safety First
- Telemetry module has no dependency on, or write access to, router rules
- Telemetry can never reconfigure the assistant by itself
- Suggestions (`ROUTING_CANDIDATE`) require explicit human review and approval
- Failures in telemetry persistence are observable but don't prevent ZARA from starting

### Data Collected
For each routing event, the system records:
- Timestamp
- Task type (e.g., voice command, file operation, web search)
- Executor (who/what performed the task)
- Model used (if applicable)
- Duration of execution
- Success/failure status
- Error message (truncated to prevent log bloat)
- Whether a fallback was used

### Telemetry Functions
1. **record()** - Store one routing result
2. **get_events()** - Retrieve recent events, optionally filtered by task type
3. **get_aggregates()** - Get statistics grouped by task, executor, and model
4. **routing_candidates()** - Suggest weak routes for human review based on:
   - Minimum samples threshold (default 5)
   - Maximum success rate threshold (default 0.6)
   - Minimum fallback rate threshold (default 0.4)

## Implementation Details

The telemetry system is implemented in `core/routing_telemetry.py` using:

- Thread-safe operations with `threading.RLock()`
- JSON persistence to `data/routing/telemetry.json`
- Event validation to prevent corruption
- Automatic cleanup of old events beyond `MAX_EVENTS` (1,000)
- Error tracking for persistence failures
- Safe string handling to prevent injection issues

## Status

**PRONTO** — Functional and tested as part of Fases 1-2. The routing telemetry system records executor, model, time, result, and fallback information, with suggestions requiring human review.