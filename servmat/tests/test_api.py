from conftest import AGENTE, RUN, entrar


def _item(cli, os_, nome_parcial):
    p = cli.get("/api/painel").json()
    s = next(s for s in p["servicos"] if s["os"] == os_)
    return s, next(i for i in s["itens"] if nome_parcial in i["item"])


def test_painel_exige_login(cliente):
    assert cliente.get("/api/painel").status_code == 401


def test_painel_agrupa_por_servico(cliente):
    entrar(cliente, "hely")
    p = cliente.get("/api/painel").json()
    assert len(p["servicos"]) == 11
    s = next(s for s in p["servicos"] if s["os"] == "71741916")
    assert (len(s["itens"]), s["cls"], s["mix"]) == (4, "Misto", "3 peças · 1 material")
    assert s["agora"]["nome"] == "Classificação PCM"
    assert sum(f["qtd"] for f in p["fases"]) == 15
    ibis = next(s for s in p["servicos"] if s["os"] == "82447493")
    assert ibis["conflito_n2"] is True
    assert "task_url" not in s


def test_fluxo_n1_n2(cliente):
    h = entrar(cliente, "hely")
    _, it = _item(cliente, "71741916", "Filtro secador")
    r = cliente.post(f"/api/itens/{it['id']}/decisao", json={"acao": "aprovar", "versao": it["versao"]}, headers=h)
    assert r.json()["fase"] == "n2"
    # versão velha → 409
    r = cliente.post(f"/api/itens/{it['id']}/decisao", json={"acao": "aprovar", "versao": it["versao"]}, headers=h)
    assert r.status_code == 409
    h2 = entrar(cliente, "renato")
    _, it = _item(cliente, "71741916", "Filtro secador")
    r = cliente.post(f"/api/itens/{it['id']}/decisao", json={"acao": "aprovar", "versao": it["versao"]}, headers=h2)
    assert r.json()["fase"] == "pedido"
    ev = cliente.get(f"/api/itens/{it['id']}/eventos").json()
    assert [(e["de"], e["para"], e["quem"]) for e in ev] == [("n1", "n2", "hely"), ("n2", "pedido", "renato")]


def test_escrita_sem_cabecalho_do_painel_e_recusada(cliente):
    entrar(cliente, "hely")
    _, it = _item(cliente, "71741916", "Filtro secador")
    r = cliente.post(f"/api/itens/{it['id']}/decisao", json={"acao": "aprovar", "versao": it["versao"]})
    assert r.status_code == 403


def test_a_definir_bloqueia_e_reclassificar_libera(cliente):
    h = entrar(cliente, "hely")
    _, it = _item(cliente, "82423841", "Disjuntor")
    r = cliente.post(f"/api/itens/{it['id']}/decisao", json={"acao": "aprovar", "versao": it["versao"]}, headers=h)
    assert r.status_code == 422 and "Contrato HGG e Pedido" in r.json()["detail"]
    r = cliente.post(f"/api/itens/{it['id']}/classificacao", json={"cls": "Pedido de compra", "versao": it["versao"]},
                     headers=h)
    assert r.status_code == 200
    r = cliente.post(f"/api/itens/{it['id']}/decisao", json={"acao": "aprovar", "versao": it["versao"] + 1}, headers=h)
    assert r.json()["fase"] == "n2"


def test_devolver_ao_agente_volta_para_a_fila_do_openclaw(cliente):
    h = entrar(cliente, "hely")
    _, it = _item(cliente, "82475965", "Rolamentos")
    r = cliente.post(f"/api/itens/{it['id']}/decisao",
                     json={"acao": "devolver", "obs": "Informe a quantidade de rolamentos", "versao": it["versao"]},
                     headers=h)
    assert r.json()["fase"] == "relatorio"
    a = {"Authorization": f"Bearer {AGENTE}"}
    pend = cliente.get("/api/agente/pendentes", headers=a).json()["pendentes"]
    p = next(x for x in pend if x["os"] == "82475965")
    assert p["devolucoes_do_nivel_1"] == ["Informe a quantidade de rolamentos"]
    r = cliente.post("/api/agente/identificacoes", headers=a, json={
        "os": "82475965", "relato_hash": p["relato_hash"], "itens": [{
            "item": "Rolamentos do motor", "natureza": "Peça", "situacao": "Necessário", "qtd": "2 un",
            "presumida": True, "cls": "Pedido de compra", "conf": "Média",
            "evidencia": "Rolamentos do motor com folga"}]})
    assert r.status_code == 200, r.text
    _, novo = _item(cliente, "82475965", "Rolamentos")
    assert (novo["fase"], novo["qtd"]) == ("n1", "2 un")


def test_rotas_de_robo_exigem_token(cliente):
    assert cliente.get("/api/agente/pendentes").status_code == 401
    assert cliente.get("/api/agente/pendentes", headers={"Authorization": f"Bearer {RUN}"}).status_code == 401
    assert cliente.post("/run/coleta").status_code == 401
    assert cliente.get("/run/status", headers={"Authorization": f"Bearer {RUN}"}).json()["aguardando_agente"] == 0


def test_login_errado_e_freio(cliente):
    for _ in range(5):
        assert cliente.post("/api/login", json={"usuario": "hely", "senha": "errada-errada"}).status_code == 401
    assert cliente.post("/api/login", json={"usuario": "hely", "senha": "senha-de-teste-123"}).status_code == 429
