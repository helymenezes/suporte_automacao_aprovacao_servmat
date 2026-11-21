"""
Catálogo de uso por cliente (HGG, CAMIL...), montado pelo agente a partir do histórico de OS.

1. `python -m servmat historico --desde 2026-02-01` lê pela central (só leitura) as OS finalizadas desde a data e
   guarda relato e "Utilizou peça" na tabela `historico`. Essas OS NÃO entram na fila de aprovação.
2. O agente do OpenClaw (skill `servmat-catalogo`) lê o histórico em páginas e envia uma proposta de catálogo:
   um item por linha, com nome padronizado, natureza, sinônimos, ocorrências, OS de exemplo e evidência.
3. O servidor confere cada evidência contra o relato das OS de exemplo (como na identificação) e guarda a proposta
   como rascunho. Só o administrador aprova (`python -m servmat catalogo --aprovar N`); a proposta aprovada passa a ir
   para o agente de identificação em `uso`, para ele padronizar os nomes.

O catálogo de uso NÃO decide "Contrato HGG": isso continua sendo o catálogo do contrato (config/catalogo.json).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import banco, coleta
from .agente import normalizar
from .central import Central

NATUREZAS = ("Peça", "Material", "Serviço")
MAX_ITENS = 400

ESQUEMA = """
CREATE TABLE IF NOT EXISTS historico (
  os           TEXT PRIMARY KEY,
  cliente      TEXT NOT NULL,
  data         TEXT NOT NULL DEFAULT '',
  tipo         TEXT NOT NULL DEFAULT '',
  equipamento  TEXT NOT NULL DEFAULT '',
  relato       TEXT NOT NULL DEFAULT '',
  utilizou     TEXT NOT NULL DEFAULT '',
  lido_em      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS historico_cliente ON historico (cliente, data, os);

CREATE TABLE IF NOT EXISTS catalogo_proposto (
  id           INTEGER PRIMARY KEY,
  cliente      TEXT NOT NULL,
  desde        TEXT NOT NULL DEFAULT '',
  itens        TEXT NOT NULL,
  n_itens      INTEGER NOT NULL,
  agente       TEXT NOT NULL,
  situacao     TEXT NOT NULL DEFAULT 'rascunho' CHECK (situacao IN ('rascunho', 'aprovado', 'substituido')),
  criado_em    TEXT NOT NULL,
  aprovado_por TEXT,
  aprovado_em  TEXT
);
"""


def criar(conn: sqlite3.Connection) -> None:
    conn.executescript(ESQUEMA)


class ErroProposta(Exception):
    def __init__(self, erros: list[str]):
        super().__init__("; ".join(erros))
        self.erros = erros


@dataclass
class RelatorioHistorico:
    gravadas: int = 0
    ignoradas: int = 0
    por_cliente: dict = field(default_factory=dict)
    completa: bool = True
    erros: list[str] = field(default_factory=list)

    def dict(self) -> dict:
        return self.__dict__.copy()


def janelas(desde: datetime, ate: datetime, dias: int = 15):
    """Períodos curtos: a listagem da central tem limite de páginas por consulta."""
    ini = desde
    while ini < ate:
        fim = min(ini + timedelta(days=dias), ate)
        yield ini, fim
        ini = fim


def importar(conn: sqlite3.Connection, central: Central, cfg: dict, desde: datetime, ate: datetime | None = None,
             clientes: list[str] | None = None) -> RelatorioHistorico:
    criar(conn)
    ate = ate or datetime.now()
    alvo = {c.upper() for c in clientes} if clientes else None
    rel = RelatorioHistorico()
    agora = banco.agora()
    for ini, fim in janelas(desde, ate):
        listagem = central.listar_tarefas(ini, fim, cfg["campos"])
        if not listagem.completa:
            rel.completa = False
            rel.erros.append(f"{ini:%d/%m/%Y}–{fim:%d/%m/%Y}: {listagem.erro or 'listagem incompleta'}")
        for t in listagem.tarefas:
            if "taskID" not in t:
                continue
            linha = coleta.mapear(t, cfg)
            if linha is None or (alvo and linha["cliente"] not in alvo) or not (linha["relato"] or linha["utilizou"]):
                rel.ignoradas += 1
                continue
            data = coleta.data_auvo(t.get("checkInDate") or t.get("taskDate"))
            conn.execute(
                "INSERT INTO historico (os, cliente, data, tipo, equipamento, relato, utilizou, lido_em) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(os) DO UPDATE SET cliente = excluded.cliente, "
                "data = excluded.data, tipo = excluded.tipo, equipamento = excluded.equipamento, "
                "relato = excluded.relato, utilizou = excluded.utilizou, lido_em = excluded.lido_em",
                (linha["os"], linha["cliente"], data.strftime("%Y-%m-%d") if data else "", linha["tipo"],
                 linha["equipamento"], linha["relato"], linha["utilizou"], agora))
            rel.gravadas += 1
            rel.por_cliente[linha["cliente"]] = rel.por_cliente.get(linha["cliente"], 0) + 1
    return rel


def pagina(conn: sqlite3.Connection, cliente: str, apos: str = "", limite: int = 40, desde: str = "") -> dict:
    """Página do histórico de um cliente, em ordem de OS. `apos` = última OS da página anterior."""
    criar(conn)
    cliente = cliente.upper()
    total = conn.execute("SELECT COUNT(*) FROM historico WHERE cliente = ? AND data >= ?",
                         (cliente, desde)).fetchone()[0]
    linhas = conn.execute(
        "SELECT os, data, tipo, equipamento, relato, utilizou FROM historico "
        "WHERE cliente = ? AND data >= ? AND os > ? ORDER BY os LIMIT ?",
        (cliente, desde, apos, limite)).fetchall()
    os_ = [dict(r) for r in linhas]
    return {"cliente": cliente, "total": total, "os": os_,
            "proximo": os_[-1]["os"] if len(os_) == limite else None}


def _lista_textos(v, nome: str, maximo: int, erros: list[str], pos: str) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        erros.append(f"{pos}: '{nome}' precisa ser lista de textos")
        return []
    v = [" ".join(x.split()) for x in v if x.strip()]
    if len(v) > maximo:
        erros.append(f"{pos}: '{nome}' com {len(v)} entradas (máximo {maximo})")
    return v[:maximo]


def validar(conn: sqlite3.Connection, payload: dict) -> tuple[str, str, list[dict]]:
    erros: list[str] = []
    cliente = str(payload.get("cliente") or "").upper()
    desde = str(payload.get("desde") or "")
    itens = payload.get("itens")
    if not cliente or not conn.execute("SELECT 1 FROM historico WHERE cliente = ? LIMIT 1", (cliente,)).fetchone():
        raise ErroProposta([f"cliente {cliente!r} sem histórico importado"])
    if not isinstance(itens, list) or not itens:
        raise ErroProposta(["'itens' precisa ser uma lista com pelo menos um item"])
    if len(itens) > MAX_ITENS:
        raise ErroProposta([f"{len(itens)} itens (máximo {MAX_ITENS})"])
    vistos: set[str] = set()
    saida: list[dict] = []
    for k, b in enumerate(itens, 1):
        pos = f"item {k}"
        if not isinstance(b, dict):
            erros.append(f"{pos}: precisa ser objeto")
            continue
        nome = " ".join(str(b.get("nome") or "").split())
        if not 2 <= len(nome) <= 120:
            erros.append(f"{pos}: 'nome' precisa ter de 2 a 120 caracteres")
        chave = normalizar(nome)
        if chave in vistos:
            erros.append(f"{pos}: '{nome}' repetido; junte os sinônimos num item só")
        vistos.add(chave)
        natureza = b.get("natureza")
        if natureza not in NATUREZAS:
            erros.append(f"{pos}: 'natureza' = {natureza!r}; use um de {list(NATUREZAS)}")
        sinonimos = _lista_textos(b.get("sinonimos"), "sinonimos", 15, erros, pos)
        exemplos = [str(x) for x in (b.get("os_exemplo") or []) if str(x).strip()]
        if not 1 <= len(exemplos) <= 5:
            erros.append(f"{pos}: 'os_exemplo' precisa de 1 a 5 OS do histórico")
        evid = " ".join(str(b.get("evidencia") or "").split())
        if len(normalizar(evid)) < 3:
            erros.append(f"{pos}: 'evidencia' vazia; copie o trecho do relato que cita o item")
        textos = conn.execute(
            f"SELECT os, relato, utilizou FROM historico WHERE cliente = ? AND os IN ({','.join('?' * len(exemplos))})",
            (cliente, *exemplos)).fetchall() if exemplos else []
        achadas = {r["os"] for r in textos}
        faltam = [x for x in exemplos if x not in achadas]
        if faltam:
            erros.append(f"{pos}: OS {', '.join(faltam)} não estão no histórico do {cliente}")
        if evid and textos and not any(normalizar(evid) in normalizar(f"{r['relato']} {r['utilizou']}") for r in textos):
            erros.append(f"{pos}: a evidência {evid[:60]!r} não está no relato de nenhuma OS de exemplo")
        ocorr = b.get("ocorrencias", len(exemplos))
        if not isinstance(ocorr, int) or ocorr < 1:
            erros.append(f"{pos}: 'ocorrencias' precisa ser inteiro ≥ 1")
        num = b.get("contrato_num")
        if num is not None and (cliente != "HGG" or not isinstance(num, int)):
            erros.append(f"{pos}: 'contrato_num' só para HGG, com o número do item do contrato")
        saida.append({"nome": nome, "natureza": natureza, "sinonimos": sinonimos, "ocorrencias": ocorr,
                      "os_exemplo": exemplos, "evidencia": evid, "contrato_num": num,
                      "obs": " ".join(str(b.get("obs") or "").split())[:200]})
    if erros:
        raise ErroProposta(erros)
    return cliente, desde, saida


def propor(conn: sqlite3.Connection, payload: dict, agente_nome: str) -> dict:
    criar(conn)
    cliente, desde, itens = validar(conn, payload)
    with banco.Transacao(conn):
        cur = conn.execute(
            "INSERT INTO catalogo_proposto (cliente, desde, itens, n_itens, agente, criado_em) VALUES (?,?,?,?,?,?)",
            (cliente, desde, json.dumps(itens, ensure_ascii=False), len(itens), agente_nome, banco.agora()))
        banco.evento(conn, "*", "catalogo_proposto", agente_nome, dados={"cliente": cliente, "itens": len(itens),
                                                                         "id": cur.lastrowid})
    return {"id": cur.lastrowid, "cliente": cliente, "itens": len(itens), "situacao": "rascunho"}


def propostas(conn: sqlite3.Connection, cliente: str | None = None) -> list[dict]:
    criar(conn)
    sql = "SELECT * FROM catalogo_proposto" + (" WHERE cliente = ?" if cliente else "") + " ORDER BY id DESC"
    return [dict(r, itens=json.loads(r["itens"])) for r in conn.execute(sql, (cliente.upper(),) if cliente else ())]


def aprovar(conn: sqlite3.Connection, proposta_id: int, quem: str) -> dict:
    criar(conn)
    with banco.Transacao(conn):
        p = conn.execute("SELECT * FROM catalogo_proposto WHERE id = ?", (proposta_id,)).fetchone()
        if p is None:
            raise KeyError(proposta_id)
        conn.execute("UPDATE catalogo_proposto SET situacao = 'substituido' WHERE cliente = ? AND situacao = 'aprovado'",
                     (p["cliente"],))
        conn.execute("UPDATE catalogo_proposto SET situacao = 'aprovado', aprovado_por = ?, aprovado_em = ? WHERE id = ?",
                     (quem, banco.agora(), proposta_id))
        banco.evento(conn, "*", "catalogo_aprovado", quem, dados={"cliente": p["cliente"], "id": proposta_id})
    return {"id": proposta_id, "cliente": p["cliente"], "situacao": "aprovado"}


def uso_aprovado(conn: sqlite3.Connection) -> dict:
    """Catálogo de uso aprovado de cada cliente, no formato que vai para o agente de identificação."""
    criar(conn)
    saida = {}
    for r in conn.execute("SELECT cliente, itens FROM catalogo_proposto WHERE situacao = 'aprovado'"):
        saida[r["cliente"]] = [{k: v for k, v in i.items() if k in ("nome", "natureza", "sinonimos", "contrato_num")}
                               for i in json.loads(r["itens"])]
    return saida


def ensaio(conn: sqlite3.Connection, cliente: str | None = None, n: int = 10) -> list[str]:
    """Copia OS do histórico para a fila como `pendente`, para testar a skill de identificação sem a coleta.
    Pula OS que já estão no painel. Devolve as OS copiadas."""
    from .agente import hash_relato
    criar(conn)
    sql = ("SELECT * FROM historico h WHERE NOT EXISTS (SELECT 1 FROM os WHERE os.os = h.os)"
           + (" AND cliente = ?" if cliente else "") + " AND relato != '' ORDER BY data DESC, os DESC LIMIT ?")
    linhas = conn.execute(sql, ((cliente.upper(),) if cliente else ()) + (n,)).fetchall()
    agora = banco.agora()
    with banco.Transacao(conn):
        for h in linhas:
            conn.execute(
                "INSERT INTO os (os, cliente, area, equipamento, tipo, relato, utilizou, relato_hash, prog_txt, "
                "prog_meta, coletada_em, atualizada_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (h["os"], h["cliente"], h["cliente"], h["equipamento"], h["tipo"], h["relato"], h["utilizou"],
                 hash_relato(h["relato"], h["utilizou"]), "Ensaio: OS copiada do histórico.",
                 f"Visita em {h['data'] or '—'} · ensaio", agora, agora))
            banco.evento(conn, h["os"], "ensaio", "ensaio", obs="OS do histórico posta na fila para testar o agente.")
    return [h["os"] for h in linhas]
