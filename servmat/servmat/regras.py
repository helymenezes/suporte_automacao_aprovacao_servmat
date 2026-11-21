"""
Regras puras do painel de peças, materiais e serviços (sem banco, sem rede).

- Fases de cada item: relatorio → n1 (Hely) → n2 (Renato) → whats (solicitação ao orçamentista) | pedido (contrato)
  → fim. Reprovado sai do fluxo com a fase em que foi reprovado.
- Um serviço é uma OS. A fase do serviço é a mais atrasada entre os itens vivos (não reprovados).
- O acompanhamento do serviço (etapas) é calculado dos itens, nunca guardado à parte.
- A decisão de aprovação é sempre humana. O agente só sugere (ver agente.py).
"""
from __future__ import annotations

from dataclasses import dataclass

FASES = ("relatorio", "n1", "n2", "whats", "pedido", "fim", "reprovado")
ORDEM = ("relatorio", "n1", "n2", "whats", "pedido", "fim")
NOME_FASE = {
    "relatorio": "Relatório", "n1": "Nível 1", "n2": "Nível 2", "whats": "Solicitação",
    "pedido": "Pedido", "fim": "Concluído", "reprovado": "Reprovado",
}
QUEM_FASE = {
    "relatorio": "Validação pelo agente", "n1": "Hely R Menezes", "n2": "Renato · avaliação técnica",
    "whats": "Enviada ao orçamentista", "pedido": "Pedido, cliente e nota", "fim": "Encerrado",
    "reprovado": "Com justificativa",
}
CONTRATO = "Contrato HGG"
PEDIDO = "Pedido de compra"
A_DEFINIR = "A definir"
CLASSIFICACOES = (CONTRATO, PEDIDO, A_DEFINIR)
NATUREZAS = ("Peça", "Material", "Serviço", "Não identificado")
SITUACOES = ("Aplicado", "Necessário", "Inconclusivo")
CONFIANCAS = ("Alta", "Média", "Baixa")
ACOES = ("aprovar", "devolver", "reprovar")
POSTERIORES = ("whats", "pedido", "fim")

_NAT_PLURAL = {"Peça": ("peça", "peças"), "Material": ("material", "materiais"),
               "Serviço": ("serviço", "serviços"), "Não identificado": ("não identificado", "não identificados")}
_CLS_CURTO = {CONTRATO: "contrato", PEDIDO: "pedido de compra", A_DEFINIR: "a definir"}


class ErroRegra(Exception):
    """Decisão que a regra não permite. A mensagem vai para a tela como está."""


@dataclass(frozen=True)
class Resultado:
    fase: str
    reprovado_em: str | None = None


def decidir(fase: str, cls: str, nivel: int, acao: str, obs: str, conflito: bool = False) -> Resultado:
    """Próxima fase de um item a partir da decisão de um nível. Não toca em banco."""
    if acao not in ACOES:
        raise ErroRegra("Ação desconhecida.")
    esperado = {1: "n1", 2: "n2"}.get(nivel)
    if esperado is None:
        raise ErroRegra("Nível sem permissão para decidir.")
    if fase != esperado:
        raise ErroRegra(f"O item está em {NOME_FASE.get(fase, fase)}, não no Nível {nivel}.")
    obs = (obs or "").strip()
    if acao in ("devolver", "reprovar") and not obs:
        raise ErroRegra("Escreva o motivo para reprovar ou devolver.")
    if conflito and not obs:
        raise ErroRegra("Você é o técnico autor desta OS. Registre uma observação para decidir.")
    if acao == "reprovar":
        return Resultado("reprovado", reprovado_em=fase)
    if acao == "devolver":
        return Resultado("relatorio" if fase == "n1" else "n1")
    if fase == "n1":
        if cls == A_DEFINIR:
            raise ErroRegra("Escolha entre Contrato HGG e Pedido de compra antes de confirmar.")
        return Resultado("n2")
    return Resultado("pedido" if cls == CONTRATO else "whats")


