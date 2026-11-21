"""
python -m servmat servico                         sobe o painel + API (uvicorn)
python -m servmat seed-esboco [--forcar]           carrega as 11 OS do esboço (sem aprovação)
python -m servmat usuario --usuario hely --nome "Hely R Menezes" --admin   (senha: SERVMAT_SENHA ou pergunta)
python -m servmat usuario --usuario renato --nome "Renato Bonfim"
  Com hely e renato criados, nasce a rota padrão (Nível 1 Hely → Nível 2 Renato). Depois, mude na tela Níveis.
python -m servmat coleta                           uma coleta pela central (o mesmo que POST /run/coleta)
python -m servmat historico --desde 2026-02-01 [--ate 2026-11-21] [--clientes HGG,CAMIL]
  lê pela central as OS finalizadas do período para o agente montar o catálogo de uso (não entram na fila)
python -m servmat catalogo [--cliente HGG] [--aprovar N] [--saida arquivo.json]
  lista as propostas de catálogo do agente; --aprovar N passa a proposta N para o agente de identificação
python -m servmat ensaio [--forcar]                 as 11 OS do esboço como pendentes (sem itens), para testar a skill
python -m servmat ensaio --do-historico 10 [--cliente CAMIL]   OS do histórico como pendentes
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import getpass
import json
import os
import sys

from . import auth, banco, coleta, historico, seed
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
    u.add_argument("--admin", action="store_true", help="edita os níveis, pede ao orçamentista e registra o Pedido")
    u.add_argument("--desativar", action="store_true")
    sub.add_parser("coleta")
    h = sub.add_parser("historico")
    h.add_argument("--desde", required=True, help="AAAA-MM-DD")
    h.add_argument("--ate", help="AAAA-MM-DD (padrão: agora)")
    h.add_argument("--clientes", default="HGG,CAMIL")
    c = sub.add_parser("catalogo")
    c.add_argument("--cliente")
    c.add_argument("--aprovar", type=int)
    c.add_argument("--por", default="admin", help="quem aprova (fica na trilha)")
    c.add_argument("--saida")
    e = sub.add_parser("ensaio")
    e.add_argument("--forcar", action="store_true")
    e.add_argument("--do-historico", type=int, default=0)
    e.add_argument("--cliente")
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
            "INSERT INTO usuarios (usuario, nome, admin, senha_hash) VALUES (?,?,?,?) "
            "ON CONFLICT(usuario) DO UPDATE SET nome = excluded.nome, admin = excluded.admin, "
            "senha_hash = excluded.senha_hash, ativo = 1",
            (a.usuario.lower(), a.nome, int(a.admin), auth.hash_senha(senha)))
        banco.garantir_rota(conn)
        print(f"usuário {a.usuario.lower()} pronto{' (administrador)' if a.admin else ''}")
        return 0
    if a.cmd == "historico":
        desde = datetime.strptime(a.desde, "%Y-%m-%d")
        ate = datetime.strptime(a.ate, "%Y-%m-%d") + timedelta(days=1) if a.ate else None
        rel = historico.importar(conn, Central(cfg.central_url, cfg.central_token), cfg.coleta_cfg(), desde, ate,
                                 [x.strip() for x in a.clientes.split(",") if x.strip()])
        print(json.dumps(rel.dict(), ensure_ascii=False))
        return 0 if rel.completa else 2
    if a.cmd == "catalogo":
        if a.aprovar:
            print(json.dumps(historico.aprovar(conn, a.aprovar, a.por), ensure_ascii=False))
            return 0
        lista = historico.propostas(conn, a.cliente)
        if a.saida:
            with open(a.saida, "w", encoding="utf-8") as f:
                json.dump(lista, f, ensure_ascii=False, indent=2)
        for p in lista:
            print(f"#{p['id']} {p['cliente']} {p['situacao']} · {p['n_itens']} itens · {p['agente']} · {p['criado_em']}")
        return 0
    if a.cmd == "ensaio":
        if a.do_historico:
            lista = historico.ensaio(conn, a.cliente, a.do_historico)
            print(f"ensaio: {len(lista)} OS do histórico na fila como pendentes")
        else:
            print(f"ensaio: {seed.ensaio(conn, a.forcar)} OS do esboço na fila como pendentes")
        return 0
    if a.cmd == "coleta":
        rel = coleta.coletar(conn, Central(cfg.central_url, cfg.central_token), cfg.coleta_cfg())
        print(json.dumps(rel.dict(), ensure_ascii=False))
        return 0 if rel.completa else 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
