import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servmat import auth, banco, seed  # noqa: E402
from servmat.config import carregar  # noqa: E402

AGENTE = "agente-token-de-teste-com-32-caracteres!!"
INTEG = "integracao-token-de-teste-com-32-caracteres"
RUN = "run-token-de-teste-com-32-caracteres!!!!!"


@pytest.fixture
def cfg(tmp_path):
    return carregar({
        "SERVMAT_SEGREDO": "x" * 40, "SERVMAT_BANCO": str(tmp_path / "t.sqlite"),
        "SERVMAT_AGENTE_TOKEN": AGENTE, "SERVMAT_RUN_TOKEN": RUN, "SERVMAT_WEB": str(tmp_path / "semweb"),
        "SERVMAT_COOKIE_SEGURO": "0", "SERVMAT_INTEGRACAO_TOKEN": INTEG,
    })


@pytest.fixture
def conn(cfg):
    c = banco.conectar(cfg.banco)
    banco.criar(c)
    for u, n, adm in (("hely", "Hely R Menezes", 1), ("renato", "Renato Bonfim", 0), ("celso", "Celso Lima", 0)):
        c.execute("INSERT INTO usuarios (usuario, nome, admin, senha_hash) VALUES (?,?,?,?)",
                  (u, n, adm, auth.hash_senha("senha-de-teste-123")))
    banco.garantir_rota(c)
    seed.carregar(c)
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
