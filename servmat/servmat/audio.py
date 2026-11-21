"""
Áudio da avaliação no celular. O arquivo fica em dados/audios/ (fora do repositório e do JSON do painel).

Transcrição opcional por qualquer serviço compatível com POST /v1/audio/transcriptions (API da OpenAI, Groq ou um
servidor Whisper local, como o faster-whisper-server). Sem SERVMAT_TRANSCRICAO_URL, a pessoa escreve o texto.
A transcrição é sempre conferida e editável antes de ir para a observação da decisão.
"""
from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.request
from pathlib import Path

MIMES = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav",
         "audio/x-wav": "wav", "audio/aac": "aac"}
MAX_BYTES = 10 * 1024 * 1024


class ErroAudio(Exception):
    pass


def tipo_base(mime: str) -> str:
    return (mime or "").split(";")[0].strip().lower()


def salvar(pasta: Path, dados: bytes, mime: str) -> tuple[str, Path]:
    base = tipo_base(mime)
    if base not in MIMES:
        raise ErroAudio(f"Formato de áudio não aceito: {base or 'desconhecido'}.")
    if not dados:
        raise ErroAudio("Áudio vazio.")
    if len(dados) > MAX_BYTES:
        raise ErroAudio("Áudio maior que 10 MB.")
    pasta.mkdir(parents=True, exist_ok=True)
    ident = secrets.token_hex(16)
    caminho = pasta / f"{ident}.{MIMES[base]}"
    caminho.write_bytes(dados)
    return ident, caminho


def transcrever(url: str, chave: str, modelo: str, caminho: Path, mime: str, timeout: float = 120.0) -> str:
    """Envia o arquivo para um serviço de transcrição compatível com a API da OpenAI. Erro → texto vazio."""
    if not url:
        return ""
    fronteira = "----servmat" + secrets.token_hex(8)
    partes = []
    for nome, valor in (("model", modelo), ("language", "pt"), ("response_format", "json")):
        partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{valor}\r\n'.encode())
    partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="file"; filename="{caminho.name}"\r\n'
                  f"Content-Type: {tipo_base(mime)}\r\n\r\n".encode() + caminho.read_bytes() + b"\r\n")
    partes.append(f"--{fronteira}--\r\n".encode())
    cab = {"Content-Type": f"multipart/form-data; boundary={fronteira}"}
    if chave:
        cab["Authorization"] = f"Bearer {chave}"
    req = urllib.request.Request(url, data=b"".join(partes), headers=cab, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return str(json.loads(r.read()).get("text") or "").strip()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return ""
