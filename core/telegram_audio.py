"""ZARA-TELEGRAM-AUDIO-001 — entender o que o Alex fala pelo celular.

Ele mandou um áudio para o bot e ficou esperando: "eu mandei um audio la no bot
da zara e ate agora ninguem respondeu". A ponte só olhava `text`, então áudio
entrava e sumia sem ninguém saber.

Isso importa mais do que parece. O Alex prefere falar a digitar — é o motivo de
a ZARA existir. Uma ponte de celular que só aceita texto obriga justamente o
esforço que ela deveria eliminar.

Como funciona
-------------
O Telegram guarda o áudio e devolve um caminho de download. Baixamos o arquivo
(OPUS dentro de OGG) e mandamos para o Gemini transcrever. Nada de ffmpeg: o
Gemini aceita o formato como veio, e acrescentar um conversor externo seria mais
uma peça para quebrar num computador onde ela não está instalada.

O texto transcrito entra na MESMA porta que uma mensagem digitada — mesmo
roteamento, mesmas regras de dono, mesmo tudo. Áudio é só outra forma de
escrever; não ganha atalho nem permissão a mais.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

_TETO_DE_DOWNLOAD = 20 * 1024 * 1024  # 20 MB; recado de celular não passa disso
_MODELO = "gemini-2.5-flash"
_URL_GEMINI = (
    "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
)

_INSTRUCAO = (
    "Transcreva exatamente o que a pessoa fala neste áudio, em português do Brasil. "
    "Devolva SOMENTE a transcrição, sem aspas, sem comentários e sem descrever o áudio. "
    "Se não houver fala audível, devolva uma linha vazia."
)


def _chave_do_gemini() -> str:
    try:
        from core.paths import config_dir

        arquivo = config_dir() / "api_keys.json"
        if arquivo.exists():
            return str(
                json.loads(arquivo.read_text(encoding="utf-8")).get("gemini_api_key") or ""
            ).strip()
    except Exception:
        pass
    return ""


def _baixar_do_telegram(token: str, file_id: str) -> tuple[bytes, str]:
    """Devolve (conteúdo, erro). Um dos dois vem vazio."""
    pergunta = (
        f"https://api.telegram.org/bot{token}/getFile?"
        + urllib.parse.urlencode({"file_id": file_id})
    )
    try:
        with urllib.request.urlopen(pergunta, timeout=30) as resposta:
            corpo = json.loads(resposta.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return b"", f"não consegui localizar o áudio ({type(exc).__name__})"

    caminho = ((corpo or {}).get("result") or {}).get("file_path")
    if not caminho:
        return b"", "o Telegram não devolveu o arquivo"

    try:
        endereco = f"https://api.telegram.org/file/bot{token}/{caminho}"
        with urllib.request.urlopen(endereco, timeout=60) as resposta:
            dados = resposta.read(_TETO_DE_DOWNLOAD + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return b"", f"não consegui baixar o áudio ({type(exc).__name__})"

    if len(dados) > _TETO_DE_DOWNLOAD:
        return b"", "esse áudio é grande demais"
    return dados, ""


def _transcrever_no_gemini(dados: bytes, tipo: str, chave: str) -> tuple[str, str]:
    pedido = {
        "contents": [{
            "parts": [
                {"text": _INSTRUCAO},
                {"inline_data": {
                    "mime_type": tipo,
                    "data": base64.b64encode(dados).decode("ascii"),
                }},
            ]
        }],
        # Transcrever não é criar: temperatura alta aqui só inventa palavra.
        "generationConfig": {"temperature": 0.0},
    }
    requisicao = urllib.request.Request(
        _URL_GEMINI.format(modelo=_MODELO),
        data=json.dumps(pedido).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": chave},
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=120) as resposta:
            corpo = json.loads(resposta.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detalhe = ""
        try:
            detalhe = json.loads(exc.read().decode("utf-8", errors="replace"))
            detalhe = str((detalhe.get("error") or {}).get("message") or "")[:120]
        except Exception:
            pass
        return "", f"o Gemini recusou a transcrição ({exc.code} {detalhe})".strip()
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return "", f"não consegui falar com o Gemini ({type(exc).__name__})"

    try:
        partes = corpo["candidates"][0]["content"]["parts"]
        texto = " ".join(str(p.get("text") or "") for p in partes).strip()
    except (KeyError, IndexError, TypeError):
        return "", "o Gemini respondeu num formato que eu não entendi"

    return " ".join(texto.split()), ""


def transcrever(token: str, mensagem: dict) -> tuple[str, str]:
    """Áudio do Telegram -> texto. Devolve (transcrição, erro).

    Um dos dois vem sempre vazio. Nunca levanta exceção: isto roda dentro do
    laço da ponte, e derrubar o laço deixaria o Alex sem canal nenhum.
    """
    pedaco = mensagem.get("voice") or mensagem.get("audio") or {}
    file_id = pedaco.get("file_id")
    if not file_id:
        return "", "não veio áudio nenhum"

    chave = _chave_do_gemini()
    if not chave:
        return "", "não tenho a chave do Gemini para transcrever"

    dados, erro = _baixar_do_telegram(str(token), str(file_id))
    if erro:
        return "", erro

    tipo = str(pedaco.get("mime_type") or "audio/ogg")
    texto, erro = _transcrever_no_gemini(dados, tipo, chave)
    if erro:
        return "", erro
    if not texto:
        return "", "não consegui ouvir nenhuma fala nesse áudio"
    return texto, ""
