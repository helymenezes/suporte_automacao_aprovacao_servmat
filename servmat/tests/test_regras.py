import pytest

from servmat import regras as R

ROTA = [dict(papel="Confirma a sugestão", usuario="hely", nome="Hely R Menezes", compra=True, contrato=True, ativo=True),
        dict(papel="Avaliação técnica", usuario="renato", nome="Renato Bonfim", compra=True, contrato=True, ativo=True),
        dict(papel="Autoriza o Pedido", usuario="gerencia", nome="Gerência", compra=True, contrato=False, ativo=True),
        dict(papel="Desligado", usuario="x", nome="X", compra=True, contrato=True, ativo=False)]


def test_rota_depende_da_classificacao():
    assert [n["usuario"] for n in R.rota_do_item(ROTA, R.PEDIDO)] == ["hely", "renato", "gerencia"]
    assert [n["usuario"] for n in R.rota_do_item(ROTA, R.CONTRATO)] == ["hely", "renato"]


def test_caminho_completo_pedido_de_compra():
    rota = R.rota_do_item(ROTA, R.PEDIDO)
    assert R.decidir("nivel", 0, R.PEDIDO, rota, "hely", "aprovar", "") == R.Resultado("nivel", 1)
    assert R.decidir("nivel", 1, R.PEDIDO, rota, "renato", "aprovar", "") == R.Resultado("nivel", 2)
    assert R.decidir("nivel", 2, R.PEDIDO, rota, "gerencia", "aprovar", "").fase == "whats"


def test_contrato_termina_no_pedido():
    rota = R.rota_do_item(ROTA, R.CONTRATO)
    assert R.decidir("nivel", 1, R.CONTRATO, rota, "renato", "aprovar", "").fase == "pedido"


def test_so_quem_esta_no_nivel_decide():
    with pytest.raises(R.ErroRegra, match="aguarda o Nível 1"):
        R.decidir("nivel", 0, R.PEDIDO, R.rota_do_item(ROTA, R.PEDIDO), "renato", "aprovar", "")


def test_primeiro_nivel_nao_confirma_a_definir():
    with pytest.raises(R.ErroRegra, match="Contrato HGG e Pedido de compra"):
        R.decidir("nivel", 0, R.A_DEFINIR, R.rota_do_item(ROTA, R.A_DEFINIR), "hely", "aprovar", "")


def test_reprovar_e_devolver():
    rota = R.rota_do_item(ROTA, R.PEDIDO)
    for acao in ("reprovar", "devolver"):
        with pytest.raises(R.ErroRegra, match="motivo"):
            R.decidir("nivel", 0, R.PEDIDO, rota, "hely", acao, "  ")
    assert R.decidir("nivel", 1, R.PEDIDO, rota, "renato", "reprovar", "x") == R.Resultado("reprovado", 1, "Nível 2")
    assert R.decidir("nivel", 0, R.PEDIDO, rota, "hely", "devolver", "x").fase == "relatorio"
    assert R.decidir("nivel", 1, R.PEDIDO, rota, "renato", "devolver", "x") == R.Resultado("nivel", 0)


def test_conflito_do_tecnico_exige_observacao():
    rota = R.rota_do_item(ROTA, R.PEDIDO)
    assert R.conflito_tecnico("Renato Bonfim", "Renato Bonfim")
    with pytest.raises(R.ErroRegra, match="técnico autor"):
        R.decidir("nivel", 1, R.PEDIDO, rota, "renato", "aprovar", "", conflito=True)


def test_reclassificar_pode_encurtar_a_rota():
    # Item de Pedido no 3º nível vira contrato (rota de 2 níveis): passa direto para o Pedido.
    assert R.ajustar_posicao("nivel", 2, R.rota_do_item(ROTA, R.CONTRATO), R.CONTRATO) == ("pedido", None)
    with pytest.raises(R.ErroRegra, match="1º nível"):
        R.pode_reclassificar("nivel", 1, R.rota_do_item(ROTA, R.PEDIDO), "renato", R.CONTRATO)


def test_validar_niveis():
    ok = R.validar_niveis([dict(papel="Confirma", usuario="hely", compra=True, contrato=True, ativo=True)], {"hely"})
    assert ok[0]["usuario"] == "hely"
    with pytest.raises(R.ErroRegra, match="escolha quem aprova"):
        R.validar_niveis([dict(papel="Confirma", usuario="", compra=True, contrato=True, ativo=True)], {"hely"})
    with pytest.raises(R.ErroRegra, match="Contrato ficou sem"):
        R.validar_niveis([dict(papel="Confirma", usuario="hely", compra=True, contrato=False, ativo=True)], {"hely"})


def test_agregacao_do_servico():
    itens = [dict(fase="nivel", nivel_pos=1), dict(fase="nivel", nivel_pos=0), dict(fase="reprovado", nivel_pos=0)]
    assert R.fase_servico(itens) == ("nivel", 0)
    assert R.resumo_classificacao([R.PEDIDO, R.CONTRATO, R.PEDIDO, R.CONTRATO]) == \
        ("Misto", "2 pedido de compra · 2 contrato")
    assert R.mix_natureza(["Peça", "Peça", "Peça", "Material"]) == "3 peças · 1 material"


def test_etapas_da_os_71741916():
    itens = [dict(fase="nivel", nivel_pos=0, nivel_quem="Hely R Menezes", nivel_papel="Confirmar a sugestão",
                  cls=c, situacao="Necessário") for c in (R.PEDIDO, R.CONTRATO, R.PEDIDO, R.CONTRATO)]
    a = R.etapas_servico(itens, "Primeira data 02/11 08:00.")
    assert [e["nome"] for e in a["etapas"]] == [
        "Programação inicial", "Classificação PCM", "Pedido", "Autorização de Celso", "Aprovação do cliente",
        "Programação da execução", "Finalização", "Cobrança"]
    assert a["agora"]["nome"] == "Classificação PCM" and "Hely R Menezes no Nível 1 dos 4 itens" in a["agora"]["txt"]


def test_etapas_acompanham_o_pedido():
    itens = [dict(fase="whats", nivel_pos=None, cls=R.PEDIDO, situacao="Necessário")]
    a = R.etapas_servico(itens, "x", {"solicitacao": "ENVIADO", "vinculo": "vinculado", "pedido_num": "4512",
                                      "aceite": "aceito", "execucao": "concluida", "cobranca": ""})
    est = {e["nome"]: e["estado"] for e in a["etapas"]}
    assert est["Pedido"] == est["Aprovação do cliente"] == est["Finalização"] == "feito"
    assert a["agora"]["nome"] == "Cobrança"


def test_trilha():
    rota = R.rota_do_item(ROTA, R.CONTRATO)
    assert [t["estado"] for t in R.trilha("nivel", 1, rota)] == ["Aprovado", "Aguardando"]
    assert [t["estado"] for t in R.trilha("reprovado", 1, rota)] == ["Aprovado", "Reprovado"]
    assert [t["estado"] for t in R.trilha("pedido", None, rota)] == ["Aprovado", "Aprovado"]
