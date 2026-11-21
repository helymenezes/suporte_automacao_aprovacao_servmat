"""
API HTTP do painel (FastAPI). Três públicos, três credenciais:
- pessoas (Hely Nível 1, Renato Nível 2): usuário e senha → cookie de sessão assinado;
- agente do OpenClaw: Bearer SERVMAT_AGENTE_TOKEN, só /api/agente/*;
- agendas: Bearer SERVMAT_RUN_TOKEN, só /run/*.
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

from . import agente, auth, banco, coleta, regras
from .central import Central
from .config import Config

COOKIE = "servmat_sessao"


class Login(BaseModel):
    usuario: str = Field(max_length=40)
    senha: str = Field(max_length=200)


class Decisao(BaseModel):
    acao: str
    obs: str = Field(default="", max_length=1000)
    versao: int


class Reclassificacao(BaseModel):
    cls: str
    versao: int


def criar_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="servmat", docs_url=None, redoc_url=None, openapi_url=None)
    freio = auth.Freio()
    catalogo = agente.carregar_catalogo(cfg.catalogo)

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

    def exige_agente(request: Request):
        if not auth.token_ok(request.headers.get("Authorization"), cfg.agente_token):
            raise HTTPException(401, "token do agente inválido")

    def exige_run(request: Request):
        if not auth.token_ok(request.headers.get("Authorization"), cfg.run_token):
            raise HTTPException(401, "token da agenda inválido")

    @app.exception_handler(regras.ErroRegra)
    async def _erro_regra(_req, e: regras.ErroRegra):
        return JSONResponse({"detail": str(e)}, status_code=422)

    @app.exception_handler(agente.ErroIdentificacao)
    async def _erro_ident(_req, e: agente.ErroIdentificacao):
        return JSONResponse({"detail": "identificação recusada", "erros": e.erros}, status_code=422)

    @app.exception_handler(agente.Conflito)
    async def _conflito(_req, e: agente.Conflito):
        return JSONResponse({"detail": str(e)}, status_code=409)

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
        return {"usuario": u, "nome": row["nome"], "nivel": row["nivel"]}

    @app.post("/api/logout")
    def logout(response: Response):
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/eu")
    def eu(u=Depends(usuario_atual)):
        return {"usuario": u["usuario"], "nome": u["nome"], "nivel": u["nivel"]}

    @app.get("/api/painel")
    def painel(u=Depends(usuario_atual), conn: sqlite3.Connection = Depends(conexao)):
        return montar_painel(conn)

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
            "SELECT tipo, quem, de, para, obs, em FROM eventos WHERE item_id = ? ORDER BY id", (item_id,))]

    @app.post("/api/itens/{item_id}/decisao")
    def decidir(item_id: int, d: Decisao, u=Depends(usuario_atual), conn: sqlite3.Connection = Depends(conexao)):
        with banco.Transacao(conn):
            it = conn.execute("SELECT itens.*, os.tecnico FROM itens JOIN os USING (os) WHERE id = ?",
                              (item_id,)).fetchone()
            if it is None:
                raise HTTPException(404, "Item não encontrado.")
            if it["versao"] != d.versao:
                raise HTTPException(409, "Outra pessoa mudou este item. Atualize a tela.")
            conflito = u["nivel"] == 2 and regras.conflito_tecnico(it["tecnico"], u["nome"])
            r = regras.decidir(it["fase"], it["cls"], u["nivel"], d.acao, d.obs, conflito)
            conn.execute("UPDATE itens SET fase = ?, reprovado_em = ?, versao = versao + 1 WHERE id = ?",
                         (r.fase, r.reprovado_em, item_id))
            dados = {"acao": d.acao, "nivel": u["nivel"], "conflito": conflito}
            if r.fase == "relatorio":
                # Devolvido ao agente: a OS volta para a fila do OpenClaw numa rodada nova, com o motivo.
                conn.execute("UPDATE os SET identificacao = 'pendente', rodada = rodada + 1, atualizada_em = ? "
                             "WHERE os = ?", (banco.agora(), it["os"]))
                dados["rodada_nova"] = conn.execute("SELECT rodada FROM os WHERE os = ?", (it["os"],)).fetchone()[0]
            banco.evento(conn, it["os"], "decisao", u["usuario"], item_id, it["fase"], r.fase, d.obs.strip(), dados)
        return {"id": item_id, "fase": r.fase, "fase_nome": regras.NOME_FASE[r.fase]}

    @app.post("/api/itens/{item_id}/classificacao")
    def reclassificar(item_id: int, d: Reclassificacao, u=Depends(usuario_atual),
                      conn: sqlite3.Connection = Depends(conexao)):
        with banco.Transacao(conn):
            it = conn.execute("SELECT * FROM itens WHERE id = ?", (item_id,)).fetchone()
            if it is None:
                raise HTTPException(404, "Item não encontrado.")
            if it["versao"] != d.versao:
                raise HTTPException(409, "Outra pessoa mudou este item. Atualize a tela.")
            regras.pode_reclassificar(it["fase"], u["nivel"], d.cls)
            if d.cls == regras.CONTRATO and conn.execute("SELECT cliente FROM os WHERE os = ?",
                                                        (it["os"],)).fetchone()[0] != "HGG":
                raise regras.ErroRegra("Contrato HGG só vale para OS do HGG.")
            conn.execute("UPDATE itens SET cls = ?, versao = versao + 1 WHERE id = ?", (d.cls, item_id))
            banco.evento(conn, it["os"], "classificacao", u["usuario"], item_id, it["cls"], d.cls)
        return {"id": item_id, "cls": d.cls}

    # ---------- agente do OpenClaw ----------
    @app.get("/api/agente/pendentes", dependencies=[Depends(exige_agente)])
    def agente_pendentes(limite: int = 10, conn: sqlite3.Connection = Depends(conexao)):
        return {"pendentes": agente.pendentes(conn, max(1, min(limite, 25)))}

    @app.get("/api/agente/catalogo", dependencies=[Depends(exige_agente)])
    def agente_catalogo():
        return catalogo

    @app.post("/api/agente/identificacoes", dependencies=[Depends(exige_agente)])
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
    @app.post("/run/coleta", dependencies=[Depends(exige_run)])
    def run_coleta(conn: sqlite3.Connection = Depends(conexao)):
        if not cfg.central_url:
            raise HTTPException(503, "SERVMAT_CENTRAL_URL não configurada")
        rel = coleta.coletar(conn, Central(cfg.central_url, cfg.central_token), cfg.coleta_cfg())
        return JSONResponse(rel.dict(), status_code=200 if rel.completa else 502)

    @app.get("/run/status", dependencies=[Depends(exige_run)])
    def run_status(conn: sqlite3.Connection = Depends(conexao)):
        pend = conn.execute("SELECT COUNT(*) FROM os WHERE identificacao = 'pendente'").fetchone()[0]
        por_fase = dict(conn.execute("SELECT fase, COUNT(*) FROM itens GROUP BY fase").fetchall())
        return {"aguardando_agente": pend, "itens_por_fase": por_fase}

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


def montar_painel(conn: sqlite3.Connection) -> dict:
    avaliadores = [r["nome"] for r in conn.execute("SELECT nome FROM usuarios WHERE nivel = 2 AND ativo = 1")]
    itens_por_os: dict[str, list[dict]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM itens ORDER BY id"):
        d = dict(r)
        d["presumida"] = bool(d["presumida"])
        d["val_ok"] = bool(d["val_ok"])
        d["fase_nome"] = regras.NOME_FASE[d["fase"]]
        d["trilha"] = regras.trilha(d["fase"], d["reprovado_em"])
        itens_por_os[d["os"]].append(d)

    servicos = []
    linhas = conn.execute(
        "SELECT * FROM os WHERE identificacao = 'pendente' OR EXISTS (SELECT 1 FROM itens i WHERE i.os = os.os "
        "AND i.fase NOT IN ('fim', 'reprovado')) OR atualizada_em >= datetime('now', '-30 days') "
        "ORDER BY coletada_em, os").fetchall()
    for o in linhas:
        its = itens_por_os.get(o["os"], [])
        if its:
            fase = regras.fase_servico([i["fase"] for i in its])
            cls_nome, cls_sub = regras.resumo_classificacao([i["cls"] for i in its])
            acomp = regras.etapas_servico(its, o["prog_txt"])
            mix = regras.mix_natureza([i["natureza"] for i in its])
        else:
            fase, cls_nome, cls_sub, mix = "relatorio", "A definir", "", "Aguardando o agente"
            acomp = regras.etapas_aguardando_agente(o["prog_txt"])
        servicos.append({
            "os": o["os"], "cliente": o["cliente"], "area": o["area"], "equipamento": o["equipamento"],
            "tipo": o["tipo"], "tecnico": o["tecnico"], "origem": o["origem"], "relato": o["relato"],
            "utilizou": o["utilizou"], "prog_txt": o["prog_txt"], "prog_meta": o["prog_meta"],
            "identificacao": o["identificacao"], "tem_link": o["task_url"].startswith("https://"),
            "fase": fase, "fase_nome": regras.NOME_FASE[fase], "cls": cls_nome, "cls_sub": cls_sub, "mix": mix,
            "conflito_n2": any(regras.conflito_tecnico(o["tecnico"], n) for n in avaliadores),
            "etapas": acomp["etapas"], "agora": acomp["agora"], "itens": its,
        })

    contagem: dict[str, int] = defaultdict(int)
    for its in itens_por_os.values():
        for i in its:
            contagem[i["fase"]] += 1
    fases = [{"chave": f, "nome": regras.NOME_FASE[f], "quem": regras.QUEM_FASE[f], "qtd": contagem.get(f, 0)}
             for f in regras.FASES]
    aguardando = sum(1 for s in servicos if not s["itens"])
    return {"gerado_em": banco.agora(), "fases": fases, "aguardando_agente": aguardando, "servicos": servicos}
