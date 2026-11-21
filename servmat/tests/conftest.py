import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servmat import auth, banco, seed  # noqa: E402
from servmat.config import carregar  # noqa: E402

AGENTE = "agente-token-de-teste-com-32-caracteres!!"
RUN = "run-token-de-teste-com-32-caracteres!!!!!"


@pytest.fixture
def cfg(tmp_path):
    return carregar({
        "SERVMAT_SEGREDO": "x" * 40, "SERVMAT_BANCO": str(tmp_path / "t.sqlite"),
        "SERVMAT_AGENTE_TOKEN": AGENTE, "SERVMAT_RUN_TOKEN": RUN, "SERVMAT_WEB": str(tmp_path / "semweb"),
        "SERVMAT_COOKIE_SEGURO": "0",
    })


@pytest.fixture
def conn(cfg):
    c = banco.conectar(cfg.banco)
    banco.criar(c)
    seed.carregar(c)
    for u, n, nv in (("hely", "Hely R Menezes", 1), ("renato", "Renato Bonfim", 2)):
        c.execute("INSERT INTO usuarios (usuario, nome, nivel, senha_hash) VALUES (?,?,?,?)",
                  (u, n, nv, auth.hash_senha("senha-de-teste-123")))
    yield c
    c.close()


@pytest.fixture
def cliente(cfg, conn):
    from fastapi.testclient import TestClient
    from servmat.api import criar_app
    return TestClient(criar_app(cfg))


def entrar(cli, usuario):
    r = cli.post("/api/login", json={"usuario": usuario, "senha": "senha-de-teste-123"})
    assert r.status_code == 200, r.text
    return {"X-Servmat": "1"}
