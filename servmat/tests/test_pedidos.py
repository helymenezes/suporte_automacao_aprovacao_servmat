import json
from pathlib import Path

from conftest import INTEG, entrar

from servmat import banco, envio


def aprovar_os(cli, os_):
    """Hely e Renato aprovam todos os itens da OS (classificando 'A definir' como Pedido de compra)."""
    for usuario in ("hely", "renato"):
        h = entrar(cli, usuario)
        s = next(x for x in cli.get("/api/painel").json()["servicos"] if x["os"] == os_)
        for it in s["itens"]:
            v = it["versao"]
            if it["cls"] == "A definir":
                cli.post(f"/api/itens/{it['id']}/classificacao", json={"cls": "Pedido de compra", "versao": v}, headers=h)
                v += 1
            r = cli.post(f"/api/itens/{it['id']}/decisao", json={"acao": "aprovar", "versao": v}, headers=h)
            assert r.status_code == 200, r.text


def linha(cli, os_, tipo):
    return next(l for l in cli.get("/api/pedidos").json()["linhas"] if l["os"] == os_ and l["tipo"] == tipo)


def test_do_pedido_a_cobranca_simulada(cliente, conn):
    aprovar_os(cliente, "82150519")              # condensador, Pedido de compra
    h = entrar(cliente, "hely")
    l = linha(cliente, "82150519", "compra")
    assert (l["grupo"], l["pode_solicitar"]) == ("solicitar", True)
    e = cliente.post("/api/pedidos/82150519/compra/solicitar", headers=h).json()
    assert e["estado"] == "SIMULADO" and "Solicitação de orçamento" in e["texto"]
    # repetir não duplica
    assert cliente.post("/api/pedidos/82150519/compra/solicitar", headers=h).status_code == 422
    assert conn.execute("SELECT COUNT(*) FROM envios").fetchone()[0] == 1
    assert linha(cliente, "82150519", "compra")["grupo"] == "vinc"
    # cobrança antes da hora: recusada
    assert cliente.post("/api/pedidos/82150519/compra/cobranca", headers=h).status_code == 422
    # sistema comercial e planilha chegam pela integração
    t = {"Authorization": f"Bearer {INTEG}"}
    r = cliente.post("/api/integracao/comercial", headers=t, json={"registros": [
        {"os": "82150519", "tipo": "compra", "pedido_num": "4512", "vinculo": "vinculado"},
        {"os": "00000000", "tipo": "compra", "vinculo": "vinculado"}]}).json()
    assert r["gravadas"] == 1 and "não está no painel" in r["erros"][0]
    assert cliente.post("/api/integracao/planilha", headers=t,
                        json={"registros": [{"os": "82150519", "tipo": "compra", "pedido_num": "x"}]}).json()["gravadas"] == 0
    cliente.post("/api/integracao/planilha", headers=t, json={"registros": [{"os": "82150519", "tipo": "compra", "aceite": "aceito"}]})
    assert linha(cliente, "82150519", "compra")["grupo"] == "exec"
    # registro manual do PCM
    assert cliente.post("/api/pedidos/82150519/compra/registro", headers=h,
                        json={"campos": {"execucao": "concluida"}}).status_code == 200
    assert linha(cliente, "82150519", "compra")["grupo"] == "cob"
    assert cliente.post("/api/pedidos/82150519/compra/cobranca", headers=h).json()["estado"] == "SIMULADO"
    assert linha(cliente, "82150519", "compra")["grupo"] == "cobs"
    fases = [r[0] for r in conn.execute("SELECT fase FROM itens WHERE os = '82150519'")]
    assert fases == ["fim"]


def test_so_admin_pede_ao_orcamentista(cliente):
    aprovar_os(cliente, "82150519")
    h = entrar(cliente, "renato")
    assert cliente.post("/api/pedidos/82150519/compra/solicitar", headers=h).status_code == 403


def test_aplicado_aguardando_mostra_vinculo_a_conferir(cliente):
    entrar(cliente, "hely")
    assert linha(cliente, "82416811", "compra")["grupo"] == "vinc"   # motor já trocado na visita
    assert linha(cliente, "71741916", "compra")["grupo"] == "class"


# ---------- envio real (WAHA falso) ----------

