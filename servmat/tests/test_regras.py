import pytest

from servmat import regras as R


def test_n1_confirma_vai_para_n2():
    assert R.decidir("n1", R.PEDIDO, 1, "aprovar", "").fase == "n2"


def test_n1_nao_confirma_a_definir():
    with pytest.raises(R.ErroRegra, match="Contrato HGG e Pedido de compra"):
        R.decidir("n1", R.A_DEFINIR, 1, "aprovar", "")


def test_n2_aprova_contrato_vai_para_pedido_e_compra_para_solicitacao():
    assert R.decidir("n2", R.CONTRATO, 2, "aprovar", "").fase == "pedido"
    assert R.decidir("n2", R.PEDIDO, 2, "aprovar", "").fase == "whats"


def test_reprovar_e_devolver_exigem_motivo():
    for acao in ("reprovar", "devolver"):
        with pytest.raises(R.ErroRegra, match="motivo"):
            R.decidir("n1", R.PEDIDO, 1, acao, "  ")
    r = R.decidir("n2", R.PEDIDO, 2, "reprovar", "sem necessidade")
    assert (r.fase, r.reprovado_em) == ("reprovado", "n2")
    assert R.decidir("n1", R.PEDIDO, 1, "devolver", "x").fase == "relatorio"
    assert R.decidir("n2", R.PEDIDO, 2, "devolver", "x").fase == "n1"


def test_nivel_errado_nao_decide():
    with pytest.raises(R.ErroRegra, match="não no Nível 2"):
        R.decidir("n1", R.PEDIDO, 2, "aprovar", "")


def test_conflito_do_tecnico_exige_observacao():
    assert R.conflito_tecnico("Renato Bonfim", "Renato Bonfim")
    assert not R.conflito_tecnico("Mauricio Araujo", "Renato Bonfim")
    with pytest.raises(R.ErroRegra, match="técnico autor"):
        R.decidir("n2", R.PEDIDO, 2, "aprovar", "", conflito=True)
    assert R.decidir("n2", R.PEDIDO, 2, "aprovar", "conferido por foto", conflito=True).fase == "whats"


def test_agregacao_do_servico():
    assert R.fase_servico(["n2", "n1", "reprovado"]) == "n1"
    assert R.fase_servico(["reprovado"]) == "reprovado"
    assert R.resumo_classificacao([R.PEDIDO, R.CONTRATO, R.PEDIDO, R.CONTRATO]) == \
        ("Misto", "2 pedido de compra · 2 contrato")
    assert R.mix_natureza(["Peça", "Peça", "Peça", "Material"]) == "3 peças · 1 material"


def test_etapas_da_os_71741916():
    itens = [dict(fase="n1", cls=c, situacao="Necessário") for c in (R.PEDIDO, R.CONTRATO, R.PEDIDO, R.CONTRATO)]
    a = R.etapas_servico(itens, "Primeira data 02/11 08:00.")
    nomes = [e["nome"] for e in a["etapas"]]
    assert nomes == ["Programação inicial", "Classificação PCM", "Pedido", "Autorização de Celso",
                     "Aprovação do cliente", "Programação da execução", "Finalização", "Cobrança"]
    assert a["agora"]["nome"] == "Classificação PCM" and a["agora"]["pos"] == 2
    assert "dos 4 itens" in a["agora"]["txt"]


def test_etapas_tudo_contrato_aplicado():
    a = R.etapas_servico([dict(fase="n2", cls=R.CONTRATO, situacao="Aplicado")], "x")
    por_nome = {e["nome"]: e["estado"] for e in a["etapas"]}
    assert por_nome["Aprovação do cliente"] == "na"
    assert por_nome["Programação da execução"] == "na"
    assert por_nome["Finalização"] == "feito"


def test_trilha():
    assert [t["estado"] for t in R.trilha("n2", None)] == ["Aprovado", "Aguardando"]
    assert [t["estado"] for t in R.trilha("reprovado", "n2")] == ["Aprovado", "Reprovado"]
