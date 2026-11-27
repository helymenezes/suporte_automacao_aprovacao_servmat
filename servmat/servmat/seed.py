"""
Carga do esboço: as 11 OS reais lidas pela central em 20/11/2026 23:56 e as 15 sugestões classificadas à mão no
desenho do painel. Serve para conferir o painel antes da primeira coleta real. Nenhum item vem aprovado.
"""
from __future__ import annotations

import sqlite3

from . import agente, banco

M = "Mauricio Araujo"
DIV = 'Divergência: o campo diz "Nao", mas o relato descreve troca'
REL_71741916 = ("Compressor do circuito 2. Precisa ser trocado esta em curto 01 filtro secador 210x1/2 rosca 04 varetas "
                "de solda prata 45% 02 varetas fosfoco 01 contactora 220v 40A 02 metros de nitrogênio")

OS = [
    dict(os="71741916", cliente="HGG", area="5° ANDAR - HGG", tipo="PMOC", tecnico=M, relato=REL_71741916,
         utilizou="", prog_txt="Primeira data 02/11 08:00. 6 reagendamentos pela rotina.",
         prog_meta=f"Visita em 11/11 07:16 · {M} · Auvo (histórico de reagendamento) e PCM Pro (competência 02/11)"),
    dict(os="71742023", cliente="HGG", area="5° ANDAR - HGG", tipo="PMOC", tecnico=M,
         relato="Máquina com correia danificada foi trocada pela correia A34 funcionando normalmente com bom rendimento",
         utilizou="", prog_txt="Primeira data 23/11 08:00; trazida para 03/11 em 31/10. 6 reagendamentos pela rotina.",
         prog_meta=f"Visita em 12/11 14:25 · {M} · Auvo e PCM Pro (competência 03/11)"),
    dict(os="82288641", cliente="HGG", area="TERREO - HGG", tipo="Manutenção corretiva", tecnico=M,
         relato="Isolamento com infiltração foi substituído por outro Isolamento, máquina, limpa funcionando sem pingar!",
         utilizou="1 metros de isolamento 3/4", prog_txt="Aberta em 09/11 11:14.", prog_meta=f"Visita em 09/11 12:28 · {M} · Auvo"),
    dict(os="82774691", cliente="HGG", area="1° ANDAR - HGG", tipo="Manutenção corretiva", tecnico=M,
         relato="Máquina limpa com produtos químicos internos e externos e trocados os filtros sem vazamento",
         utilizou="Nao", origem="WA-HGG-000310_923235",
         prog_txt="Aberta em 19/11 08:53, a partir do pedido WA-HGG-000310 do WhatsApp.", prog_meta=f"Visita em 19/11 14:17 · {M} · Auvo"),
    dict(os="82423841", cliente="HGG", area="2° ANDAR - HGG", tipo="Manutenção corretiva", tecnico=M,
         equipamento="Fancoil da sala 3",
         relato="o Motor esta com as bobinas rompida precisa ser rebobinado,para voltar a funcionar o fancol sala 3 "
                "Foi trocado djuntor com mola danificado para teste",
         utilizou="Nao", prog_txt="Aberta em 11/11 12:44.", prog_meta=f"Visita em 11/11 12:59 · {M} · Auvo"),
    dict(os="82475965", cliente="HGG", area="HGG", tipo="Manutenção corretiva", tecnico=M,
         relato="Rolamentos do motor com folga causando barulhos,precisa ser trocados !", utilizou="Nao",
         prog_txt='Aberta em 12/11 11:44. Cliente "HGG" sem andar.', prog_meta=f"Visita em 12/11 14:05 · {M} · Auvo"),
    dict(os="82150519", cliente="HGG", area="HGG", tipo="Manutenção corretiva", tecnico=M, origem="WA-HGG-000170",
         relato="Condesador muito amassado com dificuldade para realizar troca de calor ,superaquecendo compressor e "
                "entrando em alarme, precisa ser substituído!", utilizou="Nao",
         prog_txt="Aberta em 05/11 12:42, a partir do pedido WA-HGG-000170 do WhatsApp.", prog_meta=f"Visita em 05/11 13:33 · {M} · Auvo"),
    dict(os="82416811", cliente="IBIS", area="HOTEL IBIS - MARISTA", tipo="Manutenção corretiva",
         tecnico="Jonas Neto e Yânio - Obra", equipamento="Evaporadora do apto 1664",
         relato="foi efetuado a remoção do moto ventilador da turbina do evoaorador apartamento 1664, e instalado um novo motor",
         utilizou="Foi trocado motor da turbina novo", prog_txt="Aberta em 11/11 11:08.",
         prog_meta="Visita em 11/11 17:04 · Jonas Neto e Yânio - Obra · Auvo"),
    dict(os="82447493", cliente="IBIS", area="HOTEL IBIS - MARISTA", tipo="Inspeção", tecnico="Renato Bonfim",
         relato="O equipamento está com os dois compressores danificados, compressor 01 está com bobinamento em curto "
                "circuito com a carcaça, compressor 2 está com sobrecorrente.", utilizou="",
         prog_txt="Aberta em 11/11 17:31.", prog_meta="Check-in 11/11 17:32, check-out 16/11 11:49 · Renato Bonfim · Auvo"),
    dict(os="82650821", cliente="CAMIL", area="CAMIL ALIMENTOS S.A.", tipo="Manutenção de equipamento",
         tecnico="Regilvane Nascimento", equipamento="Torre alpina da linha 8",
         relato="Está sendo realizado a substituição do painel elétrico da torre alpina da linha 8.", utilizou="Painel elétrico",
         prog_txt="Aberta em 17/11 09:13.", prog_meta="Visita em 17/11 09:18 · Regilvane Nascimento · Auvo"),
    dict(os="81973385", cliente="CAMIL", area="CAMIL ALIMENTOS S.A.", tipo="Visita para orçamento", tecnico="Fabio Silva",
         relato="Matérias necessários estão descritos na imagem", utilizou="",
         prog_txt="Aberta em 03/11 08:06.", prog_meta="Check-in 03/11 08:08, check-out 17/11 14:47 · Fabio Silva · Auvo"),
]


