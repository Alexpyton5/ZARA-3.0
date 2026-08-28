# Telegram Pairing Recipe

**Prerequisite**: Ensure `HERMES_HOME` points to the Hermes installation directory (e.g., `%LOCALAPPDATA%\hermes\hermes-agent`).

## Steps

1. **Check for pending requests**
   ```bat
   hermes pairing list
   ```
   - If no pending requests appear, the bot will DM you a fresh 8‑character pairing code.

2. **Receive the pairing code**
   - The bot DMs an 8‑character code using the alphabet `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (no 0/O/1/I).

3. **Approve the pairing**
   ```bat
   hermes pairing approve telegram <CODE>
   ```
   Example:
   ```bat
   hermes pairing approve telegram DX964SQ6
   ```

4. **Restart the gateway (required)**
   - Approval takes effect only after the gateway process reloads approved users.
   - Run:
     ```bat
     hermes gateway restart
     ```
   - Or manually stop and start the gateway process if needed.

5. **Verify**
   - Send a test message to the bot; it should respond.
   - Optionally re‑run `hermes pairing list` to confirm the user is now approved.

**Note**: If you approve in the wrong profile, the gateway that owns the bot token will not recognize the approval. Verify which gateway (`gateway_state.json`) shows `state: connected` for Telegram and approve in that profile’s `HERMES_HOME`.

**PITFALL**: Do **not** assume the approval is immediate; the running gateway must be restarted for the change to take effect.