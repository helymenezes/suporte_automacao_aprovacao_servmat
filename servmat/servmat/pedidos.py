"""
Acompanhamento do Pedido: do fim dos níveis internos até a cobrança.

Uma linha por OS e rota: `compra` (Pedido de compra e A definir) e `contrato` (Contrato HGG). Fontes:
- Pedido, vínculo com a OS, NF, Celso e execução: sistema comercial (`POST /api/integracao/comercial`);
- aceite do cliente: planilha do cliente (`POST /api/integracao/planilha`);
- registro manual do PCM no painel, enquanto as integrações não existem (fica na trilha com o nome de quem registrou);
- solicitação e cobrança: fila de envios ao orçamentista (envio.py).
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from . import banco, regras

GRUPOS = (
    ("class", "Aguardando classificação"),
    ("solicitar", "A solicitar ao orçamentista"),
    ("vinc", "Vínculo a conferir"),
    ("cli", "Aguardando cliente ou Celso"),
    ("exec", "Em execução"),
    ("cob", "A solicitar cobrança"),
    ("cobs", "Cobrança solicitada"),
)
CAMPOS = {
    "comercial": {"pedido_num", "vinculo", "nf", "celso", "execucao", "execucao_meta"},
    "planilha": {"aceite", "aceite_obs"},
}
VALORES = {
    "vinculo": ("", "a_conferir", "vinculado", "nao_localizado"),
    "aceite": ("", "aguardando", "aceito", "parcial", "recusado"),
    "celso": ("", "aguardando", "autorizado", "devolvido", "reprovado"),
    "execucao": ("", "a_agendar", "agendada", "concluida"),
}
SAIU = ("ENVIADO", "SIMULADO")


class ErroPedido(Exception):
    pass


def tipo_de(cls: str) -> str:
    return "contrato" if cls == regras.CONTRATO else "compra"


def _limpar(campos: dict, permitidos: set[str]) -> dict:
    saida = {}
    for k, v in campos.items():
        if k not in permitidos:
            raise ErroPedido(f"Campo '{k}' não vem desta fonte.")
        v = "" if v is None else " ".join(str(v).split())
        if k in VALORES and v not in VALORES[k]:
            raise ErroPedido(f"'{k}' = {v!r}; use um de {list(VALORES[k])}.")
        if len(v) > 120:
            raise ErroPedido(f"'{k}' com mais de 120 caracteres.")
        saida[k] = v
    return saida


def gravar(conn: sqlite3.Connection, os_num: str, tipo: str, campos: dict, fonte: str, quem: str) -> None:
    """Grava campos de uma linha (chamar dentro de Transacao). Só cria linha para OS existente."""
    if tipo not in ("compra", "contrato"):
        raise ErroPedido("tipo deve ser 'compra' ou 'contrato'.")
    if conn.execute("SELECT 1 FROM os WHERE os = ?", (os_num,)).fetchone() is None:
        raise ErroPedido(f"OS {os_num} não está no painel.")
    agora = banco.agora()
    conn.execute("INSERT OR IGNORE INTO pedidos (os, tipo, atualizado_em) VALUES (?,?,?)", (os_num, tipo, agora))
    antes = dict(conn.execute("SELECT * FROM pedidos WHERE os = ? AND tipo = ?", (os_num, tipo)).fetchone())
    mudou = {k: v for k, v in campos.items() if antes.get(k) != v}
    if not mudou:
        return
    sets = ", ".join(f"{k} = ?" for k in mudou)
    conn.execute(f"UPDATE pedidos SET {sets}, fonte = ?, atualizado_em = ? WHERE os = ? AND tipo = ?",
                 (*mudou.values(), fonte, agora, os_num, tipo))
    banco.evento(conn, os_num, "pedido_atualizado", quem, dados={"tipo": tipo, "fonte": fonte, "campos": mudou})


def importar(conn: sqlite3.Connection, fonte: str, registros: list[dict], quem: str) -> dict:
    """Entrada das integrações (só leitura do lado delas). Registro com erro é pulado e relatado."""
    if fonte not in CAMPOS:
        raise ErroPedido("fonte desconhecida")
    if not isinstance(registros, list) or len(registros) > 2000:
        raise ErroPedido("'registros' precisa ser uma lista com até 2000 linhas")
    ok, erros = 0, []
    for k, r in enumerate(registros, 1):
        try:
            if not isinstance(r, dict):
                raise ErroPedido("linha precisa ser objeto")
            os_num, tipo = str(r.get("os") or ""), str(r.get("tipo") or "")
            campos = _limpar({x: y for x, y in r.items() if x not in ("os", "tipo")}, CAMPOS[fonte])
            with banco.Transacao(conn):
                gravar(conn, os_num, tipo, campos, fonte, quem)
            ok += 1
        except ErroPedido as e:
            erros.append(f"linha {k}: {e}")
    conn.execute("INSERT INTO integracoes (nome, ultima_em, resumo) VALUES (?,?,?) ON CONFLICT(nome) DO UPDATE "
                 "SET ultima_em = excluded.ultima_em, resumo = excluded.resumo",
                 (fonte, banco.agora(), f"{ok} gravadas, {len(erros)} com erro"))
    return {"gravadas": ok, "erros": erros[:50]}


def registrar_manual(conn: sqlite3.Connection, os_num: str, tipo: str, campos: dict, quem: str) -> None:
    permitidos = CAMPOS["comercial"] | CAMPOS["planilha"]
    limpos = _limpar(campos, permitidos)
    with banco.Transacao(conn):
        gravar(conn, os_num, tipo, limpos, f"manual:{quem}", quem)


def _ultimo_envio(envios: list[sqlite3.Row], acao: str) -> dict | None:
    lista = [e for e in envios if e["acao"] == acao]
    if not lista:
        return None
    e = max(lista, key=lambda x: x["id"])
    return {"id": e["id"], "estado": e["estado"], "recibo": e["recibo"], "motivo": e["motivo"],
            "em": e["atualizado_em"], "destino": e["destino"]}


def situacao(itens: list[dict], p: dict, solic: dict | None, cob: dict | None, tipo: str) -> dict:
    """Grupo da linha e o que pode ser feito nela agora."""
    vivos = [i for i in itens if i["fase"] != "reprovado"]
    aguardando = any(i["fase"] in ("relatorio", "nivel") for i in vivos)
    todos_aplicados = bool(vivos) and all(i["situacao"] == "Aplicado" for i in vivos)
    execucao = "concluida" if todos_aplicados else (p.get("execucao") or "a_agendar")
    solic_ok = bool(solic and solic["estado"] in SAIU)
    cob_ok = bool(cob and cob["estado"] in SAIU)
    vinculado = p.get("vinculo") == "vinculado"
    liberado = (p.get("celso") == "autorizado") if tipo == "contrato" else (p.get("aceite") in ("aceito", "parcial"))
    if aguardando:
        grupo = "vinc" if todos_aplicados else "class"
    elif not solic_ok and not vinculado:
        grupo = "solicitar"
    elif not vinculado:
        grupo = "vinc"
    elif not liberado:
        grupo = "cli"
    elif execucao != "concluida":
        grupo = "exec"
    elif tipo == "compra" and not cob_ok:
        grupo = "cob"
    else:
        grupo = "cobs"
    incerto = [e for e in (solic, cob) if e and e["estado"] == "INCERTO"]
    return {
        "grupo": grupo, "execucao": execucao, "todos_aplicados": todos_aplicados, "aguardando": aguardando,
        "pode_solicitar": not aguardando and not solic_ok and not vinculado and not (solic and solic["estado"] in ("INCERTO", "PENDENTE")),
        "pode_cobrar": tipo == "compra" and grupo == "cob" and not (cob and cob["estado"] in ("INCERTO", "PENDENTE")),
        "incertos": [e["id"] for e in incerto],
    }


def montar(conn: sqlite3.Connection) -> dict:
    itens_por: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM itens WHERE fase != 'reprovado' AND natureza != 'Não identificado' ORDER BY id"):
        itens_por[(r["os"], tipo_de(r["cls"]))].append(dict(r))
    oss = {r["os"]: r for r in conn.execute("SELECT * FROM os")}
    peds = {(r["os"], r["tipo"]): dict(r) for r in conn.execute("SELECT * FROM pedidos")}
    envs: dict[tuple[str, str], list] = defaultdict(list)
    for e in conn.execute("SELECT * FROM envios"):
        envs[(e["os"], e["tipo"])].append(e)
    linhas = []
    for (os_num, tipo), its in sorted(itens_por.items()):
        o = oss.get(os_num)
        if o is None:
            continue
        p = peds.get((os_num, tipo), {})
        solic = _ultimo_envio(envs[(os_num, tipo)], "solicitacao")
        cob = _ultimo_envio(envs[(os_num, tipo)], "cobranca")
        s = situacao(its, p, solic, cob, tipo)
        linhas.append({
            "os": os_num, "tipo": tipo, "cliente": o["cliente"], "equipamento": o["equipamento"], "area": o["area"],
            "itens": [{"id": i["id"], "item": i["item"], "qtd": i["qtd"], "presumida": bool(i["presumida"]),
                       "situacao": i["situacao"], "fase": i["fase"],
                       "fase_nome": regras.nome_fase(i["fase"], i["nivel_pos"])} for i in its],
            "pedido_num": p.get("pedido_num", ""), "vinculo": p.get("vinculo", ""), "aceite": p.get("aceite", ""),
            "aceite_obs": p.get("aceite_obs", ""), "celso": p.get("celso", ""), "execucao_meta": p.get("execucao_meta", ""),
            "nf": p.get("nf", ""), "fonte": p.get("fonte", ""), "solicitacao": solic, "cobranca": cob, **s,
        })
    contagem: dict[str, int] = defaultdict(int)
    for l in linhas:
        contagem[l["grupo"]] += 1
    integ = {r["nome"]: {"ultima_em": r["ultima_em"], "resumo": r["resumo"]} for r in conn.execute("SELECT * FROM integracoes")}
    return {
        "gerado_em": banco.agora(),
        "grupos": [{"chave": k, "nome": n, "qtd": contagem.get(k, 0)} for k, n in GRUPOS],
        "integracoes": {"comercial": integ.get("comercial"), "planilha": integ.get("planilha")},
        "linhas": linhas,
    }


def situacao_para_etapas(conn: sqlite3.Connection, os_num: str) -> dict:
    """Resumo do Pedido da OS para as etapas do acompanhamento (junta as duas rotas, a mais atrasada manda)."""
    peds = [dict(r) for r in conn.execute("SELECT * FROM pedidos WHERE os = ?", (os_num,))]
    envs = conn.execute("SELECT * FROM envios WHERE os = ?", (os_num,)).fetchall()
    sol = [e["estado"] for e in envs if e["acao"] == "solicitacao"]
    cob = [e["estado"] for e in envs if e["acao"] == "cobranca"]
    def todos(lista, campo, alvo):
        return bool(lista) and all(x.get(campo) == alvo for x in lista)
    return {
        "solicitacao": "ENVIADO" if sol and all(s in SAIU for s in sol) else "",
        "cobranca": "ENVIADO" if cob and all(s in SAIU for s in cob) else "",
        "vinculo": "vinculado" if todos(peds, "vinculo", "vinculado") else "",
        "pedido_num": ", ".join(p["pedido_num"] for p in peds if p.get("pedido_num")),
        "aceite": next((p["aceite"] for p in peds if p["tipo"] == "compra"), ""),
        "celso": next((p["celso"] for p in peds if p["tipo"] == "contrato"), ""),
        "execucao": "concluida" if todos(peds, "execucao", "concluida") else
                    ("agendada" if any(p.get("execucao") in ("agendada", "concluida") for p in peds) else ""),
    }
