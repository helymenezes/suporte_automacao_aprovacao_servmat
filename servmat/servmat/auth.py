"""
Autenticação do painel (usuário e senha, sessão em cookie assinado) e dos robôs (token Bearer por função:
o agente do OpenClaw e as agendas /run). Nenhum token ou senha vai para log.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


def hash_senha(senha: str) -> str:
    if len(senha) < 10:
        raise ValueError("senha com menos de 10 caracteres")
    sal = os.urandom(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, **_SCRYPT)
    return f"scrypt${sal.hex()}${h.hex()}"


def conferir_senha(senha: str, guardado: str) -> bool:
    try:
        alg, sal, h = guardado.split("$")
    except ValueError:
        return False
    if alg != "scrypt":
        return False
    calc = hashlib.scrypt(senha.encode(), salt=bytes.fromhex(sal), **_SCRYPT)
    return hmac.compare_digest(calc.hex(), h)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def emitir_sessao(usuario: str, segredo: bytes, ttl_s: int = 12 * 3600, agora: float | None = None) -> str:
    exp = int((agora or time.time()) + ttl_s)
    corpo = f"{_b64(usuario.encode())}.{exp}"
    sig = hmac.new(segredo, corpo.encode(), hashlib.sha256).digest()
    return f"{corpo}.{_b64(sig)}"


def ler_sessao(token: str | None, segredo: bytes, agora: float | None = None) -> str | None:
    if not token or token.count(".") != 2:
        return None
    u, exp, sig = token.split(".")
    esperado = hmac.new(segredo, f"{u}.{exp}".encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(_unb64(sig), esperado):
            return None
        if int(exp) < (agora or time.time()):
            return None
        return _unb64(u).decode()
    except (ValueError, UnicodeDecodeError):
        return None


def token_ok(cabecalho: str | None, esperado: str) -> bool:
    """`Authorization: Bearer <token>`. Token vazio na configuração = rota desligada."""
    if not esperado or len(esperado) < 24 or not cabecalho or not cabecalho.startswith("Bearer "):
        return False
    return hmac.compare_digest(cabecalho[7:].encode(), esperado.encode())


class Freio:
    """Até 5 senhas erradas por usuário em 10 min; depois, 10 min de espera. Em memória (um processo só)."""

    def __init__(self, limite: int = 5, janela_s: int = 600):
        self.limite, self.janela = limite, janela_s
        self._erros: dict[str, list[float]] = {}

    def bloqueado(self, usuario: str, agora: float | None = None) -> bool:
        t = agora or time.time()
        recentes = [x for x in self._erros.get(usuario, []) if t - x < self.janela]
        self._erros[usuario] = recentes
        return len(recentes) >= self.limite

    def errou(self, usuario: str, agora: float | None = None) -> None:
        self._erros.setdefault(usuario, []).append(agora or time.time())

    def acertou(self, usuario: str) -> None:
        self._erros.pop(usuario, None)
