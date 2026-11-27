import pytest

from servmat import agente, banco

CAT = {"HGG": {"_incompleto": True, "itens": {"57": "FILTRO SECADOR"}}}


def nova_os(conn, os_="90000001", cliente="HGG", relato="Foi trocado o filtro secador 210x1/2 e precisa trocar a contatora 40A",
            utilizou="Nao"):
    agora = banco.agora()
    conn.execute("INSERT INTO os (os, cliente, relato, utilizou, relato_hash, coletada_em, atualizada_em) "
                 "VALUES (?,?,?,?,?,?,?)", (os_, cliente, relato, utilizou, agente.hash_relato(relato, utilizou), agora, agora))
    return conn.execute("SELECT * FROM os WHERE os = ?", (os_,)).fetchone()


def item(**k):
    base = dict(item="Filtro secador 210 × 1/2", natureza="Peça", situacao="Aplicado", qtd="1 un", cls="Contrato HGG",
                contrato_num=57, conf="Alta", evidencia="trocado o filtro secador 210x1/2")
    base.update(k)
    return base


def test_aceita_e_grava_no_nivel_1(conn):
    o = nova_os(conn)
    r = agente.aplicar(conn, {"os": o["os"], "relato_hash": o["relato_hash"], "itens": [
        item(), item(item="Contatora 220 V 40 A", situacao="Necessário", cls="Pedido de compra", contrato_num=None,
                     conf="Média", evidencia="precisa trocar a contatora 40A")]}, "agente:t", CAT)
    assert r == {"os": "90000001", "repetida": False, "itens": 2, "sem_informacao": False}
    linhas = conn.execute("SELECT * FROM itens WHERE os = '90000001' ORDER BY id").fetchall()
    assert [(x["fase"], x["nivel_pos"]) for x in linhas] == [("nivel", 0), ("nivel", 0)]
    assert linhas[0]["rota_versao"] == 1
    assert linhas[0]["contrato_item"] == "Item do contrato: 57 · FILTRO SECADOR"
    # campo "Nao" + troca aplicada = divergência, mesmo que o agente diga que está coerente
    assert linhas[0]["val_ok"] == 0 and linhas[0]["val_txt"].startswith("Divergência")
    assert conn.execute("SELECT identificacao FROM os WHERE os = '90000001'").fetchone()[0] == "feita"


def test_repeticao_nao_duplica(conn):
    o = nova_os(conn)
    p = {"os": o["os"], "relato_hash": o["relato_hash"], "itens": [item()]}
    agente.aplicar(conn, p, "agente:t", CAT)
    assert agente.aplicar(conn, p, "agente:t", CAT)["repetida"] is True
    assert conn.execute("SELECT COUNT(*) FROM itens WHERE os = '90000001'").fetchone()[0] == 1


def test_recusa_evidencia_inventada(conn):
    o = nova_os(conn)
    with pytest.raises(agente.ErroIdentificacao, match="evidência não está no relato"):
        agente.aplicar(conn, {"os": o["os"], "relato_hash": o["relato_hash"],
                              "itens": [item(evidencia="trocado o compressor")]}, "agente:t", CAT)
    assert conn.execute("SELECT COUNT(*) FROM itens WHERE os = '90000001'").fetchone()[0] == 0


def test_contrato_hgg_so_para_hgg(conn):
    o = nova_os(conn, cliente="IBIS")
    with pytest.raises(agente.ErroIdentificacao, match="só vale para OS do HGG"):
        agente.aplicar(conn, {"os": o["os"], "relato_hash": o["relato_hash"], "itens": [item()]}, "agente:t", CAT)


def test_relato_mudou_conflito(conn):
    o = nova_os(conn)
    with pytest.raises(agente.Conflito):
        agente.aplicar(conn, {"os": o["os"], "relato_hash": "velho", "itens": [item()]}, "agente:t", CAT)


def test_sem_informacao_fica_no_relatorio(conn):
    o = nova_os(conn, relato="Materiais na imagem")
    agente.aplicar(conn, {"os": o["os"], "relato_hash": o["relato_hash"], "itens": [], "sem_informacao": True,
                          "motivo": "lista só na foto anexada"}, "agente:t", CAT)
    it = conn.execute("SELECT * FROM itens WHERE os = '90000001'").fetchone()
    assert (it["fase"], it["natureza"]) == ("relatorio", "Não identificado")


def test_pendentes_traz_relato_e_hash(conn):
    o = nova_os(conn)
    p = agente.pendentes(conn)
    assert [x["os"] for x in p] == ["90000001"]
    assert p[0]["relato_hash"] == o["relato_hash"] and p[0]["ja_registrados"] == []


def test_normalizar_tolera_acento_e_pontuacao():
    assert agente.normalizar("Condesador  muito amassado,") in agente.normalizar("o condesador muito AMASSADO, com...")


def test_contrato_desligado_recusa_contrato(conn):
    conn.execute("UPDATE contratos_cliente SET ligado = 0 WHERE cliente = 'HGG'")
    o = nova_os(conn)
    with pytest.raises(agente.ErroIdentificacao, match="critério de contrato do HGG está desligado"):
        agente.aplicar(conn, {"os": o["os"], "relato_hash": o["relato_hash"], "itens": [item()]}, "agente:t", CAT)



def test_sem_itens_conclui_a_os_sem_aprovacao_e_tira_da_fila(conn, cliente):
    from conftest import entrar
    rel = "Realizado a preventiva mensal com produto bactericida, equipamento funcionando normal"
    o = nova_os(conn, relato=rel, utilizou="")
    r = agente.aplicar(conn, {"os": o["os"], "relato_hash": o["relato_hash"], "itens": [], "sem_itens": True,
                              "motivo": "PMOC de rotina: limpeza e produto bactericida"}, "agente:t", CAT)
    assert r == {"os": "90000001", "repetida": False, "itens": 0, "sem_informacao": False}
    assert conn.execute("SELECT identificacao FROM os WHERE os = '90000001'").fetchone()[0] == "feita"
    assert conn.execute("SELECT COUNT(*) FROM itens WHERE os = '90000001'").fetchone()[0] == 0
    entrar(cliente, "hely")
    p = cliente.get("/api/painel").json()
    assert "90000001" not in [s["os"] for s in p["servicos"]]
    assert p["sem_itens"] == 1


@pytest.mark.parametrize("extra", [
    {"itens": [], "sem_itens": True},
    {"itens": [item()], "sem_itens": True, "motivo": "rotina"},
    {"itens": [], "sem_itens": True, "sem_informacao": True, "motivo": "rotina"},
    {"itens": []},
])
def test_sem_itens_exige_motivo_lista_vazia_e_nao_combina_com_sem_informacao(conn, extra):
    o = nova_os(conn)
    with pytest.raises(agente.ErroIdentificacao):
        agente.validar({"os": o["os"], "relato_hash": o["relato_hash"], **extra}, o, CAT)
