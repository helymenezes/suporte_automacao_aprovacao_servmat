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
    conn.execute("UPDATE itens SET nivel_pos = 1, versao = 2 WHERE os = '82150519'")
    t = tarefa(tid=82150519, report="Condensador trocado")
    c, _ = central_falsa([t])
    r = coleta.coletar(conn, c, CFG)
    assert r.alertas == 1
    assert conn.execute("SELECT COUNT(*) FROM itens WHERE os = '82150519'").fetchone()[0] == 1


def test_central_manda_host_quando_configurado():
    vistos = []

    def enviar(metodo, url, cabecalhos, corpo):
        vistos.append(cabecalhos)
        return 200, b'{"result": {"entityList": [], "pagedSearchReturnData": {"totalItems": 0}}}'

    Central("http://central-gw:8080", "tok", transporte=enviar, host="login.exemplo.digital").get("/api/auvo/tasks/")
    Central("http://central-gw:8080", "tok", transporte=enviar, host="").get("/api/auvo/tasks/")
    assert vistos[0]["Host"] == "login.exemplo.digital"
    assert "Host" not in vistos[1]


def test_central_recusa_host_invalido():
    import pytest
    with pytest.raises(ValueError):
        Central("http://central-gw:8080", "tok", host="evil.com\r\nX: y")


CFG_Q = dict(CFG, perguntas_relato=["RELATO DO ATENDIMENTO", "Observação do técnico"])


def _com_respostas(report, respostas):
    t = tarefa(report=report)
    t["questionnaires"] = [{"answers": [{"questionDescription": q, "reply": r} for q, r in respostas]}]
    return t


def test_relato_vem_do_questionario_quando_report_vazio():
    t = _com_respostas("", [("Observação do técnico", "Máquina com correia danificada foi trocada pela correia A34")])
    assert coleta.mapear(t, CFG_Q)["relato"] == "Máquina com correia danificada foi trocada pela correia A34"


def test_relato_igual_no_report_e_no_questionario_entra_uma_vez():
    texto = "Rolamentos do motor com folga causando barulhos,precisa ser trocados !"
    t = _com_respostas(texto, [("RELATO DO ATENDIMENTO:", texto + " "), ("Observação do técnico", texto.upper())])
    assert coleta.mapear(t, CFG_Q)["relato"] == texto


def test_relato_fica_com_o_trecho_mais_completo_e_ignora_resposta_vazia():
    t = _com_respostas("Compressor em curto", [
        ("RELATO DO ATENDIMENTO:", "Compressor em curto, precisa ser trocado"),
        ("Observação do técnico", "."),
    ])
    assert coleta.mapear(t, CFG_Q)["relato"] == "Compressor em curto, precisa ser trocado"


def test_relato_junta_textos_diferentes_sem_a_resposta_de_peca():
    t = _com_respostas("Equipamento desmontado", [
        ("RELATO DO ATENDIMENTO:", "Equipamento desmontado pra troca do moto ventilador"),
        ("Observação do técnico", "Estava com ruídos, foi feita a troca do motor"),
        ("UTILIZOU ALGUMA PEÇA?:", "Foi trocado motor da turbina novo"),
    ])
    l = coleta.mapear(t, CFG_Q)
    assert l["relato"] == ("Equipamento desmontado pra troca do moto ventilador · "
                           "Estava com ruídos, foi feita a troca do motor")
    assert "turbina" not in l["relato"]


def test_sem_perguntas_relato_continua_so_com_o_report():
    t = _com_respostas("Foi trocado o capacitor", [("Observação do técnico", "outro texto")])
    assert coleta.mapear(t, CFG)["relato"] == "Foi trocado o capacitor"
