"""
API HTTP do painel (FastAPI). Quatro públicos, quatro credenciais:
- pessoas: usuário e senha → cookie de sessão assinado. Quem decide em cada nível sai da rota (tela Níveis);
  o administrador (Hely) edita a rota, pede ao orçamentista e registra o Pedido à mão;
- agente do OpenClaw: Bearer SERVMAT_AGENTE_TOKEN, só /api/agente/*;
- agendas: Bearer SERVMAT_RUN_TOKEN, só /run/*;
- integrações (sistema comercial, planilha do cliente): Bearer SERVMAT_INTEGRACAO_TOKEN, só /api/integracao/*.
Toda escrita com cookie exige o cabeçalho X-Servmat: 1 (defesa contra CSRF, junto com SameSite=Strict).
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agente, audio, auth, banco, coleta, envio, historico, pedidos, regras
from .central import Central
from .config import Config

COOKIE = "servmat_sessao"


class Login(BaseModel):
    usuario: str = Field(max_length=40)
    senha: str = Field(max_length=200)


class Decisao(BaseModel):
    acao: str
    obs: str = Field(default="", max_length=2000)
    versao: int
    audio_id: str | None = Field(default=None, max_length=40)


class Reclassificacao(BaseModel):
    cls: str
    versao: int


class Rota(BaseModel):
    niveis: list[dict]
    contratos: dict[str, bool] = {}


class Registro(BaseModel):
    campos: dict[str, str | None]


class Conferencia(BaseModel):
    decisao: str


class Importacao(BaseModel):
    registros: list[dict]


def criar_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="servmat", docs_url=None, redoc_url=None, openapi_url=None)
    freio = auth.Freio()
    catalogo = agente.carregar_catalogo(cfg.catalogo)
    inicial = banco.conectar(cfg.banco)
    banco.criar(inicial)
    historico.criar(inicial)
    banco.garantir_rota(inicial)
    inicial.close()

    def conexao():
        conn = banco.conectar(cfg.banco)
        try:
            yield conn
        finally:
            conn.close()

    def usuario_atual(request: Request, conn: sqlite3.Connection = Depends(conexao)) -> sqlite3.Row:
        nome = auth.ler_sessao(request.cookies.get(COOKIE), cfg.segredo)
        u = conn.execute("SELECT * FROM usuarios WHERE usuario = ? AND ativo = 1", (nome,)).fetchone() if nome else None
        if u is None:
            raise HTTPException(401, "Entre com seu usuário.")
        if request.method != "GET" and request.headers.get("X-Servmat") != "1":
            raise HTTPException(403, "Requisição sem o cabeçalho do painel.")
        return u

    def admin(u=Depends(usuario_atual)) -> sqlite3.Row:
        if not u["admin"]:
            raise HTTPException(403, "Só o administrador faz esta ação.")
        return u

    def exige(token: str):
        def dep(request: Request):
            if not auth.token_ok(request.headers.get("Authorization"), token):
                raise HTTPException(401, "token inválido para esta rota")
        return dep

    for erro, codigo in ((regras.ErroRegra, 422), (pedidos.ErroPedido, 422), (audio.ErroAudio, 422),
                         (agente.Conflito, 409)):
        app.add_exception_handler(erro, lambda _r, e, c=codigo: JSONResponse({"detail": str(e)}, status_code=c))

    @app.exception_handler(historico.ErroProposta)
    async def _erro_proposta(_req, e: historico.ErroProposta):
        return JSONResponse({"detail": "proposta de catálogo recusada", "erros": e.erros}, status_code=422)

    @app.exception_handler(agente.ErroIdentificacao)
    async def _erro_ident(_req, e: agente.ErroIdentificacao):
        return JSONResponse({"detail": "identificação recusada", "erros": e.erros}, status_code=422)

    @app.get("/health")
    def health(conn: sqlite3.Connection = Depends(conexao)):
        conn.execute("SELECT 1").fetchone()
        return {"ok": True}

    # ---------- pessoas ----------
    @app.post("/api/login")
    def login(dados: Login, response: Response, conn: sqlite3.Connection = Depends(conexao)):
        u = dados.usuario.strip().lower()
        if freio.bloqueado(u):
            raise HTTPException(429, "Muitas tentativas. Espere 10 minutos.")
        row = conn.execute("SELECT * FROM usuarios WHERE usuario = ? AND ativo = 1", (u,)).fetchone()
        if row is None or not auth.conferir_senha(dados.senha, row["senha_hash"]):
            freio.errou(u)
            raise HTTPException(401, "Usuário ou senha incorretos.")
        freio.acertou(u)
        response.set_cookie(COOKIE, auth.emitir_sessao(u, cfg.segredo), max_age=12 * 3600, httponly=True,
                            secure=cfg.cookie_seguro, samesite="strict", path="/")
        return _eu(conn, row)

    @app.post("/api/logout")
    def logout(response: Response):
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/eu")
    def eu(u=Depends(usuario_atual), conn: sqlite3.Connection = Depends(conexao)):
        return _eu(conn, u)

    @app.get("/api/painel")
    def painel(u=Depends(usuario_atual), conn: sqlite3.Connection = Depends(conexao)):
        return montar_painel(conn, u["usuario"])

    @app.get("/api/os/{os_num}/auvo")
    def abrir_auvo(os_num: str, u=Depends(usuario_atual), conn: sqlite3.Connection = Depends(conexao)):
        # O link do Auvo tem chave de acesso: nunca vai no JSON, só neste redirecionamento autenticado.
        o = conn.execute("SELECT task_url FROM os WHERE os = ?", (os_num,)).fetchone()
        if o is None or not o["task_url"].startswith("https://"):
            raise HTTPException(404, "Link do Auvo não disponível para esta OS.")
        return RedirectResponse(o["task_url"], status_code=302)

    @app.get("/api/itens/{item_id}/eventos")
    def eventos_item(item_id: int, u=Depends(usuario_atual), conn: sqlite3.Connection = Depends(conexao)):
        return [dict(r) for r in conn.execute(
            "SELECT tipo, quem, de, para, obs, dados, em FROM eventos WHERE item_id = ? ORDER BY id", (item_id,))]

    @app.post("/api/itens/{item_id}/decisao")
    def decidir(item_id: int, d: Decisao, u=Depends(usuario_atual), conn: sqlite3.Connection = Depends(conexao)):
        rotas = banco.rotas_por_versao(conn)
        with banco.Transacao(conn):
            it = conn.execute("SELECT itens.*, os.tecnico FROM itens JOIN os USING (os) WHERE id = ?",
                              (item_id,)).fetchone()
            if it is None:
                raise HTTPException(404, "Item não encontrado.")
            if it["versao"] != d.versao:
                raise HTTPException(409, "Outra pessoa mudou este item. Atualize a tela.")
            if d.audio_id and conn.execute("SELECT 1 FROM audios WHERE id = ? AND item_id = ? AND usuario = ?",
                                           (d.audio_id, item_id, u["usuario"])).fetchone() is None:
                raise HTTPException(422, "Áudio não pertence a este item.")
            rota = regras.rota_do_item(rotas.get(it["rota_versao"], []), it["cls"])
            conflito = regras.conflito_tecnico(it["tecnico"], u["nome"])
            r = regras.decidir(it["fase"], it["nivel_pos"], it["cls"], rota, u["usuario"], d.acao, d.obs, conflito)
            conn.execute("UPDATE itens SET fase = ?, nivel_pos = ?, reprovado_em = ?, versao = versao + 1 WHERE id = ?",
                         (r.fase, r.pos, r.reprovado_em, item_id))
            dados = {"acao": d.acao, "nivel": (it["nivel_pos"] or 0) + 1, "conflito": conflito}
            if d.audio_id:
                dados["audio"] = d.audio_id
            if r.fase == "relatorio":
                # Devolvido ao agente: a OS volta para a fila do OpenClaw numa rodada nova, com o motivo.
                conn.execute("UPDATE os SET identificacao = 'pendente', rodada = rodada + 1, atualizada_em = ? "
                             "WHERE os = ?", (banco.agora(), it["os"]))
                dados["rodada_nova"] = conn.execute("SELECT rodada FROM os WHERE os = ?", (it["os"],)).fetchone()[0]
            banco.evento(conn, it["os"], "decisao", u["usuario"], item_id, regras.nome_fase(it["fase"], it["nivel_pos"]),
                         regras.nome_fase(r.fase, r.pos), d.obs.strip(), dados)
        return {"id": item_id, "fase": r.fase, "fase_nome": regras.nome_fase(r.fase, r.pos)}

    @app.post("/api/itens/{item_id}/classificacao")
    def reclassificar(item_id: int, d: Reclassificacao, u=Depends(usuario_atual),
                      conn: sqlite3.Connection = Depends(conexao)):
        rotas = banco.rotas_por_versao(conn)
        with banco.Transacao(conn):
            it = conn.execute("SELECT itens.*, os.cliente FROM itens JOIN os USING (os) WHERE id = ?",
                              (item_id,)).fetchone()
            if it is None:
                raise HTTPException(404, "Item não encontrado.")
            if it["versao"] != d.versao:
                raise HTTPException(409, "Outra pessoa mudou este item. Atualize a tela.")
            snap = rotas.get(it["rota_versao"], [])
            regras.pode_reclassificar(it["fase"], it["nivel_pos"], regras.rota_do_item(snap, it["cls"]),
                                      u["usuario"], d.cls)
            if d.cls == regras.CONTRATO:
                ligado = conn.execute("SELECT ligado FROM contratos_cliente WHERE cliente = ?", (it["cliente"],)).fetchone()
                if it["cliente"] != "HGG" or not (ligado and ligado[0]):
                    raise regras.ErroRegra("Contrato HGG só vale para OS do HGG com o critério de contrato ligado.")
            fase, pos = regras.ajustar_posicao(it["fase"], it["nivel_pos"], regras.rota_do_item(snap, d.cls), d.cls)
            conn.execute("UPDATE itens SET cls = ?, fase = ?, nivel_pos = ?, versao = versao + 1 WHERE id = ?",
                         (d.cls, fase, pos, item_id))
            banco.evento(conn, it["os"], "classificacao", u["usuario"], item_id, it["cls"], d.cls)
        return {"id": item_id, "cls": d.cls}

    # ---------- áudio (celular) ----------
    @app.post("/api/itens/{item_id}/audio")
    async def enviar_audio(item_id: int, request: Request, u=Depends(usuario_atual)):
        if int(request.headers.get("content-length") or 0) > audio.MAX_BYTES:
            raise HTTPException(413, "Áudio maior que 10 MB.")
        dados = await request.body()
        conn = banco.conectar(cfg.banco)
        try:
            if conn.execute("SELECT 1 FROM itens WHERE id = ?", (item_id,)).fetchone() is None:
                raise HTTPException(404, "Item não encontrado.")
            mime = request.headers.get("content-type", "")
            ident, caminho = audio.salvar(cfg.pasta_audios, dados, mime)
            texto = audio.transcrever(cfg.transcricao_url, cfg.transcricao_chave, cfg.transcricao_modelo, caminho, mime)
            conn.execute("INSERT INTO audios (id, item_id, usuario, arquivo, mime, bytes, transcricao, criado_em) "
                         "VALUES (?,?,?,?,?,?,?,?)", (ident, item_id, u["usuario"], caminho.name, audio.tipo_base(mime),
                                                      len(dados), texto, banco.agora()))
            return {"id": ident, "transcricao": texto, "transcrito": bool(texto),
                    "transcricao_ligada": bool(cfg.transcricao_url)}
        finally:
            conn.close()

    @app.get("/api/audios/{ident}")
    def ouvir_audio(ident: str, u=Depends(usuario_atual), conn: sqlite3.Connection = Depends(conexao)):
        a = conn.execute("SELECT arquivo, mime FROM audios WHERE id = ?", (ident,)).fetchone()
        if a is None or "/" in a["arquivo"]:
            raise HTTPException(404, "Áudio não encontrado.")
        return FileResponse(cfg.pasta_audios / a["arquivo"], media_type=a["mime"])

    # ---------- níveis de aprovação ----------
    @app.get("/api/catalogo-proposto")
    def catalogo_proposto(cliente: str | None = None, _u=Depends(usuario_atual),
                          conn: sqlite3.Connection = Depends(conexao)):
        return {"propostas": historico.propostas(conn, cliente)}

    @app.post("/api/catalogo-proposto/{proposta_id}/aprovar")
    def catalogo_aprovar(proposta_id: int, u=Depends(admin), conn: sqlite3.Connection = Depends(conexao)):
        try:
            return historico.aprovar(conn, proposta_id, u["usuario"])
        except KeyError:
            raise HTTPException(404, "proposta não encontrada") from None

    @app.get("/api/niveis")
    def ver_niveis(u=Depends(usuario_atual), conn: sqlite3.Connection = Depends(conexao)):
        versao, _ = banco.rota_atual(conn)
        usuarios = [dict(r) for r in conn.execute("SELECT usuario, nome FROM usuarios WHERE ativo = 1 ORDER BY nome")]
        nomes = {x["usuario"]: x["nome"] for x in usuarios}
        niveis = [dict(r, compra=bool(r["compra"]), contrato=bool(r["contrato"]), ativo=bool(r["ativo"]),
                       nome=nomes.get(r["usuario"] or "", "")) for r in conn.execute("SELECT * FROM niveis ORDER BY ordem")]
        ligados = dict(conn.execute("SELECT cliente, ligado FROM contratos_cliente").fetchall())
        clientes = sorted({r[0] for r in conn.execute("SELECT DISTINCT cliente FROM os")} | set(ligados) |
                          {"HGG", "CAMIL", "IBIS", "BLEND", "HEJ"})
        contratos = [{"cliente": c, "ligado": bool(ligados.get(c)), "tem_catalogo": c in catalogo and c == "HGG"}
                     for c in clientes]
        return {"versao": versao, "niveis": niveis, "usuarios": usuarios, "contratos": contratos,
                "pode_editar": bool(u["admin"])}

    @app.put("/api/niveis")
    def salvar_niveis(d: Rota, u=Depends(admin), conn: sqlite3.Connection = Depends(conexao)):
        ativos = {r[0] for r in conn.execute("SELECT usuario FROM usuarios WHERE ativo = 1")}
        limpos = regras.validar_niveis(d.niveis, ativos)
        for cliente, ligado in d.contratos.items():
            if ligado and not (cliente == "HGG" and cliente in catalogo):
                raise regras.ErroRegra(f"{cliente}: não há catálogo de contrato carregado para ligar o critério.")
        with banco.Transacao(conn):
            versao = banco.salvar_rota(conn, limpos, u["usuario"])
            for cliente, ligado in d.contratos.items():
                conn.execute("INSERT INTO contratos_cliente (cliente, ligado) VALUES (?,?) ON CONFLICT(cliente) "
                             "DO UPDATE SET ligado = excluded.ligado", (cliente[:20], int(ligado)))
        return {"versao": versao}

    # ---------- acompanhamento do pedido ----------
    @app.get("/api/pedidos")
    def ver_pedidos(u=Depends(usuario_atual), conn: sqlite3.Connection = Depends(conexao)):
        return dict(pedidos.montar(conn), envio_real=cfg.envio.real, destino=cfg.envio.nome_destino,
                    pode_agir=bool(u["admin"]))

    def _linha(conn, os_num: str, tipo: str) -> dict:
        linha = next((l for l in pedidos.montar(conn)["linhas"] if l["os"] == os_num and l["tipo"] == tipo), None)
        if linha is None:
            raise HTTPException(404, "Não há itens desta OS nesta rota.")
        return linha

    def _concluir(conn, os_num: str, tipo: str, quem: str) -> None:
        """Linha em 'Cobrança solicitada' (ou contrato faturável): os itens aprovados vão para Concluído."""
        if _linha(conn, os_num, tipo)["grupo"] != "cobs":
            return
        clss = (regras.CONTRATO,) if tipo == "contrato" else (regras.PEDIDO, regras.A_DEFINIR)
        marcas = ",".join("?" * len(clss))
        with banco.Transacao(conn):
            n = conn.execute(f"UPDATE itens SET fase = 'fim', versao = versao + 1 WHERE os = ? AND cls IN ({marcas}) "
                             "AND fase IN ('whats', 'pedido')", (os_num, *clss)).rowcount
            if n:
                banco.evento(conn, os_num, "concluido", quem, dados={"tipo": tipo, "itens": n})

    @app.post("/api/pedidos/{os_num}/{tipo}/solicitar")
    def solicitar(os_num: str, tipo: str, u=Depends(admin), conn: sqlite3.Connection = Depends(conexao)):
        linha = _linha(conn, os_num, tipo)
        if not linha["pode_solicitar"]:
            raise HTTPException(422, "Esta linha não está pronta para a solicitação.")
        o = conn.execute("SELECT * FROM os WHERE os = ?", (os_num,)).fetchone()
        its = [i for i in conn.execute("SELECT * FROM itens WHERE os = ? AND fase IN ('whats', 'pedido', 'fim')",
                                       (os_num,)) if pedidos.tipo_de(i["cls"]) == tipo]
        e = envio.solicitar(conn, cfg.envio, os_num, tipo, "solicitacao", u["usuario"],
                            envio.texto_solicitacao(o, its, tipo))
        return dict(e)

    @app.post("/api/pedidos/{os_num}/{tipo}/cobranca")
    def cobrar(os_num: str, tipo: str, u=Depends(admin), conn: sqlite3.Connection = Depends(conexao)):
        linha = _linha(conn, os_num, tipo)
        if not linha["pode_cobrar"]:
            raise HTTPException(422, "A cobrança só sai depois do Pedido vinculado, do aceite e da execução concluída.")
        o = conn.execute("SELECT * FROM os WHERE os = ?", (os_num,)).fetchone()
        p = conn.execute("SELECT * FROM pedidos WHERE os = ? AND tipo = ?", (os_num, tipo)).fetchone()
        its = [i for i in conn.execute("SELECT * FROM itens WHERE os = ? AND fase IN ('whats', 'pedido')", (os_num,))
               if pedidos.tipo_de(i["cls"]) == tipo]
        e = envio.solicitar(conn, cfg.envio, os_num, tipo, "cobranca", u["usuario"], envio.texto_cobranca(o, its, p))
        _concluir(conn, os_num, tipo, u["usuario"])
        return dict(e)

    @app.post("/api/pedidos/{os_num}/{tipo}/registro")
    def registrar(os_num: str, tipo: str, d: Registro, u=Depends(admin), conn: sqlite3.Connection = Depends(conexao)):
        pedidos.registrar_manual(conn, os_num, tipo, d.campos, u["usuario"])
        _concluir(conn, os_num, tipo, u["usuario"])
        return {"ok": True}

    @app.post("/api/envios/{envio_id}/conferir")
    def conferir_envio(envio_id: int, d: Conferencia, u=Depends(admin), conn: sqlite3.Connection = Depends(conexao)):
        try:
            e = envio.resolver_incerto(conn, envio_id, d.decisao, u["usuario"])
        except KeyError:
            raise HTTPException(404, "Envio não encontrado.") from None
        except ValueError as ex:
            raise HTTPException(422, str(ex)) from None
        _concluir(conn, e["os"], e["tipo"], u["usuario"])
        return dict(e)

    # ---------- integrações (sistema comercial, planilha) ----------
    @app.post("/api/integracao/{fonte}", dependencies=[Depends(exige(cfg.integracao_token))])
    def integrar(fonte: str, d: Importacao, conn: sqlite3.Connection = Depends(conexao)):
        if fonte not in pedidos.CAMPOS:
            raise HTTPException(404, "fonte desconhecida")
        r = pedidos.importar(conn, fonte, d.registros, f"integracao:{fonte}")
        for reg in d.registros:
            if isinstance(reg, dict) and reg.get("tipo") in ("compra", "contrato"):
                try:
                    _concluir(conn, str(reg.get("os")), reg["tipo"], f"integracao:{fonte}")
                except HTTPException:
                    pass
        return r

    # ---------- agente do OpenClaw ----------
    @app.get("/api/agente/pendentes", dependencies=[Depends(exige(cfg.agente_token))])
    def agente_pendentes(limite: int = 10, conn: sqlite3.Connection = Depends(conexao)):
        return {"pendentes": agente.pendentes(conn, max(1, min(limite, 25)))}

    @app.get("/api/agente/catalogo", dependencies=[Depends(exige(cfg.agente_token))])
    def agente_catalogo(conn: sqlite3.Connection = Depends(conexao)):
        ligados = [r[0] for r in conn.execute("SELECT cliente FROM contratos_cliente WHERE ligado = 1")]
        return dict(catalogo, _criterio_de_contrato_ligado=ligados, uso=historico.uso_aprovado(conn))

    @app.get("/api/agente/historico", dependencies=[Depends(exige(cfg.agente_token))])
    def agente_historico(cliente: str, apos: str = "", limite: int = 40, desde: str = "",
                         conn: sqlite3.Connection = Depends(conexao)):
        return historico.pagina(conn, cliente, apos, max(1, min(limite, 100)), desde)

    @app.post("/api/agente/catalogo-proposto", dependencies=[Depends(exige(cfg.agente_token))])
    async def agente_catalogo_proposto(request: Request):
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(422, "corpo precisa ser um objeto JSON")
        nome = str(request.headers.get("X-Agente", "openclaw"))[:40] or "openclaw"
        conn = banco.conectar(cfg.banco)
        try:
            return historico.propor(conn, payload, f"agente:{nome}")
        finally:
            conn.close()

    @app.post("/api/agente/identificacoes", dependencies=[Depends(exige(cfg.agente_token))])
    async def agente_identificar(request: Request):
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(422, "corpo precisa ser um objeto JSON")
        nome = str(request.headers.get("X-Agente", "openclaw"))[:40] or "openclaw"
        conn = banco.conectar(cfg.banco)
        try:
            return agente.aplicar(conn, payload, f"agente:{nome}", catalogo)
        except KeyError:
            raise HTTPException(404, "OS não encontrada") from None
        finally:
            conn.close()

    # ---------- agendas (OpenClaw "script", sem modelo) ----------
    @app.post("/run/coleta", dependencies=[Depends(exige(cfg.run_token))])
    def run_coleta(conn: sqlite3.Connection = Depends(conexao)):
        if not cfg.central_url:
            raise HTTPException(503, "SERVMAT_CENTRAL_URL não configurada")
        rel = coleta.coletar(conn, Central(cfg.central_url, cfg.central_token), cfg.coleta_cfg())
        return JSONResponse(rel.dict(), status_code=200 if rel.completa else 502)

    @app.get("/run/status", dependencies=[Depends(exige(cfg.run_token))])
    def run_status(conn: sqlite3.Connection = Depends(conexao)):
        pend = conn.execute("SELECT COUNT(*) FROM os WHERE identificacao = 'pendente'").fetchone()[0]
        por_fase = dict(conn.execute("SELECT fase, COUNT(*) FROM itens GROUP BY fase").fetchall())
        incertos = conn.execute("SELECT COUNT(*) FROM envios WHERE estado = 'INCERTO'").fetchone()[0]
        return {"aguardando_agente": pend, "itens_por_fase": por_fase, "envios_incertos": incertos}

    # ---------- telas ----------
    dist = Path(cfg.web_dist)
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{caminho:path}", include_in_schema=False)
        def spa(caminho: str):
            if caminho.startswith(("api/", "run/")):
                raise HTTPException(404)
            alvo = (dist / caminho).resolve()
            if caminho and alvo.is_file() and dist.resolve() in alvo.parents:
                return FileResponse(alvo)
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app


def _eu(conn: sqlite3.Connection, u: sqlite3.Row) -> dict:
    _, rota = banco.rota_atual(conn)
    meus = [k + 1 for k, n in enumerate([n for n in rota if n.get("ativo")]) if n.get("usuario") == u["usuario"]]
    return {"usuario": u["usuario"], "nome": u["nome"], "admin": bool(u["admin"]), "niveis": meus}


def montar_painel(conn: sqlite3.Connection, usuario: str) -> dict:
    rotas = banco.rotas_por_versao(conn)
    versao_atual, rota_atual = banco.rota_atual(conn)
    nomes = dict(conn.execute("SELECT usuario, nome FROM usuarios").fetchall())
    itens_por_os: dict[str, list[dict]] = defaultdict(list)
    contagem: dict[tuple[str, int | None], int] = defaultdict(int)
    for r in conn.execute("SELECT * FROM itens ORDER BY id"):
        d = dict(r)
        rota = regras.rota_do_item(rotas.get(d["rota_versao"], []), d["cls"])
        pos = d["nivel_pos"]
        nivel = rota[pos] if d["fase"] == "nivel" and pos is not None and pos < len(rota) else None
        d.update(
            presumida=bool(d["presumida"]), val_ok=bool(d["val_ok"]),
            fase_nome=regras.nome_fase(d["fase"], pos),
            fase_chave=f"nivel:{pos}" if d["fase"] == "nivel" else d["fase"],
            nivel_quem=(nivel or {}).get("nome") or nomes.get((nivel or {}).get("usuario") or "", ""),
            nivel_papel=(nivel or {}).get("papel", ""),
            minha_vez=bool(nivel and nivel.get("usuario") == usuario),
            pode_reclassificar=bool(nivel and pos == 0 and nivel.get("usuario") == usuario),
            trilha=regras.trilha(d["fase"], pos, rota),
        )
        itens_por_os[d["os"]].append(d)
        contagem[(d["fase"], pos if d["fase"] == "nivel" else None)] += 1

    ligados = {r[0] for r in conn.execute("SELECT cliente FROM contratos_cliente WHERE ligado = 1")}
    servicos = []
    linhas = conn.execute(
        "SELECT * FROM os WHERE identificacao = 'pendente' OR EXISTS (SELECT 1 FROM itens i WHERE i.os = os.os "
        "AND i.fase NOT IN ('fim', 'reprovado')) OR atualizada_em >= datetime('now', '-30 days') "
        "ORDER BY coletada_em, os").fetchall()
    for o in linhas:
        its = itens_por_os.get(o["os"], [])
        if its:
            fase, pos = regras.fase_servico(its)
            cls_nome, cls_sub = regras.resumo_classificacao([i["cls"] for i in its])
            acomp = regras.etapas_servico(its, o["prog_txt"], pedidos.situacao_para_etapas(conn, o["os"]))
            mix = regras.mix_natureza([i["natureza"] for i in its])
        else:
            fase, pos, cls_nome, cls_sub, mix = "relatorio", None, "A definir", "", "Aguardando o agente"
            acomp = regras.etapas_aguardando_agente(o["prog_txt"])
        servicos.append({
            "os": o["os"], "cliente": o["cliente"], "area": o["area"], "equipamento": o["equipamento"],
            "tipo": o["tipo"], "tecnico": o["tecnico"], "origem": o["origem"], "relato": o["relato"],
            "utilizou": o["utilizou"], "prog_txt": o["prog_txt"], "prog_meta": o["prog_meta"],
            "identificacao": o["identificacao"], "tem_link": o["task_url"].startswith("https://"),
            "contrato_avaliado": o["cliente"] in ligados,
            "fase": fase, "fase_chave": f"nivel:{pos}" if fase == "nivel" else fase,
            "fase_nome": regras.nome_fase(fase, pos), "cls": cls_nome, "cls_sub": cls_sub, "mix": mix,
            "conflito": regras.conflito_tecnico(o["tecnico"], nomes.get(usuario, "")),
            "etapas": acomp["etapas"], "agora": acomp["agora"], "itens": its,
        })

    ativos = [n for n in rota_atual if n.get("ativo")]
    fases = [{"chave": "relatorio", "nome": "Relatório", "quem": regras.QUEM_FASE["relatorio"],
              "qtd": contagem.get(("relatorio", None), 0)}]
    for k, n in enumerate(ativos):
        fases.append({"chave": f"nivel:{k}", "nome": f"Nível {k + 1}", "quem": n.get("nome") or n.get("usuario") or "—",
                      "qtd": contagem.get(("nivel", k), 0)})
    for f in ("whats", "pedido", "fim", "reprovado"):
        fases.append({"chave": f, "nome": regras.NOME_FASE[f], "quem": regras.QUEM_FASE[f], "qtd": contagem.get((f, None), 0)})
    aguardando = sum(1 for s in servicos if not s["itens"])
    return {"gerado_em": banco.agora(), "rota_versao": versao_atual, "fases": fases,
            "aguardando_agente": aguardando, "servicos": servicos}
