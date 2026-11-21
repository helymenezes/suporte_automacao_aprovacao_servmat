"""
Cliente da central (só leitura), no mesmo molde do fechamento-os: a central repassa GET /api/auvo/* e guarda a chave
do Auvo. Só rotas da allowlist, só GET, token no cabeçalho e nunca em log ou exceção.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

ROTAS = ("/api/auvo/tasks/",)

Transporte = Callable[[str, str, dict, bytes | None], tuple[int, bytes]]


class ErroCentral(Exception):
    pass


def redigir(texto: str) -> str:
    t = re.sub(r"(chave=)[^&\s\"']+", r"\1***", str(texto))
    t = re.sub(r"(?i)(authorization[\"'=:\s]+)(bearer\s+)?[^\s\"',&]+", r"\1***", t)
    t = re.sub(r"(?i)((?:token|apikey|api_key|password|senha)[\"'=:\s]+)[^\s\"',&]+", r"\1***", t)
    return t


def transporte_urllib(timeout: float = 90.0) -> Transporte:
    def enviar(metodo, url, cabecalhos, corpo):
        req = urllib.request.Request(url, data=corpo, headers=cabecalhos, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read() or b""
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErroCentral(redigir(f"falha de rede: {e}")) from None
    return enviar


@dataclass
class Listagem:
    tarefas: list[dict]
    completa: bool
    erro: str | None = None


class Central:
    def __init__(self, base: str, token: str, transporte: Transporte | None = None, page_size: int = 100):
        if not base.startswith(("https://", "http://127.0.0.1", "http://localhost", "http://central")):
            raise ValueError("central só por https ou rede interna")
        if not token:
            raise ValueError("SERVMAT_CENTRAL_TOKEN vazio")
        self.base = base.rstrip("/")
        self._auth = {"Authorization": f"Bearer {token}"}
        self._enviar = transporte or transporte_urllib()
        self.page_size = page_size

    def get(self, rota: str, params: dict | None = None):
        if rota not in ROTAS:
            raise ValueError(f"rota fora da allowlist: {rota}")
        url = self.base + rota + ("?" + urllib.parse.urlencode(params) if params else "")
        status, corpo = self._enviar("GET", url, {"Accept": "application/json", **self._auth}, None)
        if status == 404:
            return None
        if status != 200:
            raise ErroCentral(f"central respondeu {status} em {rota}")
        try:
            return json.loads(corpo)
        except ValueError:
            raise ErroCentral(f"resposta não é JSON em {rota}") from None

    @staticmethod
    def _entidades(resp) -> tuple[list[dict], int | None]:
        if resp is None:
            return [], 0
        if isinstance(resp, list):
            return resp, None
        r = resp.get("result", resp)
        if isinstance(r, list):
            return r, None
        lista = r.get("entityList") or r.get("entities") or []
        total = (r.get("pagedSearchReturnData") or {}).get("totalItems")
        return lista, total

    def listar_tarefas(self, inicio: datetime, fim: datetime, campos: str, max_paginas: int = 100) -> Listagem:
        filtro = {"startDate": inicio.strftime("%Y-%m-%dT%H:%M:%S"), "endDate": fim.strftime("%Y-%m-%dT%H:%M:%S")}
        tarefas: list[dict] = []
        for pagina in range(1, max_paginas + 1):
            try:
                resp = self.get("/api/auvo/tasks/", {"paramFilter": json.dumps(filtro), "page": pagina,
                                                     "pageSize": self.page_size, "order": "asc",
                                                     "selectfields": campos})
            except ErroCentral as e:
                return Listagem(tarefas, False, redigir(str(e)))
            lista, total = self._entidades(resp)
            tarefas.extend(lista)
            if not lista or len(lista) < self.page_size or (total is not None and len(tarefas) >= total):
                return Listagem(tarefas, True)
        return Listagem(tarefas, False, f"mais de {max_paginas} páginas")
