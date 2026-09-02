"""Testes offline (sem rede, sem baixar nada de verdade) para
tools/media_downloader.py. yt-dlp é sempre mockado -- estes testes provam a
lógica de orquestração (URL vs. busca, extração do caminho final, erro
honesto), não a rede real.

Nota: tools/screen_vision.py NÃO foi construído -- core/actions/vision.py já
tem vision_screenshot/vision_ocr registrados e funcionando (mss/PIL/
pytesseract já instalados); um segundo módulo duplicaria a mesma coisa. Ver
backlog do projeto para a decisão completa.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from tools.media_downloader import MediaDownloadError, download_audio


class _FakeYoutubeDL:
    """Substitui yt_dlp.YoutubeDL sem tocar rede. `info` é o que
    extract_info devolveria; `touch_mp3` decide se o arquivo .mp3 final é
    criado de verdade (simulando o pós-processador FFmpeg rodando)."""

    def __init__(self, info: dict, touch_mp3: bool = True):
        self._info = info
        self._touch_mp3 = touch_mp3

    def __call__(self, options):
        self._options = options
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, source, download=True):
        self.source = source
        return self._info

    def prepare_filename(self, info):
        title = info["title"]
        path = Path(self._options["outtmpl"].replace("%(title)s.%(ext)s", f"{title}.webm"))
        if self._touch_mp3:
            mp3_path = path.with_suffix(".mp3")
            mp3_path.parent.mkdir(parents=True, exist_ok=True)
            mp3_path.write_bytes(b"fake-mp3-bytes")
        return str(path)


def test_download_audio_from_direct_url(tmp_path, monkeypatch):
    import tools.media_downloader as module

    fake = _FakeYoutubeDL({"title": "minha musica"})
    monkeypatch.setattr(module.yt_dlp, "YoutubeDL", fake)

    result = download_audio("https://example.com/watch?v=abc123", output_dir=str(tmp_path))

    assert result.endswith("minha musica.mp3")
    assert Path(result).exists()
    assert fake.source == "https://example.com/watch?v=abc123"


def test_download_audio_treats_plain_text_as_search(tmp_path, monkeypatch):
    import tools.media_downloader as module

    fake = _FakeYoutubeDL({"title": "resultado da busca"})
    monkeypatch.setattr(module.yt_dlp, "YoutubeDL", fake)

    download_audio("lofi hip hop radio", output_dir=str(tmp_path))

    assert fake.source == "ytsearch1:lofi hip hop radio"


def test_download_audio_unwraps_playlist_entries(tmp_path, monkeypatch):
    import tools.media_downloader as module

    fake = _FakeYoutubeDL({"entries": [{"title": "primeiro resultado"}]})
    monkeypatch.setattr(module.yt_dlp, "YoutubeDL", fake)

    result = download_audio("busca qualquer", output_dir=str(tmp_path))

    assert result.endswith("primeiro resultado.mp3")


def test_download_audio_empty_input_raises_without_touching_network(monkeypatch):
    import tools.media_downloader as module

    def fail_if_called(*args, **kwargs):
        raise AssertionError("não deveria chamar yt_dlp para entrada vazia")

    monkeypatch.setattr(module.yt_dlp, "YoutubeDL", fail_if_called)

    with pytest.raises(MediaDownloadError):
        download_audio("   ")


def test_download_audio_network_failure_becomes_honest_error(tmp_path, monkeypatch):
    import tools.media_downloader as module

    class _BoomYoutubeDL:
        def __call__(self, options):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, source, download=True):
            raise ConnectionError("sem rede")

    monkeypatch.setattr(module.yt_dlp, "YoutubeDL", _BoomYoutubeDL())

    with pytest.raises(MediaDownloadError, match="Falha ao baixar"):
        download_audio("https://example.com/x", output_dir=str(tmp_path))


def test_download_audio_missing_mp3_after_run_is_reported_not_hidden(tmp_path, monkeypatch):
    import tools.media_downloader as module

    fake = _FakeYoutubeDL({"title": "sem ffmpeg"}, touch_mp3=False)
    monkeypatch.setattr(module.yt_dlp, "YoutubeDL", fake)

    with pytest.raises(MediaDownloadError, match="ffmpeg"):
        download_audio("https://example.com/x", output_dir=str(tmp_path))
