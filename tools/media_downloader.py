"""ZARA-MEDIA-DOWNLOADER-001 (Alex, 2026-08-28)

Modulo isolado pra baixar audio (MP3) de URL ou termo de busca via yt-dlp.
Nao e chamado por nenhum caminho de producao ainda -- e a peca em si.

Dependencia nova (yt-dlp) adicionada como passo separado e nomeado em
requirements.txt no mesmo dia, por pedido explicito do Alex -- nao foi
instalada como efeito colateral de outra tarefa.
"""
from __future__ import annotations

from pathlib import Path

import yt_dlp


class MediaDownloadError(RuntimeError):
    """Levantado quando o download falha (rede, URL invalida, sem audio)."""


def download_audio(url_or_query: str, output_dir: str = "Downloads") -> str:
    """Baixa o audio de uma URL (ou o primeiro resultado de uma busca no
    YouTube, se `url_or_query` nao for uma URL) e extrai em MP3.

    Devolve o caminho absoluto do MP3 gerado. Levanta MediaDownloadError com
    mensagem legivel se falhar -- nunca retorna string vazia/None fingindo
    sucesso (mesma regra de "nunca finge que executou" do resto do projeto).
    """
    query = str(url_or_query or "").strip()
    if not query:
        raise MediaDownloadError("Nenhum link ou termo de busca informado.")

    target_dir = Path(output_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # yt-dlp resolve "ytsearch1:<termo>" como "busca no YouTube, pegue o
    # primeiro resultado" -- nao precisamos de scraping proprio.
    source = query if query.startswith(("http://", "https://")) else f"ytsearch1:{query}"

    options = {
        "format": "bestaudio/best",
        "outtmpl": str(target_dir / "%(title)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(source, download=True)
            if "entries" in info:
                info = info["entries"][0]
            base_path = Path(ydl.prepare_filename(info))
            mp3_path = base_path.with_suffix(".mp3")
    except Exception as exc:
        raise MediaDownloadError(f"Falha ao baixar áudio: {exc}") from exc

    if not mp3_path.exists():
        raise MediaDownloadError(
            f"O download rodou mas o MP3 não apareceu em {mp3_path} "
            "(verifique se o ffmpeg está instalado e no PATH)."
        )
    return str(mp3_path)
