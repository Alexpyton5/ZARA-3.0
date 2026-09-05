"""ZARA-VIBE-GUARDRAILS-001 (Alex, 2026-08-28)

Peca ISOLADA, nao plugada em nenhum caminho de producao. Duas funcoes de
ANALISE PURA -- nenhuma delas bloqueia, corrige ou executa nada sozinha,
so devolve um veredito pra quem chamar decidir o que fazer.

check_command_safety: detecta comando de terminal perigoso (exclusao em
massa, reset destrutivo de git, formatacao de disco) e chave/segredo prestes
a vazar. translate_crash_log: traduz o tipo de excecao Python mais comum pro
portugues simples, sem inventar causa quando o texto nao bate com nada
conhecido.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Padroes fechados, mesma disciplina do resto do projeto: melhor um falso
# negativo (nao detectou) do que inventar risco onde nao ha. Cada entrada e
# (regex, motivo curto em portugues).
_DANGEROUS_COMMAND_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\brm\s+-rf?\s+[/~]", "apaga pasta inteira recursivamente (rm -rf)"),
    (r"\bdel\s+/[fsq]{1,3}\b", "exclusão forçada em massa no Windows (del /f /s /q)"),
    (r"\brmdir\s+/s\b", "remove diretório inteiro recursivamente (rmdir /s)"),
    (r"\bgit\s+reset\s+--hard\b", "descarta mudanças locais sem volta (git reset --hard)"),
    (r"\bgit\s+clean\s+-[a-z]*f", "apaga arquivo não versionado sem volta (git clean -f)"),
    (r"\bgit\s+push\s+.*--force\b", "sobrescreve histórico remoto (git push --force)"),
    (r"\bformat\s+[a-z]:", "formata um disco inteiro (format)"),
    (r"\bdrop\s+(table|database)\b", "apaga tabela ou banco inteiro (DROP)"),
    (r"\bdelete\s+from\s+\w+\s*;?\s*$", "DELETE sem WHERE apaga a tabela inteira"),
    (r"\bshutdown\s+/[rs]\b", "desliga ou reinicia a máquina (shutdown)"),
)

# Formatos comuns de chave/token que não deveriam aparecer soltos num
# comando de commit/push. Fechado de propósito -- perde alguns formatos
# novos, mas nunca marca algo comum como chave por engano.
_SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bsk-[A-Za-z0-9]{20,}", "parece uma chave de API estilo OpenAI/Anthropic (sk-...)"),
    (r"\bAKIA[0-9A-Z]{16}\b", "parece uma chave de acesso AWS (AKIA...)"),
    (r"\bghp_[A-Za-z0-9]{20,}", "parece um token de acesso pessoal do GitHub (ghp_...)"),
    (r"\bAIza[0-9A-Za-z\-_]{20,}", "parece uma chave de API do Google (AIza...)"),
)


@dataclass(frozen=True, slots=True)
class SafetyVerdict:
    safe: bool
    risk_level: str  # "low" | "high"
    reasons: list[str] = field(default_factory=list)


def check_command_safety(command: str) -> dict:
    """Analisa um comando de terminal ANTES de rodar. Só devolve veredito --
    quem chamar decide se bloqueia, pede confirmação ou deixa passar."""
    text = str(command or "")
    reasons: list[str] = []

    for pattern, reason in _DANGEROUS_COMMAND_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            reasons.append(reason)

    for pattern, reason in _SECRET_PATTERNS:
        if re.search(pattern, text):
            reasons.append(reason)

    verdict = SafetyVerdict(
        safe=not reasons,
        risk_level="high" if reasons else "low",
        reasons=reasons,
    )
    return {"safe": verdict.safe, "risk_level": verdict.risk_level, "reasons": verdict.reasons}


# (regex sobre a ÚLTIMA linha do traceback, explicação, sugestão)
_CRASH_TRANSLATIONS: tuple[tuple[str, str, str], ...] = (
    (
        r"ModuleNotFoundError: No module named '([^']+)'",
        "O Python não encontrou o pacote '{0}' instalado.",
        "Rode a instalação do pacote no ambiente virtual do projeto (nunca 'python' solto).",
    ),
    (
        r"ImportError: cannot import name '([^']+)'",
        "O código tentou importar '{0}', mas esse nome não existe (ou mudou) no módulo de origem.",
        "Confira se '{0}' ainda existe lá e se o nome não foi renomeado.",
    ),
    (
        r"SyntaxError: (.+)",
        "Erro de sintaxe no código: {0}.",
        "Reveja a linha apontada no traceback — geralmente parêntese, dois-pontos ou indentação faltando.",
    ),
    (
        r"IndentationError: (.+)",
        "Indentação errada: {0}.",
        "Python usa espaços/tabs pra marcar bloco de código — confira se a linha está alinhada com as vizinhas.",
    ),
    (
        r"NameError: name '([^']+)' is not defined",
        "A variável ou função '{0}' foi usada antes de existir (não foi definida ou está fora de escopo).",
        "Confira se '{0}' foi criada antes desse ponto do código, e se está no mesmo escopo.",
    ),
    (
        r"AttributeError: '([^']+)' object has no attribute '([^']+)'",
        "Um objeto do tipo '{0}' não tem o atributo/método '{1}' que o código tentou usar.",
        "Confira se o objeto é mesmo do tipo esperado, ou se '{1}' foi digitado errado.",
    ),
    (
        r"TypeError: (.+)",
        "Tipo de dado incompatível com a operação: {0}.",
        "Confira se os argumentos passados são do tipo que a função espera.",
    ),
    (
        r"KeyError: '?([^'\n]+)'?",
        "Tentou acessar a chave '{0}' num dicionário que não tem essa chave.",
        "Confira se '{0}' existe antes de acessar, ou use .get('{0}') com um valor padrão.",
    ),
    (
        r"FileNotFoundError: .*'([^']+)'",
        "O arquivo ou pasta '{0}' não existe no caminho informado.",
        "Confira se o caminho está certo e se o arquivo já foi criado antes desse ponto.",
    ),
    (
        r"PermissionError: (.+)",
        "O sistema recusou o acesso ao arquivo/recurso: {0}.",
        "Confira se outro programa está com o arquivo aberto/travado, ou se falta permissão.",
    ),
    (
        r"ZeroDivisionError",
        "O código tentou dividir um número por zero.",
        "Confira o valor do denominador antes da divisão.",
    ),
)


def translate_crash_log(stack_trace: str) -> str:
    """Traduz a ÚLTIMA linha de exceção de um traceback Python pro
    português simples. Se não reconhecer o formato, diz isso honestamente
    em vez de inventar uma causa."""
    text = str(stack_trace or "").strip()
    if not text:
        return "Nenhum log de erro foi informado."

    # A causa real normalmente está na última linha não-vazia do traceback.
    last_line = next((line for line in reversed(text.splitlines()) if line.strip()), text)

    for pattern, explanation, suggestion in _CRASH_TRANSLATIONS:
        match = re.search(pattern, last_line)
        if match:
            groups = match.groups()
            return f"{explanation.format(*groups)} Sugestão: {suggestion.format(*groups)}"

    return (
        "Não reconheci esse formato de erro pra traduzir com segurança. "
        f"Última linha do log: {last_line!r}"
    )
