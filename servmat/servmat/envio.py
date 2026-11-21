"""
Mensagens ao orçamentista pelo WhatsApp (WAHA dedicado, como no fechamento-os).

- Duas ações separadas, cada uma com destinatário, escopo, data e recibo: solicitação (orçamento ou Pedido de
  contrato) e cobrança.
- Fila `envios` com chave de idempotência: a mesma solicitação nunca sai duas vezes.
- Resultado: ENVIADO (com recibo do WAHA) · FALHOU (o WAHA recusou: pode tentar de novo) · INCERTO (a conexão caiu
  depois do envio: pode ter sido entregue, NUNCA reenvia sozinho; o PCM decide no painel) · SIMULADO (piloto).
- Sem SERVMAT_ENVIO_REAL=1 tudo fica SIMULADO, com o texto guardado para conferência.
"""
from __future__ import annotations

import json
import re
import socket
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from . import banco

Transporte = Callable[[str, str, dict, bytes | None], tuple[int, bytes]]


class FalhaEnvio(Exception):
    """O WAHA respondeu com erro: a mensagem não saiu."""


class EnvioIncerto(Exception):
    """A conexão caiu sem resposta: a mensagem pode ter saído."""


def transporte_urllib(timeout: float = 30.0) -> Transporte:
    def enviar(metodo, url, cab, corpo):
        req = urllib.request.Request(url, data=corpo, headers=cab, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read() or b""
        except urllib.error.URLError as e:
            # Sem conexão nenhuma (recusada, DNS): a mensagem com certeza não saiu.
            if isinstance(e.reason, (ConnectionRefusedError, socket.gaierror)):
                raise FalhaEnvio(f"WAHA inacessível: {type(e.reason).__name__}") from None
            raise EnvioIncerto("sem resposta do WAHA") from None
        except (TimeoutError, OSError):
            raise EnvioIncerto("sem resposta do WAHA") from None
    return enviar


def so_digitos(t: str) -> str:
    return re.sub(r"\D", "", t or "")


class Waha:
    def __init__(self, base: str, api_key: str, sessao: str = "default", transporte: Transporte | None = None):
        if not base.startswith(("http://127.0.0.1", "http://localhost", "http://172.", "http://waha", "https://")):
            raise ValueError("WAHA só por rede interna ou https")
        self.base = base.rstrip("/")
        self._chave = api_key
        self.sessao = sessao
        self._enviar = transporte or transporte_urllib()

    def _req(self, metodo: str, rota: str, corpo: dict | None = None, params: dict | None = None) -> dict:
        url = self.base + rota + ("?" + urllib.parse.urlencode(params) if params else "")
        cab = {"X-Api-Key": self._chave, "Accept": "application/json"}
        dados = None
        if corpo is not None:
            cab["Content-Type"] = "application/json"
            dados = json.dumps(corpo).encode()
        status, resp = self._enviar(metodo, url, cab, dados)
        if status >= 400:
            raise FalhaEnvio(f"WAHA respondeu {status}")
        try:
            return json.loads(resp or b"{}")
        except ValueError:
            return {}

    def chat_id(self, telefone: str) -> str:
        if "@" in telefone:
            return telefone
        r = self._req("GET", "/api/contacts/check-exists", params={"phone": so_digitos(telefone), "session": self.sessao})
        if not r.get("numberExists") or not r.get("chatId"):
            raise FalhaEnvio("número do orçamentista não existe no WhatsApp")
        return r["chatId"]

    def enviar_texto(self, chat_id: str, texto: str) -> str:
        r = self._req("POST", "/api/sendText", {"session": self.sessao, "chatId": chat_id, "text": texto})
        i = r.get("id")
        if isinstance(i, dict):
            i = i.get("_serialized") or i.get("id")
        return str(i or "sem-id")


@dataclass(frozen=True)
class ConfigEnvio:
    real: bool
    waha_url: str
    waha_chave: str
    waha_sessao: str
    destino: str          # telefone ou chatId do orçamentista
    nome_destino: str


def texto_solicitacao(o: sqlite3.Row, itens: list[sqlite3.Row], tipo: str) -> str:
    linhas = [f"• {i['qtd']} · {i['item']}" + (" (já aplicado: regularização)" if i["situacao"] == "Aplicado" else "")
              for i in itens]
    if tipo == "contrato":
        cab = f"*Pedido de contrato* · OS {o['os']}\nCriar o Pedido e vincular à OS (itens do contrato {o['cliente']})."
    else:
        cab = f"*Solicitação de orçamento* · OS {o['os']}"
    onde = " · ".join(x for x in (o["cliente"], o["equipamento"], o["area"]) if x)
    return f"{cab}\n{onde}\n\n" + "\n".join(linhas) + "\n\nAprovado nos níveis internos (painel servmat)."


def texto_cobranca(o: sqlite3.Row, itens: list[sqlite3.Row], p: sqlite3.Row | None) -> str:
    linhas = [f"• {i['qtd']} · {i['item']}" for i in itens]
    ped = f"Pedido {p['pedido_num']}" if p is not None and p["pedido_num"] else "Pedido não informado"
    onde = " · ".join(x for x in (o["cliente"], o["equipamento"], o["area"]) if x)
    return (f"*Solicitação de cobrança* · OS {o['os']} · {ped}\n{onde}\n\n" + "\n".join(linhas) +
            "\n\nServiço executado. Favor seguir com a cobrança.")


def solicitar(conn: sqlite3.Connection, cfg: ConfigEnvio, os_num: str, tipo: str, acao: str, quem: str,
              texto: str, waha: Waha | None = None, rodada: int = 1) -> sqlite3.Row:
    """Enfileira e envia uma mensagem. Repetir o pedido devolve o envio existente (não duplica)."""
    chave = f"{acao}:{os_num}:{tipo}:{rodada}"
    agora = banco.agora()
    with banco.Transacao(conn):
        e = conn.execute("SELECT * FROM envios WHERE chave = ?", (chave,)).fetchone()
        if e is not None and e["estado"] in ("ENVIADO", "SIMULADO", "INCERTO", "PENDENTE"):
            return e
        if e is None:
            conn.execute("INSERT INTO envios (chave, os, tipo, acao, destino, texto, estado, quem, criado_em, "
                         "atualizado_em) VALUES (?,?,?,?,?,?, 'PENDENTE', ?,?,?)",
                         (chave, os_num, tipo, acao, cfg.nome_destino or "orçamentista", texto, quem, agora, agora))
        else:
            conn.execute("UPDATE envios SET estado = 'PENDENTE', texto = ?, quem = ?, atualizado_em = ? WHERE chave = ?",
                         (texto, quem, agora, chave))
        banco.evento(conn, os_num, f"envio_{acao}", quem, dados={"tipo": tipo, "real": cfg.real})
    # O envio acontece FORA da transação: a linha PENDENTE já está gravada se o processo cair no meio.
    estado, recibo, motivo = "SIMULADO", "simulado", ""
    if cfg.real:
        try:
            w = waha or Waha(cfg.waha_url, cfg.waha_chave, cfg.waha_sessao)
            recibo = w.enviar_texto(w.chat_id(cfg.destino), texto)
            estado = "ENVIADO"
        except FalhaEnvio as ex:
            estado, recibo, motivo = "FALHOU", "", str(ex)
        except EnvioIncerto as ex:
            estado, recibo, motivo = "INCERTO", "", str(ex)
    conn.execute("UPDATE envios SET estado = ?, recibo = ?, motivo = ?, tentativas = tentativas + 1, "
                 "atualizado_em = ? WHERE chave = ?", (estado, recibo, motivo, banco.agora(), chave))
    return conn.execute("SELECT * FROM envios WHERE chave = ?", (chave,)).fetchone()


def resolver_incerto(conn: sqlite3.Connection, envio_id: int, decisao: str, quem: str) -> sqlite3.Row:
    """O PCM confere no WhatsApp: 'entregue' (vira ENVIADO) ou 'nao_entregue' (vira FALHOU e pode reenviar)."""
    with banco.Transacao(conn):
        e = conn.execute("SELECT * FROM envios WHERE id = ?", (envio_id,)).fetchone()
        if e is None:
            raise KeyError(envio_id)
        if e["estado"] != "INCERTO":
            raise ValueError("Só um envio INCERTO recebe esta decisão.")
        novo = {"entregue": "ENVIADO", "nao_entregue": "FALHOU"}.get(decisao)
        if novo is None:
            raise ValueError("Decisão inválida.")
        conn.execute("UPDATE envios SET estado = ?, recibo = ?, motivo = ?, atualizado_em = ? WHERE id = ?",
                     (novo, "conferido por " + quem if novo == "ENVIADO" else "", "conferência manual",
                      banco.agora(), envio_id))
        banco.evento(conn, e["os"], "envio_conferido", quem, de="INCERTO", para=novo, dados={"envio": envio_id})
    return conn.execute("SELECT * FROM envios WHERE id = ?", (envio_id,)).fetchone()
