# test_nervos.py — testes do protocolo (roda com: python3 test_nervos.py)
from nervos import (criar_envelope, validar_envelope, para_json,
                    de_json, eh_urgente)

falhas = 0
def check(nome, cond):
    global falhas
    falhas += 0 if cond else 1
    print(("OK  " if cond else "FAIL"), nome)

# 1. envelope válido
env = criar_envelope("zoe", "codex", "ordem", "pasta-lixo",
                     "Move o lixo pra C:\\Users\\alexp\\lixo",
                     prioridade="normal", precisa_resposta=True, seq=7)
ok, erros = validar_envelope(env)
check("envelope válido", ok and env["id"].startswith("nervo-"))

# 2. urgente detectado
u = criar_envelope("zoe", "codex", "alerta", "trava", "Travou tudo",
                   prioridade="urgente", seq=8)
check("urgente detectado", eh_urgente(u) and not eh_urgente(env))

# 3. tipo inválido rejeitado
try:
    criar_envelope("zoe", "codex", "fofoca", "a", "b")
    check("tipo inválido rejeitado", False)
except ValueError:
    check("tipo inválido rejeitado", True)

# 4. campo faltando rejeitado
ok2, erros2 = validar_envelope({"tipo": "ordem"})
check("campo faltando rejeitado", not ok2 and len(erros2) > 3)

# 5. json vai e volta intacto
volta = de_json(para_json(env))
check("json intacto", volta == env)

# 6. json inválido rejeitado
try:
    de_json('{"tipo": "ordem"}')
    check("json inválido rejeitado", False)
except ValueError:
    check("json inválido rejeitado", True)

# 7. resposta no formato do protocolo (já fiz / tô fazendo / falta)
r = criar_envelope("codex", "zoe", "resposta", "pasta-lixo",
                   "Já fiz: criei a pasta. Tô fazendo: movendo o uv cache. Falta: Temp e logs.",
                   seq=9)
ok3, _ = validar_envelope(r)
check("resposta no formato", ok3 and "Falta:" in r["corpo"])

print()
print("TUDO VERDE" if falhas == 0 else f"{falhas} FALHAS")
raise SystemExit(1 if falhas else 0)
