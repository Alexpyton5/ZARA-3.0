import sys
sys.path.insert(0, 'C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002')
from core.paths import data_dir, user_data_dir
import sqlite3
import re
import time
import unicodedata

# Path to conversation history
conv_db = data_dir() / "conversation_history.sqlite3"
# Path to aprendizado db
aprendizado_db = user_data_dir() / "data" / "aprendizado" / "experiencias.db"

def _sem_acento(texto: str) -> str:
    base = unicodedata.normalize("NFKD", str(texto or "").casefold())
    return "".join(c for c in base if not unicodedata.combining(c))

# Define the patterns from _RECLAMACAO and _APROVACAO in aprendizado.py
_RECLAMACAO = (
    r"\bn[ãa]o\s+(?:[ée]\s+)?(?:isso|isto|era|foi)\b",
    r"\bn[ãa]o\s+(?:foi|era)\s+(?:isso|isto|o\s+que)\b",
    r"\berrad[oa]\b",
    r"\bn[ãa]o\s+(?:e|é)\s+bem\s+isso\b",
    r"\bnem\s+era\s+isso\b",
    r"\bde\s+novo\b.*\bn[ãa]o\b",
    r"\bpedi\s+(?:outra|outro|foi)\b",
    r"\bnada\s+(?:aconteceu|mudou)\b",
    r"\bn[ãa]o\s+(?:funcionou|fez|executou|mudou|aconteceu)\b",
    r"\bcontinua\s+(?:igual|do\s+mesmo\s+jeito|a\s+mesma)\b",
)
_APROVACAO = (
    r"\b(?:isso|perfeito|exato|isso\s+mesmo|boa|ótimo|otimo|show|funcionou|deu\s+certo)\b",
    r"\bagora\s+sim\b",
    r"\bera\s+isso\b",
)

def matches_complaint(text):
    texto = _sem_acento(text)
    return any(re.search(p, texto) for p in _RECLAMACAO)

def matches_approval(text):
    texto = _sem_acento(text)
    return any(re.search(p, texto) for p in _APROVACAO) and len(texto) < 60

print("=== Conversation History User Messages (last 10) ===")
try:
    conn = sqlite3.connect(str(conv_db))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT content, created_at 
        FROM conversation_messages 
        WHERE role = 'user' 
        ORDER BY created_at DESC 
        LIMIT 10
    """)
    rows = cursor.fetchall()
    for i, (content, created_at_ms) in enumerate(rows):
        created_at = created_at_ms / 1000.0
        print(f"{i+1}. [{time.ctime(created_at)}] {content}")
    conn.close()
except Exception as e:
    print("Error reading conversation history:", e)

print("\n=== Checking for complaint/approval patterns in user messages ===")
try:
    conn = sqlite3.connect(str(conv_db))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT content, created_at 
        FROM conversation_messages 
        WHERE role = 'user' 
        ORDER BY created_at DESC 
        LIMIT 1000
    """)
    rows = cursor.fetchall()
    complaint_count = 0
    approval_count = 0
    for content, created_at_ms in rows:
        if matches_complaint(content):
            complaint_count += 1
            if complaint_count <= 5:
                print(f"COMPLAINT: {content}")
        if matches_approval(content):
            approval_count += 1
            if approval_count <= 5:
                print(f"APPROVAL: {content}")
    print(f"Total complaint matches: {complaint_count}")
    print(f"Total approval matches: {approval_count}")
    conn.close()
except Exception as e:
    print("Error checking patterns:", e)

print("\n=== Checking timestamps: action vs user message ===")
# We want to see if there are any user messages within 90 seconds of an action
# that match the patterns.
# First, get the list of actions (episodios) with their timestamps.
try:
    conn = sqlite3.connect(str(aprendizado_db))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pedido, acao, sucesso, quando, reacao
        FROM episodios
        ORDER BY quando DESC
        LIMIT 100
    """)
    acciones = cursor.fetchall()
    conn.close()
except Exception as e:
    print("Error reading episodios:", e)
    acciones = []

# Get user messages from conversation history
try:
    conn = sqlite3.connect(str(conv_db))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT content, created_at
        FROM conversation_messages
        WHERE role = 'user'
        ORDER BY created_at DESC
        LIMIT 1000
    """)
    user_msgs = cursor.fetchall()
    conn.close()
except Exception as e:
    print("Error reading user messages:", e)
    user_msgs = []

# Convert to seconds since epoch
actions_with_time = [(pedido, acao, sucesso, quando, reacao) for (pedido, acao, sucesso, quando, reacao) in acciones]
user_msgs_with_time = [(content, created_at_ms/1000.0) for (content, created_at_ms) in user_msgs]

print(f"Found {len(actions_with_time)} recent actions and {len(user_msgs_with_time)} recent user messages.")

# For each action, look for user messages within 90 seconds after the action time.
matches_found = 0
for pedido, acao, sucesso, cuando, reacao in acciones:
    # When is the action time? (in seconds)
    action_time = cuando
    # Look for user messages that occurred after the action and within 90 seconds.
    for content, msg_time in user_msgs_with_time:
        if msg_time >= action_time and msg_time <= action_time + 90.0:
            # Check if this user message matches complaint or approval
            if matches_complaint(content) or matches_approval(content):
                matches_found += 1
                if matches_found <= 5:
                    print(f"MATCH: Action '{pedido}' ({acao}) at {time.ctime(action_time)} -> User message '{content}' at {time.ctime(msg_time)} (delta {msg_time - action_time:.1f}s)")
                # Break after first match for this action to avoid too much output.
                break
    # If we found 5 matches, break out of the outer loop too.
    if matches_found >= 5:
        break

print(f"Total action-user message matches (within 90s and matching pattern): {matches_found}")

# Also, let's check the opposite: user messages that occur before an action (within 90 seconds before) 
# but that doesn't make sense for a reaction. Reaction should be after action.
print("\n=== End of check ===")