def pode_reclassificar(fase: str, nivel: int, cls: str) -> None:
    if nivel != 1 or fase != "n1":
        raise ErroRegra("Só o Nível 1 corrige a classificação, e só enquanto o item está no Nível 1.")
    if cls not in CLASSIFICACOES:
        raise ErroRegra("Classificação inválida.")


def fase_servico(fases: list[str]) -> str:
    vivas = [f for f in fases if f != "reprovado"]
    if not vivas:
        return "reprovado"
    return min(vivas, key=ORDEM.index)


def resumo_classificacao(clss: list[str]) -> tuple[str, str]:
    contagem: dict[str, int] = {}
    for c in clss:
        contagem[c] = contagem.get(c, 0) + 1
    if len(contagem) == 1:
        return next(iter(contagem)), ""
    return "Misto", " · ".join(f"{n} {_CLS_CURTO.get(c, c)}" for c, n in contagem.items())


def mix_natureza(naturezas: list[str]) -> str:
    contagem: dict[str, int] = {}
    for n in naturezas:
        contagem[n] = contagem.get(n, 0) + 1
    partes = []
    for nat, n in contagem.items():
        um, varios = _NAT_PLURAL.get(nat, (nat, nat))
        partes.append(f"{n} {um if n == 1 else varios}")
    return " · ".join(partes)


def trilha(fase: str, reprovado_em: str | None) -> list[dict]:
    """Situação de cada nível para um item: Aprovado, Aguardando, Reprovado ou —."""
    saida = []
    idx = ORDEM.index(fase) if fase in ORDEM else None
    for chave, nome, quem in (("n1", "Nível 1", "Hely R Menezes"), ("n2", "Nível 2", "Renato")):
        li = ORDEM.index(chave)
        estado = "—"
        if fase == "reprovado":
            ri = ORDEM.index(reprovado_em) if reprovado_em in ORDEM else -1
            estado = "Aprovado" if li < ri else ("Reprovado" if li == ri else "—")
        elif idx is not None and idx > li:
            estado = "Aprovado"
        elif idx == li:
            estado = "Aguardando"
        saida.append({"nivel": nome, "quem": quem, "estado": estado})
    return saida


def _e(nome: str, estado: str, txt: str = "", prox: str = "", quem: str = "") -> dict:
    return {"nome": nome, "estado": estado, "txt": txt, "prox": prox, "quem": quem}


