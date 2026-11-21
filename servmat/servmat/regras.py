"""
Regras puras do painel de peças, materiais e serviços (sem banco, sem rede).

- Fases de cada item: relatorio → nivel (posição 0, 1, 2… na rota do item) → whats (Pedido de compra: solicitação
  ao orçamentista) | pedido (contrato) → fim. Reprovado sai do fluxo e guarda o nível em que foi reprovado.
- A rota (níveis em ordem) é configurável na tela "Níveis de aprovação". Cada mudança cria uma versão nova; o item
  guarda a versão com que entrou. A rota de um item depende da classificação: contrato ou Pedido de compra.
- Um serviço é uma OS. A fase do serviço é a mais atrasada entre os itens vivos (não reprovados).
- O acompanhamento do serviço (etapas) é calculado dos itens, nunca guardado à parte.
- A decisão é sempre humana. O agente só sugere (ver agente.py).
"""
from __future__ import annotations

from dataclasses import dataclass

FASES = ("relatorio", "nivel", "whats", "pedido", "fim", "reprovado")
ORDEM = ("relatorio", "nivel", "whats", "pedido", "fim")
NOME_FASE = {
    "relatorio": "Relatório", "nivel": "Nível", "whats": "Solicitação", "pedido": "Pedido",
    "fim": "Concluído", "reprovado": "Reprovado",
}
QUEM_FASE = {
    "relatorio": "Validação pelo agente", "whats": "Enviada ao orçamentista", "pedido": "Pedido, cliente e nota",
    "fim": "Encerrado", "reprovado": "Com justificativa",
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
    pos: int | None = None
    reprovado_em: str | None = None


# ---------- rota ----------

def validar_niveis(niveis: list[dict], usuarios: set[str]) -> list[dict]:
    """Lista vinda da tela "Níveis de aprovação" → lista limpa. Erros vão para a tela."""
    if not isinstance(niveis, list) or not niveis:
        raise ErroRegra("A rota precisa de pelo menos um nível.")
    if len(niveis) > 8:
        raise ErroRegra("No máximo 8 níveis.")
    limpos = []
    for k, n in enumerate(niveis, 1):
        papel = " ".join(str(n.get("papel") or "").split())
        usuario = str(n.get("usuario") or "").strip().lower() or None
        if not 3 <= len(papel) <= 80:
            raise ErroRegra(f"Nível {k}: escreva o papel do nível (3 a 80 caracteres).")
        ativo = bool(n.get("ativo"))
        if ativo and usuario is None:
            raise ErroRegra(f"Nível {k}: escolha quem aprova antes de ligar o nível.")
        if usuario is not None and usuario not in usuarios:
            raise ErroRegra(f"Nível {k}: usuário {usuario} não existe ou está desativado.")
        compra, contrato = bool(n.get("compra")), bool(n.get("contrato"))
        if ativo and not (compra or contrato):
            raise ErroRegra(f"Nível {k}: um nível ligado precisa entrar na rota de Pedido, de Contrato ou das duas.")
        limpos.append({"papel": papel, "usuario": usuario, "compra": compra, "contrato": contrato, "ativo": ativo})
    if not any(n["ativo"] and n["compra"] for n in limpos):
        raise ErroRegra("A rota de Pedido de compra ficou sem nenhum nível ligado.")
    if not any(n["ativo"] and n["contrato"] for n in limpos):
        raise ErroRegra("A rota de Contrato ficou sem nenhum nível ligado.")
    return limpos


def rota_do_item(snapshot: list[dict], cls: str) -> list[dict]:
    """Níveis ligados da versão da rota do item, na ordem, para a classificação dele."""
    chave = "contrato" if cls == CONTRATO else "compra"
    return [n for n in snapshot if n.get("ativo") and n.get(chave)]


def apos_niveis(cls: str) -> str:
    return "pedido" if cls == CONTRATO else "whats"


def nome_fase(fase: str, pos: int | None) -> str:
    if fase == "nivel" and pos is not None:
        return f"Nível {pos + 1}"
    return NOME_FASE[fase]


def ajustar_posicao(fase: str, pos: int | None, rota: list[dict], cls: str) -> tuple[str, int | None]:
    """Depois de uma reclassificação a rota pode encurtar: posição além do fim → fase seguinte."""
    if fase == "nivel" and pos is not None and pos >= len(rota):
        return apos_niveis(cls), None
    return fase, pos


def decidir(fase: str, pos: int | None, cls: str, rota: list[dict], usuario: str, acao: str, obs: str,
            conflito: bool = False) -> Resultado:
    """Próxima fase de um item a partir da decisão de quem está no nível atual. Não toca em banco."""
    if acao not in ACOES:
        raise ErroRegra("Ação desconhecida.")
    if fase != "nivel" or pos is None or pos >= len(rota):
        raise ErroRegra(f"O item está em {nome_fase(fase, pos)}: não há decisão de nível pendente.")
    nivel = rota[pos]
    if nivel.get("usuario") != usuario:
        raise ErroRegra(f"Este item aguarda o Nível {pos + 1} ({nivel.get('nome') or nivel.get('usuario')}).")
    obs = (obs or "").strip()
    if acao in ("devolver", "reprovar") and not obs:
        raise ErroRegra("Escreva o motivo para reprovar ou devolver.")
    if conflito and not obs:
        raise ErroRegra("Você é o técnico autor desta OS. Registre uma observação para decidir.")
    if acao == "reprovar":
        return Resultado("reprovado", pos, reprovado_em=f"Nível {pos + 1}")
    if acao == "devolver":
        return Resultado("relatorio", None) if pos == 0 else Resultado("nivel", pos - 1)
    if pos == 0 and cls == A_DEFINIR:
        raise ErroRegra("Escolha entre Contrato HGG e Pedido de compra antes de confirmar.")
    if pos + 1 < len(rota):
        return Resultado("nivel", pos + 1)
    return Resultado(apos_niveis(cls), None)


def pode_reclassificar(fase: str, pos: int | None, rota: list[dict], usuario: str, cls: str) -> None:
    if cls not in CLASSIFICACOES:
        raise ErroRegra("Classificação inválida.")
    if fase != "nivel" or pos != 0 or not rota or rota[0].get("usuario") != usuario:
        raise ErroRegra("Só o 1º nível corrige a classificação, e só enquanto o item está nele.")


def trilha(fase: str, pos: int | None, rota: list[dict]) -> list[dict]:
    """Situação de cada nível da rota do item: Aprovado, Aguardando, Reprovado ou —."""
    saida = []
    for k, n in enumerate(rota):
        estado = "—"
        if fase in POSTERIORES:
            estado = "Aprovado"
        elif fase == "nivel" and pos is not None:
            estado = "Aprovado" if k < pos else ("Aguardando" if k == pos else "—")
        elif fase == "reprovado" and pos is not None:
            estado = "Aprovado" if k < pos else ("Reprovado" if k == pos else "—")
        saida.append({"nivel": f"Nível {k + 1}", "quem": n.get("nome") or n.get("usuario") or "—",
                      "papel": n.get("papel", ""), "estado": estado})
    return saida


# ---------- serviço ----------

def chave_fase(fase: str, pos: int | None) -> tuple[int, int]:
    return (ORDEM.index(fase), pos or 0) if fase in ORDEM else (len(ORDEM), 0)


def fase_servico(itens: list[dict]) -> tuple[str, int | None]:
    vivos = [i for i in itens if i["fase"] != "reprovado"]
    if not vivos:
        return "reprovado", None
    m = min(vivos, key=lambda i: chave_fase(i["fase"], i.get("nivel_pos")))
    return m["fase"], m.get("nivel_pos")


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


def _e(nome: str, estado: str, txt: str = "", prox: str = "", quem: str = "") -> dict:
    return {"nome": nome, "estado": estado, "txt": txt, "prox": prox, "quem": quem}


def etapas_servico(itens: list[dict], prog_txt: str, pedido: dict | None = None) -> dict:
    """Etapas do serviço inteiro. Cada item: fase, nivel_pos, nivel_quem, nivel_papel, cls, situacao.
    `pedido` (opcional): situação vinda do Acompanhamento do Pedido para as etapas depois da aprovação."""
    if not itens:
        return {"etapas": [], "agora": None}
    p = pedido or {}
    vivos = [i for i in itens if i["fase"] != "reprovado"]
    base = vivos or itens
    n = len(base)

    def dos(k: int) -> str:
        if k == n:
            return "do item" if n == 1 else f"dos {n} itens"
        return f"de {k} de {n} itens"

    algum_contrato = any(i["cls"] == CONTRATO for i in base)
    todos_contrato = all(i["cls"] == CONTRATO for i in base)
    algum_indefinido = any(i["cls"] == A_DEFINIR for i in base)
    todos_aplicados = all(i["situacao"] == "Aplicado" for i in base)
    internas = bool(vivos) and all(i["fase"] in POSTERIORES for i in vivos)
    em_nivel = [i for i in base if i["fase"] == "nivel"]

    if not vivos:
        cls = _e("Classificação PCM", "reprovado", "Todos os itens reprovados, com justificativa registrada.")
    elif any(i["fase"] == "relatorio" for i in base):
        cls = _e("Classificação PCM", "seminfo", "Sem informação: o relatório não descreve o serviço.",
                 "Corrigir o relatório no Auvo", "Técnico e PCM")
    elif em_nivel:
        primeiro = min(em_nivel, key=lambda i: i.get("nivel_pos") or 0)
        k = sum(1 for i in em_nivel if i.get("nivel_pos") == primeiro.get("nivel_pos"))
        quem = primeiro.get("nivel_quem") or "aprovador"
        cls = _e("Classificação PCM", "atual",
                 f"Aguardando {quem} no Nível {(primeiro.get('nivel_pos') or 0) + 1} {dos(k)}.",
                 primeiro.get("nivel_papel") or "Decidir", quem)
    else:
        cls = _e("Classificação PCM", "feito", "Níveis internos aprovaram.")

    lista = [_e("Programação inicial", "feito", prog_txt), cls]
    if not vivos:
        for nome in ("Pedido", "Aprovação do cliente", "Programação da execução", "Finalização", "Cobrança"):
            lista.append(_e(nome, "na", "Não se aplica · serviço reprovado."))
    else:
        solic = p.get("solicitacao") in ("ENVIADO", "SIMULADO")
        vinculado = p.get("vinculo") == "vinculado"
        if not internas:
            lista.append(_e("Pedido", "pendente", "Aguardando a classificação (contrato ou Pedido de compra)."
                            if algum_indefinido else "Aguardando os níveis internos para solicitar ao orçamentista."))
        elif vinculado:
            lista.append(_e("Pedido", "feito", f"Pedido {p.get('pedido_num') or ''} vinculado à OS.".replace("  ", " ")))
        elif solic:
            lista.append(_e("Pedido", "atual", "Solicitação enviada. Aguardando o Pedido ser criado e vinculado à OS.",
                            "Criar o Pedido e vincular à OS", "Orçamentista"))
        else:
            lista.append(_e("Pedido", "atual", "Aprovações internas concluídas. Solicitação pronta para o orçamentista.",
                            "Solicitar ao orçamentista", "PCM"))
        if algum_contrato:
            celso = p.get("celso") or ""
            lista.append(_e("Autorização de Celso", "feito" if celso == "autorizado" else
                            ("atual" if vinculado else "pendente"),
                            "Celso autorizou o Pedido." if celso == "autorizado" else "Depois do Pedido criado e vinculado à OS.",
                            "Autorizar o Pedido" if vinculado and celso != "autorizado" else "", "Celso" if vinculado else ""))
        if todos_contrato:
            lista.append(_e("Aprovação do cliente", "na", "Não se aplica · itens cobertos pelo contrato HGG."))
        else:
            aceite = p.get("aceite") or ""
            lista.append(_e("Aprovação do cliente", "feito" if aceite in ("aceito", "parcial") else
                            ("reprovado" if aceite == "recusado" else "pendente"),
                            {"aceito": "Cliente aceitou a proposta.", "parcial": "Aceite parcial: só os itens aceitos seguem.",
                             "recusado": "Cliente recusou a proposta."}.get(aceite,
                                                                            "Aguardando proposta. O retorno será acompanhado pela planilha.")))
        exe = p.get("execucao") or ""
        if todos_aplicados:
            lista.append(_e("Programação da execução", "na", "Não se aplica · itens já aplicados na visita de origem."))
            lista.append(_e("Finalização", "feito", "Aplicado na visita de origem."))
        else:
            lista.append(_e("Programação da execução", "feito" if exe in ("agendada", "concluida") else "pendente",
                            "Execução agendada." if exe in ("agendada", "concluida") else
                            ("A programar pelo PCM." if todos_contrato else "A agendar após autorização do cliente.")))
            lista.append(_e("Finalização", "feito" if exe == "concluida" else "pendente",
                            "Serviço executado." if exe == "concluida" else "Serviço pendente."))
        cob = p.get("cobranca") or ""
        lista.append(_e("Cobrança", "feito" if cob in ("ENVIADO", "SIMULADO") else "pendente",
                        "Cobrança solicitada ao orçamentista." if cob in ("ENVIADO", "SIMULADO") else
                        ("Envio ao faturamento após a autorização de Celso." if todos_contrato else
                         "Solicitar ao orçamentista após a execução do serviço autorizado.")))

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
    """O técnico autor da OS é o próprio aprovador do nível (ex.: OS 82447493, Renato Bonfim)."""
    t = " ".join((tecnico or "").casefold().split())
    partes = (nome_avaliador or "").casefold().split()
    if not t or not partes:
        return False
    return all(p in t for p in partes)
