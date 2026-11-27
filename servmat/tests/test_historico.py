from datetime import datetime

import pytest

from servmat import historico, seed
from servmat.central import Central

from conftest import AGENTE, entrar

CFG = {"campos": "x", "campo_relato": "report", "pergunta_utilizou": "Utilizou peça",
       "clientes": {"HGG": ["HGG"], "CAMIL": ["CAMIL"]}}


def tarefa(tid, cliente, relato, data="2026-03-10T09:00:00", util="Sim"):
    return {"taskID": tid, "taskStatus": 5, "customerDescription": cliente, "report": relato, "checkInDate": data,
            "questionnaires": [{"answers": [{"questionDescription": "Utilizou peça?", "reply": util}]}]}


class CentralFalsa(Central):
    def __init__(self, tarefas):
        self.tarefas, self.chamadas = tarefas, []

    def listar_tarefas(self, inicio, fim, campos, max_paginas=100):
        from servmat.central import Listagem
        self.chamadas.append((inicio, fim))
        return Listagem([t for t in self.tarefas if inicio <= datetime.fromisoformat(t["checkInDate"]) < fim], True)


@pytest.fixture
def com_historico(conn):
    c = CentralFalsa([
        tarefa(5001, "CAMIL - GOIANIA", "Trocada a contactora 40A do compressor 2"),
        tarefa(5002, "CAMIL - GOIANIA", "Substituído contator 40 A e 2 m de isolamento 3/4", data="2026-04-02T10:00:00"),
        tarefa(5003, "HGG - 2 ANDAR", "foi trocado o filtro secador 210x1/2"),
        tarefa(5004, "IBIS", "trocado capacitor"),
        tarefa(4000, "CAMIL", "antes do período", data="2026-01-15T10:00:00"),
    ])
    rel = historico.importar(conn, c, CFG, datetime(2026, 2, 1), datetime(2026, 5, 1), ["HGG", "CAMIL"])
    assert rel.completa and rel.por_cliente == {"CAMIL": 2, "HGG": 1}
    assert len(c.chamadas) > 1  # janelas curtas
    return conn


def test_historico_nao_entra_na_fila(com_historico):
    assert com_historico.execute("SELECT COUNT(*) FROM os WHERE os IN ('5001','5002','5003')").fetchone()[0] == 0


def test_pagina(com_historico):
    p = historico.pagina(com_historico, "camil", limite=1)
    assert p["total"] == 2 and p["os"][0]["os"] == "5001" and p["proximo"] == "5001"
    p2 = historico.pagina(com_historico, "CAMIL", apos="5001", limite=1)
    assert p2["os"][0]["os"] == "5002"


def proposta(**k):
    base = {"cliente": "CAMIL", "desde": "2026-02-01", "itens": [
        {"nome": "Contatora 40 A", "natureza": "Peça", "sinonimos": ["contactora 40A", "contator 40 A"],
         "ocorrencias": 2, "os_exemplo": ["5001", "5002"], "evidencia": "contactora 40A"}]}
    base.update(k)
    return base


def test_proposta_aceita_e_aprovacao(com_historico):
    r = historico.propor(com_historico, proposta(), "agente:t")
    assert r["situacao"] == "rascunho" and r["itens"] == 1
    assert historico.uso_aprovado(com_historico) == {}
    historico.aprovar(com_historico, r["id"], "hely")
    assert historico.uso_aprovado(com_historico)["CAMIL"][0]["nome"] == "Contatora 40 A"
    r2 = historico.propor(com_historico, proposta(), "agente:t")
    historico.aprovar(com_historico, r2["id"], "hely")
    sit = {p["id"]: p["situacao"] for p in historico.propostas(com_historico, "CAMIL")}
    assert sit == {r["id"]: "substituido", r2["id"]: "aprovado"}


@pytest.mark.parametrize("mudar, trecho", [
    ({"evidencia": "compressor novo instalado"}, "não está no relato"),
    ({"os_exemplo": ["5003"]}, "não estão no histórico do CAMIL"),
    ({"natureza": "Coisa"}, "natureza"),
    ({"contrato_num": 57}, "só para HGG"),
    ({"os_exemplo": 5001}, "lista de números de OS"),
])
def test_proposta_recusada(com_historico, mudar, trecho):
    it = dict(proposta()["itens"][0], **mudar)
    with pytest.raises(historico.ErroProposta) as e:
        historico.propor(com_historico, proposta(itens=[it]), "agente:t")
    assert trecho in str(e.value)


def test_nomes_repetidos_recusados(com_historico):
    it = proposta()["itens"][0]
    with pytest.raises(historico.ErroProposta, match="repetido"):
        historico.propor(com_historico, proposta(itens=[it, dict(it, nome="contatora 40 a")]), "agente:t")


def test_ensaio_do_historico(com_historico):
    assert historico.ensaio(com_historico, "CAMIL", 5) == ["5002", "5001"]
    o = com_historico.execute("SELECT identificacao FROM os WHERE os = '5001'").fetchone()
    assert o["identificacao"] == "pendente"
    assert historico.ensaio(com_historico, "CAMIL", 5) == []  # não duplica


def test_ensaio_do_esboco(conn):
    with pytest.raises(SystemExit):
        seed.ensaio(conn)
    assert seed.ensaio(conn, forcar=True) == 11
    assert conn.execute("SELECT COUNT(*) FROM itens").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM os WHERE identificacao = 'pendente'").fetchone()[0] == 11


def test_api_agente(cliente, com_historico):
    h = {"Authorization": f"Bearer {AGENTE}", "X-Agente": "teste"}
    r = cliente.get("/api/agente/historico", params={"cliente": "CAMIL", "desde": "2026-02-01"}, headers=h)
    assert r.status_code == 200 and r.json()["total"] == 2
    assert cliente.get("/api/agente/historico", params={"cliente": "CAMIL"}).status_code == 401
    r = cliente.post("/api/agente/catalogo-proposto", json=proposta(), headers=h)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    ruim = proposta(itens=[dict(proposta()["itens"][0], evidencia="nada disso")])
    r = cliente.post("/api/agente/catalogo-proposto", json=ruim, headers=h)
    assert r.status_code == 422 and r.json()["erros"]
    # pessoa vê; só admin aprova
    hd = entrar(cliente, "renato")
    assert cliente.get("/api/catalogo-proposto").json()["propostas"][0]["id"] == pid
    assert cliente.post(f"/api/catalogo-proposto/{pid}/aprovar", headers=hd).status_code == 403
    hd = entrar(cliente, "hely")
    assert cliente.post(f"/api/catalogo-proposto/{pid}/aprovar", headers=hd).status_code == 200
    cat = cliente.get("/api/agente/catalogo", headers=h).json()
    assert cat["uso"]["CAMIL"][0]["sinonimos"] == ["contactora 40A", "contator 40 A"]