class WahaFalso:
    def __init__(self, modo):
        self.modo, self.chamadas = modo, []

    def __call__(self, metodo, url, cab, corpo):
        self.chamadas.append((metodo, url))
        assert cab["X-Api-Key"] == "chave"
        if "check-exists" in url:
            return 200, json.dumps({"numberExists": True, "chatId": "556299990000@c.us"}).encode()
        if self.modo == "ok":
            return 201, json.dumps({"id": {"_serialized": "true_556299990000@c.us_ABC"}}).encode()
        if self.modo == "erro":
            return 500, b"{}"
        raise envio.EnvioIncerto("sem resposta do WAHA")


def cfg_real():
    return envio.ConfigEnvio(True, "http://127.0.0.1:3001", "chave", "default", "62 99999-0000", "Orçamentista")


def test_envio_real_com_recibo(conn):
    w = WahaFalso("ok")
    e = envio.solicitar(conn, cfg_real(), "82150519", "compra", "solicitacao", "hely", "texto",
                        envio.Waha("http://127.0.0.1:3001", "chave", transporte=w))
    assert (e["estado"], e["recibo"]) == ("ENVIADO", "true_556299990000@c.us_ABC")


def test_incerto_nunca_reenvia_sozinho(conn):
    w = WahaFalso("cai")
    waha = envio.Waha("http://127.0.0.1:3001", "chave", transporte=w)
    e = envio.solicitar(conn, cfg_real(), "82150519", "compra", "solicitacao", "hely", "texto", waha)
    assert e["estado"] == "INCERTO"
    envios_antes = len([c for c in w.chamadas if "sendText" in c[1]])
    e2 = envio.solicitar(conn, cfg_real(), "82150519", "compra", "solicitacao", "hely", "texto", waha)
    assert e2["estado"] == "INCERTO" and len([c for c in w.chamadas if "sendText" in c[1]]) == envios_antes
    assert envio.resolver_incerto(conn, e["id"], "nao_entregue", "hely")["estado"] == "FALHOU"
    w.modo = "ok"
    assert envio.solicitar(conn, cfg_real(), "82150519", "compra", "solicitacao", "hely", "texto", waha)["estado"] == "ENVIADO"


def test_falha_pode_tentar_de_novo(conn):
    w = WahaFalso("erro")
    waha = envio.Waha("http://127.0.0.1:3001", "chave", transporte=w)
    assert envio.solicitar(conn, cfg_real(), "82150519", "compra", "cobranca", "hely", "t", waha)["estado"] == "FALHOU"
    w.modo = "ok"
    e = envio.solicitar(conn, cfg_real(), "82150519", "compra", "cobranca", "hely", "t", waha)
    assert (e["estado"], e["tentativas"]) == ("ENVIADO", 2)


# ---------- áudio ----------

def test_audio_sem_transcricao(cliente, cfg):
    h = entrar(cliente, "hely")
    s = next(x for x in cliente.get("/api/painel").json()["servicos"] if x["os"] == "82150519")
    it = s["itens"][0]
    r = cliente.post(f"/api/itens/{it['id']}/audio", content=b"OggS\x00fake", headers={**h, "Content-Type": "audio/webm;codecs=opus"})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["transcricao"] == "" and a["transcricao_ligada"] is False
    assert cliente.get(f"/api/audios/{a['id']}").content == b"OggS\x00fake"
    assert len(list(Path(cfg.pasta_audios).iterdir())) == 1
    r = cliente.post(f"/api/itens/{it['id']}/decisao", headers=h,
                     json={"acao": "aprovar", "versao": it["versao"], "obs": "[áudio] conferido", "audio_id": a["id"]})
    assert r.status_code == 200
    assert cliente.post(f"/api/itens/{it['id']}/audio", content=b"x", headers={**h, "Content-Type": "text/plain"}).status_code == 422


def test_audio_de_outro_item_e_recusado(cliente):
    h = entrar(cliente, "hely")
    p = cliente.get("/api/painel").json()["servicos"]
    a_it = next(x for x in p if x["os"] == "82150519")["itens"][0]
    b_it = next(x for x in p if x["os"] == "82475965")["itens"][0]
    a = cliente.post(f"/api/itens/{a_it['id']}/audio", content=b"abc", headers={**h, "Content-Type": "audio/ogg"}).json()
    r = cliente.post(f"/api/itens/{b_it['id']}/decisao", headers=h,
                     json={"acao": "aprovar", "versao": b_it["versao"], "audio_id": a["id"]})
    assert r.status_code == 422


def test_rota_padrao_nasce_com_os_usuarios(conn):
    versao, rota = banco.rota_atual(conn)
    assert versao == 1 and [n["nome"] for n in rota] == ["Hely R Menezes", "Renato Bonfim"]
