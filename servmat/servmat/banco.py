"""
SQLite WAL. Três tabelas de negócio (os, itens, eventos) mais usuários e o registro das identificações do agente.
`eventos` é só de acréscimo: a trilha de auditoria de cada item sai dela.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS os (
  os             TEXT PRIMARY KEY,
  cliente        TEXT NOT NULL,
  area           TEXT NOT NULL DEFAULT '',
  equipamento    TEXT NOT NULL DEFAULT '',
  tipo           TEXT NOT NULL DEFAULT '',
  tecnico        TEXT NOT NULL DEFAULT '',
  relato         TEXT NOT NULL DEFAULT '',
  utilizou       TEXT NOT NULL DEFAULT '',
  relato_hash    TEXT NOT NULL DEFAULT '',
  origem         TEXT NOT NULL DEFAULT '',
  prog_txt       TEXT NOT NULL DEFAULT '',
  prog_meta      TEXT NOT NULL DEFAULT '',
  task_url       TEXT NOT NULL DEFAULT '',
  identificacao  TEXT NOT NULL DEFAULT 'pendente' CHECK (identificacao IN ('pendente', 'feita', 'sem_info')),
  rodada         INTEGER NOT NULL DEFAULT 1 CHECK (rodada >= 1),
  coletada_em    TEXT NOT NULL,
  atualizada_em  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS itens (
  id             INTEGER PRIMARY KEY,
  os             TEXT NOT NULL REFERENCES os(os) ON DELETE CASCADE,
  item           TEXT NOT NULL CHECK (length(item) BETWEEN 1 AND 160),
  natureza       TEXT NOT NULL CHECK (natureza IN ('Peça', 'Material', 'Serviço', 'Não identificado')),
  situacao       TEXT NOT NULL CHECK (situacao IN ('Aplicado', 'Necessário', 'Inconclusivo')),
  qtd            TEXT NOT NULL,
  presumida      INTEGER NOT NULL DEFAULT 0 CHECK (presumida IN (0, 1)),
  cls            TEXT NOT NULL CHECK (cls IN ('Contrato HGG', 'Pedido de compra', 'A definir')),
  conf           TEXT NOT NULL CHECK (conf IN ('Alta', 'Média', 'Baixa')),
  contrato_item  TEXT NOT NULL DEFAULT '',
  val_ok         INTEGER NOT NULL DEFAULT 1 CHECK (val_ok IN (0, 1)),
  val_txt        TEXT NOT NULL DEFAULT '',
  evidencia      TEXT NOT NULL DEFAULT '',
  fase           TEXT NOT NULL CHECK (fase IN ('relatorio', 'nivel', 'whats', 'pedido', 'fim', 'reprovado')),
  nivel_pos      INTEGER CHECK (nivel_pos IS NULL OR nivel_pos >= 0),
  rota_versao    INTEGER REFERENCES rotas(versao),
  reprovado_em   TEXT,
  versao         INTEGER NOT NULL DEFAULT 1,
  sugerido_por   TEXT NOT NULL,
  criado_em      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS itens_os ON itens(os);
CREATE INDEX IF NOT EXISTS itens_fase ON itens(fase);

CREATE TABLE IF NOT EXISTS eventos (
  id       INTEGER PRIMARY KEY,
  os       TEXT NOT NULL,
  item_id  INTEGER,
  tipo     TEXT NOT NULL,
  quem     TEXT NOT NULL,
  de       TEXT,
  para     TEXT,
  obs      TEXT NOT NULL DEFAULT '',
  dados    TEXT NOT NULL DEFAULT '{}',
  em       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS eventos_os ON eventos(os);
CREATE INDEX IF NOT EXISTS eventos_item ON eventos(item_id);

CREATE TABLE IF NOT EXISTS usuarios (
  usuario     TEXT PRIMARY KEY CHECK (usuario GLOB '[a-z0-9._-]*' AND length(usuario) BETWEEN 2 AND 40),
  nome        TEXT NOT NULL,
  admin       INTEGER NOT NULL DEFAULT 0 CHECK (admin IN (0, 1)),
  senha_hash  TEXT NOT NULL,
  ativo       INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1))
);

-- Níveis da rota em edição (tela "Níveis de aprovação"). Cada gravação vira uma versão em `rotas`.
CREATE TABLE IF NOT EXISTS niveis (
  id        INTEGER PRIMARY KEY,
  ordem     INTEGER NOT NULL,
  papel     TEXT NOT NULL,
  usuario   TEXT REFERENCES usuarios(usuario),
  compra    INTEGER NOT NULL DEFAULT 1 CHECK (compra IN (0, 1)),
  contrato  INTEGER NOT NULL DEFAULT 1 CHECK (contrato IN (0, 1)),
  ativo     INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1))
);

-- Versões imutáveis da rota: o item guarda a versão com que entrou nos níveis.
CREATE TABLE IF NOT EXISTS rotas (
  versao      INTEGER PRIMARY KEY,
  niveis      TEXT NOT NULL,
  criada_em   TEXT NOT NULL,
  criada_por  TEXT NOT NULL
);

-- Critério de contrato por cliente: ligado = o agente confere o catálogo; desligado = "Contrato não avaliado".
CREATE TABLE IF NOT EXISTS contratos_cliente (
  cliente  TEXT PRIMARY KEY,
  ligado   INTEGER NOT NULL DEFAULT 0 CHECK (ligado IN (0, 1))
);

-- Acompanhamento do Pedido: uma linha por OS e rota (compra ou contrato).
CREATE TABLE IF NOT EXISTS pedidos (
  os             TEXT NOT NULL REFERENCES os(os) ON DELETE CASCADE,
  tipo           TEXT NOT NULL CHECK (tipo IN ('compra', 'contrato')),
  pedido_num     TEXT NOT NULL DEFAULT '',
  vinculo        TEXT NOT NULL DEFAULT '' CHECK (vinculo IN ('', 'a_conferir', 'vinculado', 'nao_localizado')),
  aceite         TEXT NOT NULL DEFAULT '' CHECK (aceite IN ('', 'aguardando', 'aceito', 'parcial', 'recusado')),
  aceite_obs     TEXT NOT NULL DEFAULT '',
  celso          TEXT NOT NULL DEFAULT '' CHECK (celso IN ('', 'aguardando', 'autorizado', 'devolvido', 'reprovado')),
  execucao       TEXT NOT NULL DEFAULT '' CHECK (execucao IN ('', 'a_agendar', 'agendada', 'concluida')),
  execucao_meta  TEXT NOT NULL DEFAULT '',
  nf             TEXT NOT NULL DEFAULT '',
  fonte          TEXT NOT NULL DEFAULT '',
  atualizado_em  TEXT NOT NULL,
  PRIMARY KEY (os, tipo)
);

-- Fila de mensagens ao orçamentista. INCERTO (caiu depois de enviar) nunca reenvia sozinho.
CREATE TABLE IF NOT EXISTS envios (
  id             INTEGER PRIMARY KEY,
  chave          TEXT NOT NULL UNIQUE,
  os             TEXT NOT NULL,
  tipo           TEXT NOT NULL,
  acao           TEXT NOT NULL CHECK (acao IN ('solicitacao', 'cobranca')),
  destino        TEXT NOT NULL,
  texto          TEXT NOT NULL,
  estado         TEXT NOT NULL CHECK (estado IN ('PENDENTE', 'ENVIADO', 'FALHOU', 'INCERTO', 'SIMULADO')),
  recibo         TEXT NOT NULL DEFAULT '',
  motivo         TEXT NOT NULL DEFAULT '',
  tentativas     INTEGER NOT NULL DEFAULT 0,
  quem           TEXT NOT NULL,
  criado_em      TEXT NOT NULL,
  atualizado_em  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS envios_os ON envios(os, tipo, acao);

-- Áudios da avaliação no celular. O arquivo fica em dados/audios/; a transcrição é conferida pela pessoa.
CREATE TABLE IF NOT EXISTS audios (
  id          TEXT PRIMARY KEY,
  item_id     INTEGER NOT NULL REFERENCES itens(id) ON DELETE CASCADE,
  usuario     TEXT NOT NULL,
  arquivo     TEXT NOT NULL,
  mime        TEXT NOT NULL,
  bytes       INTEGER NOT NULL,
  transcricao TEXT NOT NULL DEFAULT '',
  criado_em   TEXT NOT NULL
);

-- Última leitura de cada integração (sistema comercial, planilha do cliente).
CREATE TABLE IF NOT EXISTS integracoes (
  nome       TEXT PRIMARY KEY,
  ultima_em  TEXT NOT NULL,
  resumo     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS identificacoes (
  id           INTEGER PRIMARY KEY,
  chave        TEXT NOT NULL UNIQUE,
  os           TEXT NOT NULL,
  relato_hash  TEXT NOT NULL,
  rodada       INTEGER NOT NULL,
  agente       TEXT NOT NULL,
  n_itens      INTEGER NOT NULL,
  recebida_em  TEXT NOT NULL
);
"""