def _i(os_, item, natureza, situacao, qtd, cls, conf, evidencia, contrato="", val_ok=True, val_txt="", presumida=False,
       fase="nivel"):
    return dict(os=os_, item=item, natureza=natureza, situacao=situacao, qtd=qtd, presumida=int(presumida), cls=cls,
                conf=conf, contrato_item=contrato, val_ok=int(val_ok), val_txt=val_txt, evidencia=evidencia, fase=fase)


ITENS = [
    _i("71741916", "Compressor do circuito 2", "Peça", "Necessário", "1 un", "Pedido de compra", "Média",
       "Compressor do circuito 2. Precisa ser trocado esta em curto", presumida=True,
       val_txt='Necessidade futura ("precisa ser trocado"), com lista de materiais',
       contrato="Fora do catálogo: o contrato só cobre compressor rotativo inverter de 9.000 e 12.000 BTU (itens 42 e 43). Modelo do compressor não informado."),
    _i("71741916", "Filtro secador 210 × 1/2 rosca", "Peça", "Necessário", "1 un", "Contrato HGG", "Alta",
       "01 filtro secador 210x1/2 rosca", "Item do contrato: 57 · FILTRO SECADOR", val_txt="Quantidade escrita no relato"),
    _i("71741916", "Contatora 220 V 40 A", "Peça", "Necessário", "1 un", "Pedido de compra", "Alta",
       "01 contactora 220v 40A", "Fora da faixa do item 58 (CONTATORA 18 A 32 AMPERES).", val_txt="Quantidade escrita no relato"),
    _i("71741916", "Varetas de solda fosfoco", "Material", "Necessário", "2 un", "Contrato HGG", "Média",
       "02 varetas fosfoco", 'Item do contrato sugerido: 8 · SOLDA FOSCOPER (confirmar se "fosfoco" é Foscoper)',
       val_txt="Quantidade escrita no relato"),
    _i("71742023", "Correia A34", "Peça", "Aplicado", "1 un", "Contrato HGG", "Alta", "trocada pela correia A34",
       "Item do contrato: 1 · CORREIAS PARA EQUIP. DE AR CONDICIONADO", presumida=True,
       val_txt="Evidência só no relato (a PMOC não tem a pergunta de peça)"),
    _i("82288641", 'Isolamento térmico 3/4"', "Material", "Aplicado", "1 m", "Pedido de compra", "Média",
       "1 metros de isolamento 3/4", "Fora do catálogo do contrato HGG.", val_txt="Relatório coerente: o campo traz a quantidade"),
    _i("82774691", "Filtros de ar", "Material", "Aplicado", "não informada", "A definir", "Baixa", "trocados os filtros",
       "Dois itens possíveis: 55 (split high wall) ou 56 (piso teto). O tipo da máquina não está na OS.", val_ok=False, val_txt=DIV),
    _i("82423841", "Recondicionamento do motor do fancoil da sala 3", "Serviço", "Necessário", "1 sv", "Contrato HGG", "Alta",
       "precisa ser rebobinado", "Item do contrato: 50 · RECONDICIONAMENTO MOTOR ELÉTRICO (FANCOIL, EXAUSTOR E VENTILADOR)",
       presumida=True, val_txt="Coerente para o motor (necessidade futura)"),
    _i("82423841", "Disjuntor", "Peça", "Inconclusivo", "1 un", "A definir", "Baixa", "Foi trocado djuntor com mola danificado para teste",
       "Fora do catálogo do contrato HGG. Confirmar se a troca ficou.", presumida=True, val_ok=False,
       val_txt=DIV + ' ("para teste": não diz se ficou instalado)'),
    _i("82475965", "Rolamentos do motor", "Peça", "Necessário", "não informada", "Pedido de compra", "Média",
       "Rolamentos do motor com folga", "Fora do catálogo do contrato HGG.",
       val_txt="Coerente: necessidade futura, sem quantidade nem equipamento"),
    _i("82150519", "Condensador", "Peça", "Necessário", "1 un", "Pedido de compra", "Média", "precisa ser substituído",
       "Fora do catálogo do contrato HGG.", presumida=True,
       val_txt='Coerente: "precisa ser substituído" é necessidade futura, não troca'),
    _i("82416811", "Motor ventilador da turbina da evaporadora (apto 1664)", "Peça", "Aplicado", "1 un", "Pedido de compra",
       "Alta", "instalado um novo motor", val_txt="Relatório coerente com o campo do Auvo"),
    _i("82447493", "Compressores (01 em curto com a carcaça, 02 com sobrecorrente)", "Peça", "Necessário", "2 un",
       "Pedido de compra", "Alta", "os dois compressores danificados", val_ok=False,
       val_txt="Atenção: o técnico autor é Renato Bonfim, o mesmo avaliador do Nível 2"),
    _i("82650821", "Painel elétrico da torre alpina (linha 8)", "Peça", "Inconclusivo", "1 un", "A definir", "Baixa",
       "Está sendo realizado a substituição do painel elétrico", presumida=True, val_ok=False,
       val_txt='Inconclusivo: "está sendo realizado" não diz se a troca terminou'),
    _i("81973385", "Lista de materiais só na foto", "Não identificado", "Inconclusivo", "—", "A definir", "Baixa",
       "descritos na imagem", val_ok=False, val_txt="Sem informação no texto: a lista está só na foto anexada",
       fase="relatorio"),
]


