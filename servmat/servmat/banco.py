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
  fase           TEXT NOT NULL CHECK (fase IN ('relatorio', 'n1', 'n2', 'whats', 'pedido', 'fim', 'reprovado')),
  reprovado_em   TEXT CHECK (reprovado_em IS NULL OR reprovado_em IN ('n1', 'n2')),
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
  nivel       INTEGER NOT NULL CHECK (nivel IN (1, 2)),
  senha_hash  TEXT NOT NULL,
  ativo       INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1))
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
