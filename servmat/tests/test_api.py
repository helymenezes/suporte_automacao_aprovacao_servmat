from conftest import AGENTE, RUN, entrar


def _item(cli, os_, nome_parcial):
    p = cli.get("/api/painel").json()
    s = next(s for s in p["servicos"] if s["os"] == os_)
    return s, next(i for i in s["itens"] if nome_parcial in i["item"])


def decidir(cli, h, it, acao="aprovar", obs=""):
    return cli.post(f"/api/itens/{it['id']}/decisao", json={"acao": acao, "obs": obs, "versao": it["versao"]}, headers=h)


def test_painel_exige_login(cliente):
    assert cliente.get("/api/painel").status_code == 401


def test_painel_agrupa_por_servico(cliente):
    entrar(cliente, "hely")
    p = cliente.get("/api/painel").json()
    assert len(p["servicos"]) == 11
    s = next(s for s in p["servicos"] if s["os"] == "71741916")
    assert (len(s["itens"]), s["cls"], s["mix"]) == (4, "Misto", "3 peças · 1 material")
    assert s["agora"]["nome"] == "Classificação PCM"
    assert [f["chave"] for f in p["fases"]] == ["relatorio", "nivel:0", "nivel:1", "whats", "pedido", "fim", "reprovado"]
    assert sum(f["qtd"] for f in p["fases"]) == 15
    assert all(i["minha_vez"] for i in s["itens"])
    assert "task_url" not in s


def test_fluxo_dois_niveis(cliente):
    h = entrar(cliente, "hely")
    _, it = _item(cliente, "71741916", "Filtro secador")
    assert decidir(cliente, h, it).json()["fase_nome"] == "Nível 2"
    assert decidir(cliente, h, it).status_code == 409   # versão velha
    h2 = entrar(cliente, "renato")
    _, it = _item(cliente, "71741916", "Filtro secador")
    assert it["minha_vez"] and not it["pode_reclassificar"]
    assert decidir(cliente, h2, it).json()["fase"] == "pedido"
    ev = cliente.get(f"/api/itens/{it['id']}/eventos").json()
    assert [(e["de"], e["para"], e["quem"]) for e in ev] == [("Nível 1", "Nível 2", "hely"), ("Nível 2", "Pedido", "renato")]


def test_quem_nao_esta_no_nivel_nao_decide(cliente):
    h = entrar(cliente, "renato")
    _, it = _item(cliente, "71741916", "Filtro secador")
    r = decidir(cliente, h, it)
    assert r.status_code == 422 and "aguarda o Nível 1" in r.json()["detail"]


def test_escrita_sem_cabecalho_do_painel_e_recusada(cliente):
    entrar(cliente, "hely")
    _, it = _item(cliente, "71741916", "Filtro secador")
    r = cliente.post(f"/api/itens/{it['id']}/decisao", json={"acao": "aprovar", "versao": it["versao"]})
    assert r.status_code == 403


def test_a_definir_bloqueia_e_reclassificar_libera(cliente):
    h = entrar(cliente, "hely")
    _, it = _item(cliente, "82423841", "Disjuntor")
    r = decidir(cliente, h, it)
    assert r.status_code == 422 and "Contrato HGG e Pedido" in r.json()["detail"]
    assert cliente.post(f"/api/itens/{it['id']}/classificacao", json={"cls": "Pedido de compra", "versao": it["versao"]},
                        headers=h).status_code == 200
    _, it = _item(cliente, "82423841", "Disjuntor")
    assert decidir(cliente, h, it).json()["fase_nome"] == "Nível 2"


def test_contrato_so_para_hgg(cliente):
    h = entrar(cliente, "hely")
    _, it = _item(cliente, "82416811", "Motor")
    r = cliente.post(f"/api/itens/{it['id']}/classificacao", json={"cls": "Contrato HGG", "versao": it["versao"]}, headers=h)
    assert r.status_code == 422


def test_devolver_ao_agente_volta_para_a_fila_do_openclaw(cliente):
    h = entrar(cliente, "hely")
    _, it = _item(cliente, "82475965", "Rolamentos")
    assert decidir(cliente, h, it, "devolver", "Informe a quantidade de rolamentos").json()["fase"] == "relatorio"
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
    assert (novo["fase"], novo["qtd"]) == ("nivel", "2 un")


def test_niveis_nova_versao_vale_para_quem_entra_depois(cliente):
    h = entrar(cliente, "hely")
    n = cliente.get("/api/niveis").json()
    assert n["versao"] == 1 and n["pode_editar"]
    niveis = [{k: x[k] for k in ("papel", "usuario", "compra", "contrato", "ativo")} for x in n["niveis"]]
    niveis.append({"papel": "Autoriza o Pedido", "usuario": "celso", "compra": True, "contrato": False, "ativo": True})
    r = cliente.put("/api/niveis", json={"niveis": niveis, "contratos": {"HGG": True}}, headers=h)
    assert r.json()["versao"] == 2
    p = cliente.get("/api/painel").json()
    assert "nivel:2" in [f["chave"] for f in p["fases"]]
    # item que já estava na fila segue a rota 1 (dois níveis)
    _, it = _item(cliente, "82150519", "Condensador")
    assert len(it["trilha"]) == 2


def test_niveis_so_admin_edita(cliente):
    h = entrar(cliente, "renato")
    assert cliente.put("/api/niveis", json={"niveis": [], "contratos": {}}, headers=h).status_code == 403


def test_rotas_de_robo_exigem_token(cliente):
    assert cliente.get("/api/agente/pendentes").status_code == 401
    assert cliente.get("/api/agente/pendentes", headers={"Authorization": f"Bearer {RUN}"}).status_code == 401
    assert cliente.post("/run/coleta").status_code == 401
    assert cliente.post("/api/integracao/comercial", json={"registros": []}).status_code == 401
    assert cliente.get("/run/status", headers={"Authorization": f"Bearer {RUN}"}).json()["aguardando_agente"] == 0


def test_login_errado_e_freio(cliente):
    for _ in range(5):
        assert cliente.post("/api/login", json={"usuario": "hely", "senha": "errada-errada"}).status_code == 401
    assert cliente.post("/api/login", json={"usuario": "hely", "senha": "senha-de-teste-123"}).status_code == 429
