"""
Coleta (sem IA): lê pela central as OS finalizadas dos últimos dias e grava o relato de cada uma.
OS nova ou com relato mudado fica `pendente` para o agente do OpenClaw identificar.

Os nomes de campo do Auvo (relato, pergunta "Utilizou peça", nome do equipamento) estão em config/coleta.json
porque precisam ser conferidos na central antes do primeiro uso (ver docs/ARQUITETURA.md, pendência P-01).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import agente, banco
from .central import Central

STATUS_FINALIZADA = 5


@dataclass
class Relatorio:
    novas: int = 0
    reabertas: int = 0
    alertas: int = 0
    iguais: int = 0
    ignoradas: int = 0
    completa: bool = True
    erro: str | None = None
    os_novas: list[str] = field(default_factory=list)

    def dict(self) -> dict:
        return self.__dict__.copy()


def data_auvo(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "")[:19])
    except ValueError:
        return None


def _dm(d: datetime | None) -> str:
    return d.strftime("%d/%m %H:%M") if d else "—"


def cliente_de(descricao: str, regras_cli: dict[str, list[str]]) -> str | None:
    d = (descricao or "").upper()
    for cliente, marcas in regras_cli.items():
        if any(m.upper() in d for m in marcas):
            return cliente
    return None


def resposta_utilizou(t: dict, pergunta: str) -> str:
    alvo = agente.normalizar(pergunta)
    for q in t.get("questionnaires") or []:
        for r in (q.get("answers") or q.get("questions") or []) if isinstance(q, dict) else []:
            if not isinstance(r, dict):
                continue
            texto = r.get("questionDescription") or r.get("description") or ""
            if alvo and alvo in agente.normalizar(str(texto)):
                return str(r.get("reply") or r.get("answer") or "").strip()
    return ""


def mapear(t: dict, cfg: dict) -> dict | None:
    """Uma tarefa do Auvo → linha da tabela os. None = fora (outro cliente ou não finalizada)."""
    status = t.get("taskStatus")
    finalizada = status == STATUS_FINALIZADA if status is not None else bool(t.get("finished"))
    if not finalizada:
        return None
    cliente = cliente_de(str(t.get("customerDescription") or ""), cfg["clientes"])
    if cliente is None:
        return None
    relato = " ".join(str(t.get(cfg.get("campo_relato", "report")) or "").split())
    utilizou = resposta_utilizou(t, cfg.get("pergunta_utilizou", "utilizou peça"))
    tipos = {str(k): v for k, v in (cfg.get("tipos") or {}).items()}
    tipo = tipos.get(str(t.get("taskType")), str(t.get("taskTypeDescription") or ""))
    tecnico = str(t.get("userToName") or "")
    task_date, check_in = data_auvo(t.get("taskDate")), data_auvo(t.get("checkInDate") or t.get("checkOutDate"))
    return {
        "os": str(t["taskID"]), "cliente": cliente, "area": str(t.get("customerDescription") or ""),
        "equipamento": str(t.get(cfg.get("campo_equipamento", "equipmentName")) or ""),
        "tipo": tipo, "tecnico": tecnico, "relato": relato, "utilizou": utilizou,
        "relato_hash": agente.hash_relato(relato, utilizou),
        "prog_txt": f"Aberta em {_dm(task_date)}.",
        "prog_meta": f"Visita em {_dm(check_in)} · {tecnico or 'técnico não informado'} · Auvo",
        "task_url": str(t.get("taskUrl") or ""),
    }


def gravar(conn: sqlite3.Connection, linha: dict, rel: Relatorio) -> None:
    agora = banco.agora()
    with banco.Transacao(conn):
        o = conn.execute("SELECT * FROM os WHERE os = ?", (linha["os"],)).fetchone()
        if o is None:
            conn.execute(
                "INSERT INTO os (os, cliente, area, equipamento, tipo, tecnico, relato, utilizou, relato_hash, "
                "prog_txt, prog_meta, task_url, coletada_em, atualizada_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (linha["os"], linha["cliente"], linha["area"], linha["equipamento"], linha["tipo"], linha["tecnico"],
                 linha["relato"], linha["utilizou"], linha["relato_hash"], linha["prog_txt"], linha["prog_meta"],
                 linha["task_url"], agora, agora))
            banco.evento(conn, linha["os"], "coletada", "coleta")
            rel.novas += 1
            rel.os_novas.append(linha["os"])
            return
        if o["relato_hash"] == linha["relato_hash"]:
            conn.execute("UPDATE os SET task_url = ?, tecnico = ?, area = ? WHERE os = ?",
                         (linha["task_url"] or o["task_url"], linha["tecnico"], linha["area"], linha["os"]))
            rel.iguais += 1
            return
        decididos = conn.execute(
            "SELECT COUNT(*) FROM itens WHERE os = ? AND (fase NOT IN ('relatorio', 'n1') OR versao > 1)",
            (linha["os"],)).fetchone()[0]
        conn.execute("UPDATE os SET relato = ?, utilizou = ?, relato_hash = ?, task_url = ?, atualizada_em = ? "
                     "WHERE os = ?", (linha["relato"], linha["utilizou"], linha["relato_hash"],
                                      linha["task_url"] or o["task_url"], agora, linha["os"]))
        if decididos:
            # Já há decisão humana: não apaga nada. O Hely vê o alerta na trilha da OS.
            banco.evento(conn, linha["os"], "relato_mudou_apos_decisao", "coleta",
                         obs="O relato mudou no Auvo depois de uma decisão. Conferir os itens.")
            rel.alertas += 1
            return
        conn.execute("DELETE FROM itens WHERE os = ?", (linha["os"],))
        conn.execute("UPDATE os SET identificacao = 'pendente', rodada = rodada + 1 WHERE os = ?", (linha["os"],))
        banco.evento(conn, linha["os"], "relato_mudou", "coleta", obs="Relato corrigido no Auvo: nova identificação.")
        rel.reabertas += 1


def coletar(conn: sqlite3.Connection, central: Central, cfg: dict, agora: datetime | None = None) -> Relatorio:
    agora = agora or datetime.now()
    inicio = agora - timedelta(days=int(cfg.get("dias", 15)))
    listagem = central.listar_tarefas(inicio, agora, cfg["campos"])
    rel = Relatorio(completa=listagem.completa, erro=listagem.erro)
    vistos: set[str] = set()
    for t in listagem.tarefas:
        if "taskID" not in t or str(t["taskID"]) in vistos:
            continue
        vistos.add(str(t["taskID"]))
        linha = mapear(t, cfg)
        if linha is None:
            rel.ignoradas += 1
            continue
        gravar(conn, linha, rel)
    return rel
