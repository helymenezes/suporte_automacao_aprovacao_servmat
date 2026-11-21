import json
from datetime import datetime

from servmat import coleta
from servmat.central import Central

CFG = {"dias": 15, "campos": "taskID", "campo_relato": "report", "pergunta_utilizou": "Utilizou peça",
       "clientes": {"HGG": ["HGG"]}, "tipos": {"7": "Manutenção corretiva"}}


def tarefa(tid=91000001, report="Foi trocado o capacitor 35uF", status=5, cliente="2° ANDAR - HGG"):
    return {"taskID": tid, "taskStatus": status, "customerDescription": cliente, "taskType": 7, "report": report,
            "userToName": "Mauricio Araujo", "taskDate": "2026-11-18T08:00:00", "checkInDate": "2026-11-18T09:10:00",
            "taskUrl": "https://app.auvo.com.br/x?chave=SEGREDO",
            "questionnaires": [{"answers": [{"questionDescription": "Utilizou peça?", "reply": "Sim, capacitor"}]}]}


def central_falsa(tarefas):
    chamadas = []

    def enviar(metodo, url, cab, corpo):
        chamadas.append(url)
        return 200, json.dumps({"result": {"entityList": tarefas}}).encode()
    return Central("http://127.0.0.1:9", "tok", transporte=enviar), chamadas


def test_mapear():
    l = coleta.mapear(tarefa(), CFG)
    assert (l["os"], l["cliente"], l["tipo"], l["utilizou"]) == ("91000001", "HGG", "Manutenção corretiva", "Sim, capacitor")
    assert l["prog_txt"] == "Aberta em 18/11 08:00."
    assert coleta.mapear(tarefa(status=3), CFG) is None
    assert coleta.mapear(tarefa(cliente="OUTRO"), CFG) is None


def test_coleta_nova_igual_e_relato_corrigido(conn):
    c, chamadas = central_falsa([tarefa()])
    r = coleta.coletar(conn, c, CFG, datetime(2026, 11, 21, 6, 0))
    assert (r.novas, r.completa) == (1, True)
    assert "SEGREDO" not in "".join(chamadas)
    r = coleta.coletar(conn, c, CFG, datetime(2026, 11, 21, 7, 0))
    assert r.iguais == 1
    c2, _ = central_falsa([tarefa(report="Foi trocado o capacitor 45uF")])
    r = coleta.coletar(conn, c2, CFG, datetime(2026, 11, 21, 8, 0))
    assert r.reabertas == 1
    o = conn.execute("SELECT identificacao, rodada FROM os WHERE os = '91000001'").fetchone()
    assert (o["identificacao"], o["rodada"]) == ("pendente", 2)


def test_relato_mudou_depois_de_decisao_so_alerta(conn):
    conn.execute("UPDATE itens SET fase = 'n2', versao = 2 WHERE os = '82150519'")
    t = tarefa(tid=82150519, report="Condensador trocado")
    c, _ = central_falsa([t])
    r = coleta.coletar(conn, c, CFG)
    assert r.alertas == 1
    assert conn.execute("SELECT COUNT(*) FROM itens WHERE os = '82150519'").fetchone()[0] == 1