def agora() -> str:
    return datetime.now(FUSO).isoformat(timespec="seconds")


def conectar(caminho: Path | str) -> sqlite3.Connection:
    if str(caminho) != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(caminho), timeout=15, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    if str(caminho) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def criar(conn: sqlite3.Connection) -> None:
    conn.executescript(ESQUEMA)


class Transacao:
    """BEGIN IMMEDIATE ... COMMIT/ROLLBACK: a decisão lê e grava sob o mesmo bloqueio."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, tipo, valor, tb):
        self.conn.execute("ROLLBACK" if tipo else "COMMIT")
        return False


def evento(conn: sqlite3.Connection, os_: str, tipo: str, quem: str, item_id: int | None = None,
           de: str | None = None, para: str | None = None, obs: str = "", dados: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO eventos (os, item_id, tipo, quem, de, para, obs, dados, em) VALUES (?,?,?,?,?,?,?,?,?)",
        (os_, item_id, tipo, quem, de, para, obs, json.dumps(dados or {}, ensure_ascii=False), agora()))


NIVEIS_PADRAO = [
    {"papel": "Confirma ou corrige a sugestão do agente", "usuario": "hely", "compra": True, "contrato": True, "ativo": True},
    {"papel": "Avaliação técnica", "usuario": "renato", "compra": True, "contrato": True, "ativo": True},
]


def _snapshot(conn: sqlite3.Connection, niveis: list[dict]) -> list[dict]:
    nomes = dict(conn.execute("SELECT usuario, nome FROM usuarios").fetchall())
    return [dict(n, nome=nomes.get(n.get("usuario") or "", n.get("usuario") or "")) for n in niveis]


def salvar_rota(conn: sqlite3.Connection, niveis: list[dict], quem: str) -> int:
    """Grava a lista de níveis em edição e cria uma versão nova (imutável) da rota. Chamar dentro de Transacao."""
    conn.execute("DELETE FROM niveis")
    for k, n in enumerate(niveis):
        conn.execute("INSERT INTO niveis (ordem, papel, usuario, compra, contrato, ativo) VALUES (?,?,?,?,?,?)",
                     (k, n["papel"], n.get("usuario"), int(n["compra"]), int(n["contrato"]), int(n["ativo"])))
    versao = (conn.execute("SELECT COALESCE(MAX(versao), 0) FROM rotas").fetchone()[0]) + 1
    conn.execute("INSERT INTO rotas (versao, niveis, criada_em, criada_por) VALUES (?,?,?,?)",
                 (versao, json.dumps(_snapshot(conn, niveis), ensure_ascii=False), agora(), quem))
    evento(conn, "*", "rota_nova", quem, dados={"versao": versao, "niveis": len(niveis)})
    return versao


def rota_atual(conn: sqlite3.Connection) -> tuple[int, list[dict]]:
    r = conn.execute("SELECT versao, niveis FROM rotas ORDER BY versao DESC LIMIT 1").fetchone()
    if r is None:
        return 0, []
    return r["versao"], json.loads(r["niveis"])


def rotas_por_versao(conn: sqlite3.Connection) -> dict[int, list[dict]]:
    return {r["versao"]: json.loads(r["niveis"]) for r in conn.execute("SELECT versao, niveis FROM rotas")}


def garantir_rota(conn: sqlite3.Connection) -> None:
    """Primeira subida: rota padrão (Hely → Renato) e contrato ligado só no HGG, se os usuários já existirem."""
    if conn.execute("SELECT COUNT(*) FROM rotas").fetchone()[0]:
        return
    usuarios = {r[0] for r in conn.execute("SELECT usuario FROM usuarios WHERE ativo = 1")}
    if not {"hely", "renato"} <= usuarios:
        return
    with Transacao(conn):
        salvar_rota(conn, NIVEIS_PADRAO, "sistema")
        conn.execute("INSERT OR IGNORE INTO contratos_cliente (cliente, ligado) VALUES ('HGG', 1)")