def remover(conn: sqlite3.Connection) -> dict:
    """Tira do banco as OS do esboço e os itens delas, para a fila mostrar só OS coletadas.

    OS do esboço com item decidido por uma pessoa (ou sugerido fora do esboço) fica, e sai listada em `mantidas`.
    A trilha de eventos é preservada. Uma OS do esboço que também é real volta na próxima coleta.
    """
    ids = [o["os"] for o in OS]
    ph = ",".join("?" * len(ids))
    with banco.Transacao(conn):
        mantidas = sorted({r[0] for r in conn.execute(
            f"SELECT DISTINCT os FROM itens WHERE os IN ({ph}) AND (versao > 1 OR sugerido_por != 'esboço')", ids)})
        alvo = [x for x in ids if x not in mantidas]
        if not alvo:
            return {"os": 0, "itens": 0, "mantidas": mantidas}
        pa = ",".join("?" * len(alvo))
        n_itens = conn.execute(f"SELECT COUNT(*) FROM itens WHERE os IN ({pa})", alvo).fetchone()[0]
        n_os = conn.execute(f"SELECT COUNT(*) FROM os WHERE os IN ({pa})", alvo).fetchone()[0]
        conn.execute(f"DELETE FROM os WHERE os IN ({pa})", alvo)  # itens e Pedidos saem em cascata
        banco.evento(conn, "*", "seed_esboco_removido", "seed", dados={"os": n_os, "itens": n_itens, "mantidas": mantidas})
    return {"os": n_os, "itens": n_itens, "mantidas": mantidas}


