"""Configuração só por variáveis de ambiente (.env com permissão 600 na VPS). Nenhum segredo no repositório."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    banco: Path
    segredo: bytes
    agente_token: str
    run_token: str
    host: str
    porta: int
    web_dist: Path
    catalogo: Path
    coleta: Path
    central_url: str
    central_token: str
    cookie_seguro: bool

    def coleta_cfg(self) -> dict:
        with open(self.coleta, encoding="utf-8") as f:
            return json.load(f)


def carregar(env: dict | None = None) -> Config:
    e = os.environ if env is None else env
    segredo = e.get("SERVMAT_SEGREDO", "")
    if len(segredo) < 32:
        raise SystemExit("SERVMAT_SEGREDO precisa ter 32+ caracteres (gere com: python -c 'import secrets;print(secrets.token_urlsafe(48))')")
    return Config(
        banco=Path(e.get("SERVMAT_BANCO", RAIZ / "dados" / "servmat.sqlite")),
        segredo=segredo.encode(),
        agente_token=e.get("SERVMAT_AGENTE_TOKEN", ""),
        run_token=e.get("SERVMAT_RUN_TOKEN", ""),
        host=e.get("SERVMAT_HOST", "127.0.0.1"),
        porta=int(e.get("SERVMAT_PORTA", "8792")),
        web_dist=Path(e.get("SERVMAT_WEB", RAIZ.parent / "web" / "dist")),
        catalogo=Path(e.get("SERVMAT_CATALOGO", RAIZ / "config" / "catalogo.json")),
        coleta=Path(e.get("SERVMAT_COLETA_CFG", RAIZ / "config" / "coleta.json")),
        central_url=e.get("SERVMAT_CENTRAL_URL", ""),
        central_token=e.get("SERVMAT_CENTRAL_TOKEN", ""),
        cookie_seguro=e.get("SERVMAT_COOKIE_SEGURO", "1") == "1",
    )
