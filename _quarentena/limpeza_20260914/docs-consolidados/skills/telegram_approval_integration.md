# Telegram Approval Integration with Real Actions

## Trigger Conditions
When you need to implement a risky action in ZARA that requires explicit user approval via Telegram before execution in the real system.

## Context
This skill documents how to integrate Telegram-based remote approval with real action execution in ZARA 3.0, based on the completed task t_cedd17f6 (F2.9 Aprovação pelo Celular / Bridge Telegram → Ações Reais). The integration uses the RemoteApprovalBridge for state management and TelegramApprovalAdapter for communication.

## Steps

### 1. Set up the Remote Approval Bridge
```python
from core.remote_approval_bridge import RemoteApprovalBridge
from core.telegram_approval_adapter import TelegramApprovalAdapter

# Create the bridge with a token verifier (if needed)
def verify_telegram_token(token: str) -> bool:
    # Implement your Telegram token verification logic here
    # This could validate against stored bot tokens or user IDs
    return True  # Placeholder

bridge = RemoteApprovalBridge(verifier=verify_telegram_token)
```

### 2. Configure the Telegram Adapter
```python
# You need a "ponte" object that implements the avisar method
# This is typically your Telegram bridge/gateway object
class TelegramPonte:
    async def avisar(self, message: str) -> bool:
        # Implement actual Telegram sending logic here
        # Return True if message sent successfully, False otherwise
        pass

ponte = TelegramPonte()
adapter = TelegramApprovalAdapter(ponte)
```

### 3. Submit an Action for Approval
When ZARA needs to perform a risky action:
```python
# Generate a unique approval ID for the action
action_description = "Delete all temporary files in C:\\temp"
approval_id = bridge.submit_action(
    action_description=action_description,
    timeout_seconds=300  # 5 minutes to respond
)

# Send the approval request via Telegram
approval_message = f"ZARA requests approval for:\n{action_description}\n\nApproval ID: {approval_id}\nReply with /approve {approval_id} or /reject {approval_id}"

# Send via Telegram (this would typically be done async)
import asyncio
asyncio.create_task(adapter.send_request(approval_id, approval_message))
```

### 4. Handle the Telegram Response
When the user responds via Telegram:
```python
# When you receive a Telegram message like "/approve {id}" or "/reject {id}"
def handle_telegram_response(telegram_text: str) -> bool:
    # Parse the response to extract approval ID and action (approve/reject)
    # This is simplified - implement proper parsing based on your Telegram bot format
    parts = telegram_text.split()
    if len(parts) >= 3 and parts[0] in ["/approve", "/reject"]:
        action = parts[0][1:]  # Remove leading slash
        approval_id = parts[2]  # Assuming format: /approve <id>
        
        if action == "approve":
            return bridge.approve_action(approval_id, telegram_text)
        elif action == "reject":
            return bridge.reject_action(approval_id, telegram_text)
    
    return False  # Invalid format
```

### 5. Consume the Approval to Execute the Action
Once approved, consume the approval to execute the real action:
```python
from core.action_registry import execute_action

# Check if approved before consuming
if bridge.get_status(approval_id) == "approved":
    # Consume the approval (this transitions state from approved to consumed)
    if bridge.consume_approval(approval_id):
        # Now execute the real action
        result = await execute_action(
            "os_delete_files",  # Example action - replace with your actual action
            path="C:\\temp",
            confirm=True  # This confirms we have proper authorization
        )
        
        if result.success:
            return f"Action completed: {action_description}"
        else:
            return f"Action failed: {result.error}"
    else:
        return "Approval was consumed by another process or expired"
else:
    return f"Action not approved. Current status: {bridge.get_status(approval_id)}"
```

### 6. Clean Up Expired Approvals
The bridge automatically cleans up expired approvals, but you can manually trigger cleanup:
```python
# This is called automatically in most bridge methods, but can be called manually
import time
now = time.time()
# The bridge's internal cleanup handles expired records based on timeout
```

## Pitfalls
- **Token Verification**: Never skip token verification in production. The `_verify_token` method is critical for security.
- **State Management**: The bridge is thread-safe but must be used as a singleton. Creating multiple instances will break the approval flow.
- **Telegram Message Format**: Ensure your Telegram bot expects and parses the exact format you're sending (e.g., "/approve {id}").
- **Action Consumption**: Remember that `consume_approval()` is a one-time operation. Once consumed, the same ID cannot be used again.
- **Timeout Handling**: Approvals expire automatically based on the timeout set in `submit_action()`. Handle expired approvals gracefully in your UI.
- **Duplicate Requests**: Avoid submitting the same action multiple times without consuming previous approvals, as this can create confusion.
- **Error Handling**: The Telegram adapter returns False on any exception - implement proper logging to distinguish between network issues and bot errors.
- **Security**: Never execute actions based solely on Telegram response without consuming the approval through the bridge.

## Verification Steps
1. **Unit Test Verification**:
   - Run `pytest tests/test_telegram_approval_adapter.py -v` to ensure adapter tests pass
   - Verify remote_approval_bridge.py has adequate test coverage

2. **Integration Test**:
   - Submit an action via the bridge
   - Verify a Telegram message is sent with the correct format
   - Simulate a Telegram approval response
   - Verify the bridge state transitions from pending → approved
   - Verify consume_approval() returns True only once for an approved action
   - Verify the real action executes only after approval consumption

3. **End-to-End Test**:
   - Trigger a risky action in ZARA (e.g., file deletion, system change)
   - Verify Telegram notification is received
   - Approve via Telegram
   - Verify the action executes in the real system
   - Verify rejection prevents action execution
   - Verify expired requests don't execute actions

4. **Manual Verification Checklist**:
   - [ ] Bridge correctly generates unique approval IDs
   - [ ] Telegram adapter successfully sends messages via the ponte
   - [ ] Approval/reject responses correctly update bridge state
   - [ ] Consume_approval() atomically transitions approved → consumed
   - [ ] Actions only execute after successful consumption
   - [ ] Expired approvals are automatically cleaned up
   - [ ] Invalid tokens are rejected
   - [ ] Replayed approval attempts are rejected
   - [ ] Bridge handles concurrent requests safely

## References
- `core/remote_approval_bridge.py` - Core approval state management
- `core/telegram_approval_adapter.py` - Telegram communication adapter
- `tests/test_telegram_approval_adapter.py` - Adapter test suite
- `docs/arquitetura_zara-brain.md` - Architecture documentation (sections on Remote Approval and Telegram flow)
- `core/ipc_handlers.py` - Shows integration points in the IPC handler

## Notes
This implementation follows the "fail closed" principle - if any part of the approval chain fails, the action does not execute. The separation of concerns between approval state management (bridge) and communication (adapter) allows for flexible integration with different communication channels while maintaining a consistent approval workflow.