def carregar(conn: sqlite3.Connection, forcar: bool = False) -> int:
    existentes = conn.execute("SELECT COUNT(*) FROM os").fetchone()[0]
    if existentes and not forcar:
        raise SystemExit("O banco já tem OS. Use --forcar para apagar e recarregar o esboço.")
    agora = banco.agora()
    with banco.Transacao(conn):
        if forcar:
            for t in ("eventos", "audios", "envios", "pedidos", "itens", "identificacoes", "os"):
                conn.execute(f"DELETE FROM {t}")
        for o in OS:
            o = {"equipamento": "", "origem": "", **o}
            sem_info = o["os"] == "81973385"
            conn.execute(
                "INSERT INTO os (os, cliente, area, equipamento, tipo, tecnico, relato, utilizou, relato_hash, origem, "
                "prog_txt, prog_meta, identificacao, coletada_em, atualizada_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (o["os"], o["cliente"], o["area"], o["equipamento"], o["tipo"], o["tecnico"], o["relato"], o["utilizou"],
                 agente.hash_relato(o["relato"], o["utilizou"]), o["origem"], o["prog_txt"], o["prog_meta"],
                 "sem_info" if sem_info else "feita", agora, agora))
        versao, _ = banco.rota_atual(conn)
        if not versao:
            raise SystemExit("Crie antes os usuários hely e renato: a rota padrão (Hely → Renato) nasce com eles.")
        for i in ITENS:
            pos = 0 if i["fase"] == "nivel" else None
            conn.execute(
                "INSERT INTO itens (os, item, natureza, situacao, qtd, presumida, cls, conf, contrato_item, val_ok, "
                "val_txt, evidencia, fase, nivel_pos, rota_versao, sugerido_por, criado_em) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (i["os"], i["item"], i["natureza"], i["situacao"], i["qtd"], i["presumida"], i["cls"], i["conf"],
                 i["contrato_item"], i["val_ok"], i["val_txt"], i["evidencia"], i["fase"], pos,
                 versao if pos is not None else None, "esboço", agora))
        banco.evento(conn, "*", "seed_esboco", "seed", dados={"os": len(OS), "itens": len(ITENS)})
    return len(ITENS)


def ensaio(conn: sqlite3.Connection, forcar: bool = False) -> int:
    """As mesmas 11 OS do esboço, mas SEM itens e como `pendente`: o agente identifica e o Hely compara com a
    classificação feita à mão (lista ITENS acima)."""
    existentes = conn.execute("SELECT COUNT(*) FROM os").fetchone()[0]
    if existentes and not forcar:
        raise SystemExit("O banco já tem OS. Use --forcar para apagar e carregar o ensaio.")
    agora = banco.agora()
    with banco.Transacao(conn):
        if forcar:
            for t in ("eventos", "audios", "envios", "pedidos", "itens", "identificacoes", "os"):
                conn.execute(f"DELETE FROM {t}")
        for o in OS:
            o = {"equipamento": "", "origem": "", **o}
            conn.execute(
                "INSERT INTO os (os, cliente, area, equipamento, tipo, tecnico, relato, utilizou, relato_hash, origem, "
                "prog_txt, prog_meta, identificacao, coletada_em, atualizada_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (o["os"], o["cliente"], o["area"], o["equipamento"], o["tipo"], o["tecnico"], o["relato"], o["utilizou"],
                 agente.hash_relato(o["relato"], o["utilizou"]), o["origem"], o["prog_txt"], o["prog_meta"],
                 "pendente", agora, agora))
        banco.evento(conn, "*", "ensaio_esboco", "seed", dados={"os": len(OS)})
    return len(OS)
