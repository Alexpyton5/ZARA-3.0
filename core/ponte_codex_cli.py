"""ZARA-PONTE-CODEX-CLI-001 — falar com o Codex sem passar pela tela.

Por que este arquivo existe
---------------------------
A ponte com o Codex era feita digitando na janela do app do ChatGPT e lendo a
resposta de volta pela acessibilidade do Windows. Isso funciona, mas é frágil
por natureza: depende da janela estar aberta, de ela vir para a frente, de a
caixa de texto ser encontrada, e de o texto renderizado ser legível. Cada uma
dessas etapas já falhou de verdade, e a pior delas falhou em silêncio — a
leitura descartava trechos curtos e entregava frases furadas que pareciam
inteiras (ver `ZARA-PONTE-LEITURA-BURACO-001`).

O próprio Codex apontou a saída: tirar a tela do caminho e usar o CLI, que
devolve eventos estruturados. E fez uma ressalva que define o desenho daqui:

    "esta janela não é um espelho documentado de uma sessão separada do CLI.
     Se você colar aqui toda mensagem do canal estruturado, pode criar um
     segundo agente e duas histórias divergentes."

Ele está certo. Então as duas coisas ficam separadas e não se misturam:

    janela do ChatGPT  -> a conversa pessoal do Alex com o Codex. Ninguém
                          escreve nela sem ele pedir.
    este canal         -> a conversa da ZARA com o Codex. Fonte da verdade.
                          O Alex acompanha pelo Telegram.

Memória entre mensagens
-----------------------
Uma chamada por mensagem criaria uma sessão nova a cada vez e o Codex perderia
o fio. O CLI resolve isso com `codex exec resume <thread_id>`, então o id da
conversa fica guardado em disco e é reusado. Só se perde o fio se o arquivo
sumir — e aí ele começa uma conversa nova, em vez de quebrar.

Segurança
---------
Roda com sandbox `read-only` de propósito. Este canal existe para conversar e
para o Codex poder LER o projeto, não para ele mexer no computador do Alex sem
ninguém olhando. Ampliar isso é decisão do Alex, numa tarefa própria — nunca
efeito colateral desta.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent

# Um turno do Codex pode envolver leitura de arquivos e raciocínio longo.
# Curto demais mata a resposta no meio; infinito trava a ZARA.
#
# ZARA-CODEX-PACIENCIA-001. Cinco minutos servem para conversa e mataram duas
# tarefas de verdade: classificar 70 ações e uma pesquisa profunda na web. Nos
# dois casos ele estava trabalhando e eu desliguei na cara dele — e o relatório
# saiu como "o Codex não respondeu", que é acusação errada.
#
# Conversa continua com teto curto (o Alex está esperando na frente do celular);
# trabalho de fundo ganha paciência, porque ninguém está olhando.
_TETO_DE_ESPERA = 300.0
_TETO_DE_TRABALHO = 1500.0  # 25 min para pesquisa e varredura


def _executavel() -> str | None:
    """Onde está o `codex`, por caminho explícito sempre que possível.

    Regra do projeto: não depender do PATH, que já resolveu para o ambiente de
    outro projeto no passado.
    """
    achado = shutil.which("codex")
    if achado:
        return achado
    candidatos = [
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs" / "nodejs" / "node-v24.18.0-win-x64" / "codex.cmd",
        Path(os.environ.get("APPDATA", "")) / "npm" / "codex.cmd",
    ]
    for c in candidatos:
        if c.exists():
            return str(c)
    return None


def _arquivo_da_conversa() -> Path:
    from core.paths import user_data_dir

    return user_data_dir() / "codex_conversa.json"


# ZARA-CODEX-FIO-NOVO-001
#
# Alex, ao ver a conta subir: "isso de fio novo é o que mesmo".
#
# Cada mensagem num fio retomado reenvia a conversa inteira. Medido em
# 2026-08-14: começou em 16 mil tokens de entrada e chegou a 417 mil em um dia
# de conversa. A partir daí cada pergunta ficava mais lenta e mais cara que a
# anterior, e uma delas simplesmente falhou.
#
# Quem carrega essa conta é o Codex, mas o prejuízo é do Alex de qualquer jeito:
# resposta lenta. Então o fio se aposenta sozinho quando fica pesado, e o
# seguinte começa com um resumo curto em vez da bagagem toda — que foi
# exatamente o que o Codex recomendou ("mantenha um resumo curto da missão").
_FIO_PESADO = 250_000  # tokens de entrada; acima disso, aposenta


def _estado() -> dict:
    try:
        arquivo = _arquivo_da_conversa()
        if arquivo.exists():
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            if isinstance(dados, dict):
                return dados
    except Exception:
        pass
    return {}


def _thread_guardada() -> str | None:
    return str(_estado().get("thread_id") or "") or None


def _resumo_guardado() -> str:
    return str(_estado().get("resumo") or "")


def _guardar_thread(thread_id: str, *, entrada: int = 0, resumo: str = "") -> None:
    try:
        arquivo = _arquivo_da_conversa()
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        dados = _estado()
        dados["thread_id"] = thread_id
        if entrada:
            dados["ultima_entrada"] = int(entrada)
        if resumo:
            dados["resumo"] = resumo[:600]
        arquivo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass  # perder o fio é chato, não é fatal


def _fio_ficou_pesado() -> bool:
    return int(_estado().get("ultima_entrada") or 0) >= _FIO_PESADO


def esquecer_a_conversa() -> None:
    """Começa do zero na próxima mensagem. Usado quando o fio se embaraça."""
    try:
        _arquivo_da_conversa().unlink(missing_ok=True)
    except Exception:
        pass


def _montar_comando(
    exe: str, mensagem: str, saida: Path, thread: str | None, escrever: bool = False
) -> list[str]:
    """Monta a linha de comando. `resume` NÃO aceita as mesmas opções de `exec`.

    Medido em codex-cli 0.146.0: `exec resume` recusa `-s` e `-C`
    ("error: unexpected argument '-s' found"). O sandbox continua sendo
    read-only, só que declarado por configuração, que o resume aceita — deixar
    cair para o padrão daria mais permissão do que esta ponte deveria ter. O
    diretório não precisa ser repetido: a sessão retomada já sabe o dela.
    """
    # ZARA-CODEX-MULTILINHA-001
    #
    # A mensagem NÃO vai mais na linha de comando: vai por stdin, e o `-` diz
    # ao CLI para ler de lá.
    #
    # Motivo, observado duas vezes: qualquer pedido com quebra de linha voltava
    # vazio, com um resto de erro no lugar da resposta. Eu contornei a primeira
    # vez achatando o texto numa linha só — o que fez a falha voltar depois,
    # numa tarefa longa, e ainda me fez culpar o Codex por não responder.
    #
    # Isso não era um detalhe de conforto: mensagem do Telegram tem quebra de
    # linha o tempo todo. Alex teria pedido algo em duas linhas e o Codex ficaria
    # mudo, sem ninguém saber por quê.
    comum = ["--json", "-o", str(saida), "--skip-git-repo-check"]
    modo = "workspace-write" if escrever else "read-only"
    if thread:
        return [
            exe, "exec", "resume", thread, "-",
            "-c", f'sandbox_mode="{modo}"',
            *comum,
        ]
    return [
        exe, "exec", "-",
        "-s", modo,
        "-C", str(RAIZ_DO_PROJETO),
        *comum,
    ]


def _ler_eventos(saida_bruta: str) -> tuple[str | None, str, dict]:
    """Devolve (thread_id, texto do agente, uso de tokens) do JSONL do CLI."""
    thread_id = None
    falas: list[str] = []
    uso: dict = {}
    for linha in saida_bruta.splitlines():
        linha = linha.strip()
        if not linha.startswith("{"):
            continue
        try:
            evento = json.loads(linha)
        except Exception:
            continue
        tipo = evento.get("type")
        if tipo == "thread.started":
            thread_id = evento.get("thread_id") or thread_id
        elif tipo == "item.completed":
            item = evento.get("item") or {}
            if item.get("type") == "agent_message" and item.get("text"):
                falas.append(str(item["text"]))
        elif tipo == "turn.completed":
            uso = evento.get("usage") or {}
    return thread_id, "\n\n".join(falas).strip(), uso


def falar_com_codex(
    mensagem: str,
    *,
    novo_assunto: bool = False,
    trabalho_longo: bool = False,
    escrever: bool = False,
) -> tuple[str, str]:
    """Manda uma mensagem ao Codex e devolve (resposta, erro).

    `trabalho_longo=True` para pesquisa e varredura, onde ninguém está esperando
    na frente da tela. Ver ZARA-CODEX-PACIENCIA-001.

    `escrever=True` libera o Codex para MODIFICAR arquivos. Autorizado por Alex
    em 15/08, com condições que não são opcionais: área delimitada que nenhum
    outro agente esteja tocando, e relatório do que ele mexeu. O padrão continua
    sendo somente leitura — escrever é decisão explícita de quem chama, nunca o
    comportamento normal desta ponte.

    Um dos dois vem vazio. Nunca levanta exceção: esta ponte roda dentro do
    laço do Telegram, e derrubar o laço deixaria o Alex sem canal nenhum.
    """
    texto = str(mensagem or "").strip()
    if not texto:
        return "", "Chegou vazio."

    exe = _executavel()
    if not exe:
        return "", "Não encontrei o Codex instalado neste computador."

    # ZARA-CODEX-FIO-NOVO-001: o fio se aposenta sozinho antes de ficar lento.
    aposentou = False
    if novo_assunto or _fio_ficou_pesado():
        aposentou = not novo_assunto
        resumo = _resumo_guardado()
        esquecer_a_conversa()
        if aposentou:
            print("[CODEX_CLI] fio antigo aposentado por peso; comecando outro", flush=True)
            if resumo:
                texto = (
                    f"[retomando do zero para nao ficar lento; onde estavamos: {resumo}]\n\n"
                    f"{texto}"
                )
    thread = _thread_guardada()

    with tempfile.TemporaryDirectory(prefix="zara-codex-") as pasta:
        saida = Path(pasta) / "ultima.txt"
        comando = _montar_comando(exe, texto, saida, thread, escrever)
        try:
            processo = subprocess.run(  # noqa: S603 - comando montado aqui, sem shell
                comando,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_TETO_DE_TRABALHO if trabalho_longo else _TETO_DE_ESPERA,
                # ZARA-CODEX-MULTILINHA-001: a mensagem entra por aqui, não pela
                # linha de comando. Fecha o stdin depois de escrever, então o
                # CLI não fica esperando mais nada.
                input=texto,
                check=False,
            )
        except subprocess.TimeoutExpired:
            minutos = int((_TETO_DE_TRABALHO if trabalho_longo else _TETO_DE_ESPERA) // 60)
            return "", f"O Codex passou de {minutos} minutos sem responder."
        except Exception as exc:
            return "", f"Não consegui chamar o Codex: {type(exc).__name__}"

        thread_novo, resposta, uso = _ler_eventos(processo.stdout or "")

        # O `-o` é a resposta final segundo o próprio CLI; os eventos são o
        # rastro. Quando os dois existem, o arquivo manda.
        try:
            if saida.exists():
                do_arquivo = saida.read_text(encoding="utf-8", errors="replace").strip()
                if do_arquivo:
                    resposta = do_arquivo
        except Exception:
            pass

    if thread_novo:
        # O resumo guardado é a última troca, curta: é o que sobrevive quando o
        # fio se aposentar, para o próximo não começar sem saber de nada.
        _guardar_thread(
            thread_novo,
            entrada=int(uso.get("input_tokens") or 0),
            resumo=f"eu perguntei sobre '{texto[:120]}' e voce respondeu '{(resposta or '')[:200]}'",
        )

    if not resposta:
        erro = (processo.stderr or "").strip().splitlines()
        motivo = erro[-1] if erro else f"codigo {processo.returncode}"
        return "", f"O Codex não devolveu resposta ({motivo[:160]})."

    if uso:
        print(
            f"[CODEX_CLI] entrada={uso.get('input_tokens')} "
            f"saida={uso.get('output_tokens')} thread={thread_novo or thread}",
            flush=True,
        )
    return resposta, ""