def etapas_servico(itens: list[dict], prog_txt: str) -> dict:
    """Etapas do serviço inteiro (todos os itens da OS). Cada item: fase, cls, situacao."""
    if not itens:
        return {"etapas": [], "agora": None}
    vivos = [i for i in itens if i["fase"] != "reprovado"]
    base = vivos or itens
    n = len(base)

    def conta(f: str) -> int:
        return sum(1 for i in base if i["fase"] == f)

    def dos(k: int) -> str:
        if k == n:
            return "do item" if n == 1 else f"dos {n} itens"
        return f"de {k} de {n} itens"

    algum_contrato = any(i["cls"] == CONTRATO for i in base)
    todos_contrato = all(i["cls"] == CONTRATO for i in base)
    algum_indefinido = any(i["cls"] == A_DEFINIR for i in base)
    todos_aplicados = all(i["situacao"] == "Aplicado" for i in base)
    internas = bool(vivos) and all(i["fase"] in POSTERIORES for i in vivos)

    if not vivos:
        cls = _e("Classificação PCM", "reprovado", "Todos os itens reprovados, com justificativa registrada.")
    elif conta("relatorio"):
        cls = _e("Classificação PCM", "seminfo", "Sem informação: o relatório não descreve o serviço.",
                 "Corrigir o relatório no Auvo", "Técnico e PCM")
    elif conta("n1"):
        cls = _e("Classificação PCM", "atual", f"Aguardando Hely confirmar a classificação sugerida {dos(conta('n1'))}.",
                 "Confirmar ou corrigir a sugestão", "Hely R Menezes")
    elif conta("n2"):
        cls = _e("Classificação PCM", "atual",
                 f"Hely confirmou. Aguardando a avaliação técnica de Renato {dos(conta('n2'))}.",
                 "Avaliação técnica", "Renato")
    else:
        cls = _e("Classificação PCM", "feito", "Hely e Renato aprovaram.")

    lista = [_e("Programação inicial", "feito", prog_txt), cls]
    if not vivos:
        for nome in ("Pedido", "Aprovação do cliente", "Programação da execução", "Finalização", "Cobrança"):
            lista.append(_e(nome, "na", "Não se aplica · serviço reprovado."))
    else:
        if internas:
            lista.append(_e("Pedido", "atual",
                            "Aprovações internas concluídas. Aguardando o Pedido ser criado e vinculado à OS."
                            if todos_contrato else "Solicitação pronta para o orçamentista.",
                            "Criar o Pedido e vincular à OS" if todos_contrato else "Solicitar orçamento ao orçamentista",
                            "Orçamentista" if todos_contrato else "PCM"))
        else:
            lista.append(_e("Pedido", "pendente", "Aguardando a classificação (contrato ou Pedido de compra)."
                            if algum_indefinido else "Aguardando a classificação para solicitar ao orçamentista."))
        if algum_contrato:
            lista.append(_e("Autorização de Celso", "pendente", "Depois do Pedido criado e vinculado à OS."))
        lista.append(_e("Aprovação do cliente", "na", "Não se aplica · itens cobertos pelo contrato HGG.")
                     if todos_contrato else
                     _e("Aprovação do cliente", "pendente", "Aguardando proposta. O retorno será acompanhado pela planilha."))
        lista.append(_e("Programação da execução", "na", "Não se aplica · itens já aplicados na visita de origem.")
                     if todos_aplicados else
                     _e("Programação da execução", "pendente",
                        "A programar pelo PCM." if todos_contrato else "A agendar após autorização do cliente."))
        lista.append(_e("Finalização", "feito", "Aplicado na visita de origem.")
                     if todos_aplicados else _e("Finalização", "pendente", "Serviço pendente."))
        lista.append(_e("Cobrança", "pendente", "Envio ao faturamento após a autorização de Celso."
                        if todos_contrato else "Solicitar ao orçamentista após a execução do serviço autorizado."))

    pos = next((k for k, e in enumerate(lista) if e["estado"] in ("atual", "seminfo", "reprovado")), None)
    if pos is None:
        pos = next((k for k, e in enumerate(lista) if e["estado"] == "pendente"), len(lista) - 1)
    agora = dict(lista[pos], pos=pos + 1, total=len(lista))
    return {"etapas": lista, "agora": agora}


def etapas_aguardando_agente(prog_txt: str) -> dict:
    """OS coletada que o agente ainda não leu (sem itens)."""
    lista = [_e("Programação inicial", "feito", prog_txt),
             _e("Classificação PCM", "atual", "Aguardando o agente identificar os itens do relatório.",
                "Identificar materiais, peças e serviços", "Agente OpenClaw")]
    for nome in ("Pedido", "Aprovação do cliente", "Programação da execução", "Finalização", "Cobrança"):
        lista.append(_e(nome, "pendente", "Depende da identificação."))
    return {"etapas": lista, "agora": dict(lista[1], pos=2, total=len(lista))}


def conflito_tecnico(tecnico: str, nome_avaliador: str) -> bool:
    """O técnico autor da OS é o próprio avaliador do Nível 2 (ex.: OS 82447493, Renato Bonfim)."""
    t = " ".join((tecnico or "").casefold().split())
    partes = (nome_avaliador or "").casefold().split()
    if not t or not partes:
        return False
    return all(p in t for p in partes)
