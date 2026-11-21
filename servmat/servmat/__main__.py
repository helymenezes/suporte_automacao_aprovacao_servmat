"""
python -m servmat servico                         sobe o painel + API (uvicorn)
python -m servmat seed-esboco [--forcar]           carrega as 11 OS do esboço (sem aprovação)
python -m servmat usuario --usuario hely --nome "Hely R Menezes" --nivel 1   (senha: SERVMAT_SENHA ou pergunta)
python -m servmat coleta                           uma coleta pela central (o mesmo que POST /run/coleta)
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from . import auth, banco, coleta, seed
from .central import Central
from .config import carregar


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="servmat")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("servico")
    s = sub.add_parser("seed-esboco")
    s.add_argument("--forcar", action="store_true")
    u = sub.add_parser("usuario")
    u.add_argument("--usuario", required=True)
    u.add_argument("--nome", required=True)
    u.add_argument("--nivel", type=int, choices=(1, 2), required=True)
    u.add_argument("--desativar", action="store_true")
    sub.add_parser("coleta")
    a = p.parse_args(argv)

    cfg = carregar()
    conn = banco.conectar(cfg.banco)
    banco.criar(conn)

    if a.cmd == "servico":
        import uvicorn
        from .api import criar_app
        conn.close()
        uvicorn.run(criar_app(cfg), host=cfg.host, port=cfg.porta, log_level="info", proxy_headers=False,
                    server_header=False)
        return 0
    if a.cmd == "seed-esboco":
        n = seed.carregar(conn, a.forcar)
        print(f"esboço carregado: {n} itens")
        return 0
    if a.cmd == "usuario":
        if a.desativar:
            conn.execute("UPDATE usuarios SET ativo = 0 WHERE usuario = ?", (a.usuario,))
            print("desativado")
            return 0
        senha = os.environ.get("SERVMAT_SENHA") or getpass.getpass("Senha (10+ caracteres): ")
        conn.execute(
            "INSERT INTO usuarios (usuario, nome, nivel, senha_hash) VALUES (?,?,?,?) "
            "ON CONFLICT(usuario) DO UPDATE SET nome = excluded.nome, nivel = excluded.nivel, "
            "senha_hash = excluded.senha_hash, ativo = 1",
            (a.usuario.lower(), a.nome, a.nivel, auth.hash_senha(senha)))
        print(f"usuário {a.usuario.lower()} pronto (Nível {a.nivel})")
        return 0
    if a.cmd == "coleta":
        rel = coleta.coletar(conn, Central(cfg.central_url, cfg.central_token), cfg.coleta_cfg())
        print(json.dumps(rel.dict(), ensure_ascii=False))
        return 0 if rel.completa else 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
