import sys
import time
from core.actions.ponte_claude import codex_enviar_action, codex_ler_action

def main():
    # Initial message from user
    initial_msg = "Oi eu sou o seu funcionario preciso de instrucoes precisas do que fazer"
    print(f"Enviando mensagem ao Codex: {initial_msg}")
    result = codex_enviar_action(initial_msg)
    if not result.success:
        print(f"Falha ao enviar mensagem: {result.error}")
        sys.exit(1)
    print("Mensagem enviada. Aguardando resposta do Codex...")
    # Wait a bit for Codex to respond
    time.sleep(5)  # adjustable
    # Try to read the response
    read_result = codex_ler_action()
    if not read_result.success:
        print(f"Falha ao ler resposta: {read_result.error}")
        sys.exit(1)
    print("Resposta do Codex:")
    print(read_result.output)
    # Optionally, we could parse the response and execute actions here
    # For now, just show the response.

if __name__ == "__main__":
    main()