"""
Entrada do agente de IA (OpenClaw, VPS02). O agente LÊ o relatório da OS e SUGERE os materiais, peças e serviços.
Ele nunca aprova, nunca muda fase além de colocar o item no Nível 1 e nunca toca em item que um humano já decidiu.

Proteções contra sugestão inventada:
- toda sugestão traz `evidencia`, um trecho que precisa existir no relato (ou no campo "Utilizou peça") da OS;
- `relato_hash` precisa ser o do relato atual (o relato mudou → o agente pede os pendentes de novo);
- "Contrato HGG" só para cliente HGG e só com o número do item do catálogo;
- a mesma OS/relato/rodada só é aceita uma vez (repetição devolve o mesmo resultado, sem duplicar).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata

from . import banco, regras

MAX_ITENS = 30


class ErroIdentificacao(Exception):
    def __init__(self, erros: list[str]):
        super().__init__("; ".join(erros))
        self.erros = erros


class Conflito(Exception):
    pass


def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[^0-9a-z]+", " ", t).split())


def hash_relato(relato: str, utilizou: str) -> str:
    return hashlib.sha256(f"{relato}\n--\n{utilizou}".encode()).hexdigest()


def _texto(v, nome: str, minimo: int, maximo: int, erros: list[str], pos: str) -> str:
    if not isinstance(v, str):
        erros.append(f"{pos}: '{nome}' precisa ser texto")
        return ""
    v = " ".join(v.split())
    if not minimo <= len(v) <= maximo:
        erros.append(f"{pos}: '{nome}' com {len(v)} caracteres (aceito de {minimo} a {maximo})")
    return v


def _enum(v, nome: str, opcoes, erros: list[str], pos: str) -> str:
    if v not in opcoes:
        erros.append(f"{pos}: '{nome}' = {v!r}; use um de {list(opcoes)}")
        return ""
    return v


def texto_contrato(num, obs: str, catalogo: dict, cliente: str, erros: list[str], pos: str) -> str:
    itens = {str(k): v for k, v in (catalogo.get(cliente, {}).get("itens") or {}).items()}
    incompleto = bool(catalogo.get(cliente, {}).get("_incompleto"))
    if num is None or not str(num).isdigit():
        erros.append(f"{pos}: 'Contrato HGG' exige 'contrato_num' (número do item no catálogo)")
        return ""
    desc = itens.get(str(int(num)))
    if desc:
        base = f"Item do contrato: {int(num)} · {desc}"
    elif incompleto:
        base = f"Item do contrato: {int(num)} (fora do catálogo carregado: conferir)"
    else:
        erros.append(f"{pos}: item {num} não existe no catálogo do contrato {cliente}")
        return ""
    return f"{base}. {obs}" if obs else base


def validar(payload: dict, os_row: sqlite3.Row, catalogo: dict, contrato_ligado: bool = True) -> tuple[list[dict], bool, str]:
    """Devolve (itens limpos, sem_informacao, motivo). Erro de qualquer item recusa a identificação inteira."""
    erros: list[str] = []
    sem_info = bool(payload.get("sem_informacao"))
    # sem_itens: o relato descreve o serviço, mas não há nada a comprar nem a lançar (ex.: PMOC de rotina com
    # limpeza e produto bactericida). A OS fica identificada, sem itens, e sai da fila de aprovação.
    sem_itens = bool(payload.get("sem_itens"))
    motivo = _texto(payload.get("motivo", ""), "motivo", 0, 300, erros, "OS")
    brutos = payload.get("itens")
    if not isinstance(brutos, list):
        raise ErroIdentificacao(["'itens' precisa ser uma lista (vazia quando sem_informacao ou sem_itens)"])
    if sem_info and sem_itens:
        raise ErroIdentificacao(["use só um: sem_informacao (relato não descreve o serviço) ou sem_itens (nada a comprar)"])
    if sem_info:
        if brutos:
            erros.append("com sem_informacao = true, 'itens' deve vir vazio")
        if not motivo:
            erros.append("com sem_informacao = true, explique em 'motivo' (ex.: 'lista só na foto anexada')")
        if erros:
            raise ErroIdentificacao(erros)
        return [], True, motivo
    if sem_itens:
        if brutos:
            erros.append("com sem_itens = true, 'itens' deve vir vazio")
        if not motivo:
            erros.append("com sem_itens = true, explique em 'motivo' (ex.: 'PMOC de rotina: limpeza e bactericida')")
        if erros:
            raise ErroIdentificacao(erros)
        return [], False, motivo
    if not brutos:
        raise ErroIdentificacao(["nenhum item: use sem_itens = true (serviço sem nada a comprar) ou sem_informacao = true "
                                 "(relato não descreve o serviço), sempre com 'motivo'"])
    if len(brutos) > MAX_ITENS:
        raise ErroIdentificacao([f"mais de {MAX_ITENS} itens numa OS"])

    fonte = normalizar(os_row["relato"]) + " | " + normalizar(os_row["utilizou"])
    utilizou_nao = normalizar(os_row["utilizou"]) in ("nao", "n")
    limpos = []
    for k, b in enumerate(brutos, 1):
        pos = f"item {k}"
        if not isinstance(b, dict):
            erros.append(f"{pos}: precisa ser objeto")
            continue
        it = {
            "item": _texto(b.get("item"), "item", 2, 160, erros, pos),
            "natureza": _enum(b.get("natureza"), "natureza", regras.NATUREZAS[:3], erros, pos),
            "situacao": _enum(b.get("situacao"), "situacao", regras.SITUACOES, erros, pos),
            "qtd": _texto(b.get("qtd", "não informada"), "qtd", 1, 30, erros, pos),
            "presumida": 1 if b.get("presumida") else 0,
            "cls": _enum(b.get("cls"), "cls", regras.CLASSIFICACOES, erros, pos),
            "conf": _enum(b.get("conf"), "conf", regras.CONFIANCAS, erros, pos),
            "evidencia": _texto(b.get("evidencia"), "evidencia", 3, 400, erros, pos),
            "val_ok": 1 if b.get("val_ok", True) else 0,
            "val_txt": _texto(b.get("val_txt", ""), "val_txt", 0, 200, erros, pos),
        }
        obs_contrato = _texto(b.get("contrato_obs", ""), "contrato_obs", 0, 300, erros, pos)
        if it["evidencia"] and normalizar(it["evidencia"]) not in fonte:
            erros.append(f"{pos}: a evidência não está no relato nem no campo 'Utilizou peça'. Copie o trecho exato.")
        if it["cls"] == regras.CONTRATO:
            if os_row["cliente"] != "HGG":
                erros.append(f"{pos}: 'Contrato HGG' só vale para OS do HGG (esta é {os_row['cliente']})")
            elif not contrato_ligado:
                erros.append(f"{pos}: o critério de contrato do {os_row['cliente']} está desligado; use 'Pedido de compra' ou 'A definir'")
            else:
                it["contrato_item"] = texto_contrato(b.get("contrato_num"), obs_contrato, catalogo, "HGG", erros, pos)
        else:
            it["contrato_item"] = obs_contrato
        if it["situacao"] == "Aplicado" and utilizou_nao and it["val_ok"]:
            # Regra das rotinas: campo "Nao" com relato de troca é divergência, nunca "coerente".
            it["val_ok"] = 0
            it["val_txt"] = 'Divergência: o campo diz "Nao", mas o relato descreve troca' + (
                f" ({it['val_txt']})" if it["val_txt"] else "")
        limpos.append(it)
    if erros:
        raise ErroIdentificacao(erros)
    return limpos, False, motivo


def pendentes(conn: sqlite3.Connection, limite: int = 10) -> list[dict]:
    linhas = conn.execute(
        "SELECT * FROM os WHERE identificacao = 'pendente' ORDER BY coletada_em LIMIT ?", (limite,)).fetchall()
    saida = []
    for o in linhas:
        devolucoes = [r["obs"] for r in conn.execute(
            "SELECT obs FROM eventos WHERE os = ? AND tipo = 'decisao' "
            "AND json_extract(dados, '$.rodada_nova') = ? ORDER BY id", (o["os"], o["rodada"]))]
        ja = [dict(item=r["item"], natureza=r["natureza"], qtd=r["qtd"], fase=r["fase"]) for r in conn.execute(
            "SELECT item, natureza, qtd, fase FROM itens WHERE os = ? AND fase != 'relatorio' ORDER BY id", (o["os"],))]
        saida.append({
            "os": o["os"], "cliente": o["cliente"], "area": o["area"], "equipamento": o["equipamento"],
            "tipo": o["tipo"], "tecnico": o["tecnico"], "relato": o["relato"], "utilizou": o["utilizou"],
            "relato_hash": o["relato_hash"], "rodada": o["rodada"],
            "devolucoes_do_nivel_1": devolucoes, "ja_registrados": ja,
        })
    return saida


def aplicar(conn: sqlite3.Connection, payload: dict, agente_nome: str, catalogo: dict) -> dict:
    os_num = str(payload.get("os") or "")
    with banco.Transacao(conn):
        o = conn.execute("SELECT * FROM os WHERE os = ?", (os_num,)).fetchone()
        if o is None:
            raise KeyError(os_num)
        if payload.get("relato_hash") != o["relato_hash"]:
            raise Conflito("O relato desta OS mudou desde a leitura. Peça os pendentes de novo.")
        chave = hashlib.sha256(f"{os_num}:{o['relato_hash']}:{o['rodada']}".encode()).hexdigest()
        ja = conn.execute("SELECT n_itens FROM identificacoes WHERE chave = ?", (chave,)).fetchone()
        if ja is not None:
            return {"os": os_num, "repetida": True, "itens": ja["n_itens"]}
        if o["identificacao"] != "pendente":
            raise Conflito("Esta OS não está aguardando identificação.")
        ligado = conn.execute("SELECT ligado FROM contratos_cliente WHERE cliente = ?", (o["cliente"],)).fetchone()
        itens, sem_info, motivo = validar(payload, o, catalogo, bool(ligado and ligado[0]))
        versao, snapshot = banco.rota_atual(conn)
        if not versao and itens:
            raise Conflito("A rota de aprovação ainda não foi configurada (tela Níveis de aprovação).")
        conn.execute("DELETE FROM itens WHERE os = ? AND fase = 'relatorio'", (os_num,))
        agora = banco.agora()
        if sem_info:
            itens = [{"item": "Sem material, peça ou serviço no texto", "natureza": "Não identificado",
                      "situacao": "Inconclusivo", "qtd": "—", "presumida": 0, "cls": regras.A_DEFINIR,
                      "conf": "Baixa", "contrato_item": "", "val_ok": 0, "val_txt": f"Sem informação: {motivo}",
                      "evidencia": ""}]
        for it in itens:
            if sem_info:
                fase, pos, rv = "relatorio", None, None
            elif regras.rota_do_item(snapshot, it["cls"]):
                fase, pos, rv = "nivel", 0, versao
            else:
                fase, pos, rv = regras.apos_niveis(it["cls"]), None, versao
            conn.execute(
                "INSERT INTO itens (os, item, natureza, situacao, qtd, presumida, cls, conf, contrato_item, val_ok, "
                "val_txt, evidencia, fase, nivel_pos, rota_versao, sugerido_por, criado_em) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (os_num, it["item"], it["natureza"], it["situacao"], it["qtd"], it["presumida"], it["cls"], it["conf"],
                 it["contrato_item"], it["val_ok"], it["val_txt"], it["evidencia"], fase, pos, rv, agente_nome, agora))
        conn.execute("UPDATE os SET identificacao = ?, atualizada_em = ? WHERE os = ?",
                     ("sem_info" if sem_info else "feita", agora, os_num))
        conn.execute("INSERT INTO identificacoes (chave, os, relato_hash, rodada, agente, n_itens, recebida_em) "
                     "VALUES (?,?,?,?,?,?,?)", (chave, os_num, o["relato_hash"], o["rodada"], agente_nome,
                                                len(itens), agora))
        banco.evento(conn, os_num, "identificacao_agente", agente_nome, obs=motivo,
                     dados={"itens": len(itens), "sem_informacao": sem_info, "sem_itens": not itens and not sem_info,
                            "rodada": o["rodada"]})
    return {"os": os_num, "repetida": False, "itens": len(itens), "sem_informacao": sem_info}


def carregar_catalogo(caminho) -> dict:
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)
