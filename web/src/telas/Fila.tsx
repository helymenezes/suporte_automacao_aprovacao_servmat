import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ErroApi } from "../api";
import { classeCls, EtapaAtual, Etapas } from "../componentes/Etapas";
import type { Item, Painel, Servico, Usuario } from "../tipos";

interface Filtros {
  fase: string;
  cliente: string;
  tipo: string;
  cls: string;
  nat: string;
  busca: string;
}
const SEM_FILTRO: Filtros = { fase: "", cliente: "", tipo: "", cls: "", nat: "", busca: "" };
const CONF_SIMB: Record<string, string> = { Alta: "●", Média: "▲", Baixa: "▼" };

function unicos(lista: string[]): string[] {
  return Array.from(new Set(lista.filter(Boolean))).sort();
}

export function Fila({ eu, aoSair }: { eu: Usuario; aoSair: () => void }) {
  const [painel, setPainel] = useState<Painel | null>(null);
  const [erroCarga, setErroCarga] = useState("");
  const [f, setF] = useState<Filtros>(SEM_FILTRO);
  const [abertos, setAbertos] = useState<Set<string>>(new Set());
  const [selId, setSelId] = useState<number | null>(null);
  const [mostrarDetalhe, setMostrarDetalhe] = useState(false);
  const [obs, setObs] = useState("");
  const [erroAcao, setErroAcao] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setPainel(await api.painel());
      setErroCarga("");
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) return aoSair();
      setErroCarga(e instanceof Error ? e.message : "Falha ao carregar.");
    }
  }, [aoSair]);

  useEffect(() => {
    carregar();
    const t = window.setInterval(carregar, 60_000);
    return () => window.clearInterval(t);
  }, [carregar]);

  const servicos = painel?.servicos ?? [];
  const todosItens = useMemo(() => servicos.flatMap((s) => s.itens), [servicos]);
  const sel: Item | undefined = todosItens.find((i) => i.id === selId) ?? servicos.find((s) => s.itens.length)?.itens[0];
  const svSel: Servico | undefined = servicos.find((s) => s.os === sel?.os);

  const filtrados = useMemo(() => {
    const q = f.busca.trim().toLowerCase();
    const passaItem = (i: Item) => (!f.fase || i.fase === f.fase) && (!f.cls || i.cls === f.cls) && (!f.nat || i.natureza === f.nat);
    return servicos.filter((s) =>
      (!f.cliente || s.cliente === f.cliente) &&
      (!f.tipo || s.tipo === f.tipo) &&
      (s.itens.length ? s.itens.some(passaItem) : !f.cls && !f.nat && (!f.fase || f.fase === "relatorio")) &&
      (!q || [s.os, s.equipamento, s.area, ...s.itens.map((i) => i.item)].join(" ").toLowerCase().includes(q)));
  }, [servicos, f]);

  const todosAbertos = filtrados.length > 0 && filtrados.every((s) => abertos.has(s.os));
  const totalItens = filtrados.reduce((t, s) => t + s.itens.length, 0);
  const resumo = `${filtrados.length} de ${servicos.length} serviços · ${totalItens} itens`;

  const alternar = (os: string) => {
    const n = new Set(abertos);
    if (n.has(os)) n.delete(os);
    else n.add(os);
    setAbertos(n);
  };
  const apresentar = (s: Servico) => {
    if (s.itens.length && sel?.os !== s.os) setSelId(s.itens[0].id);
    setAbertos(new Set(abertos).add(s.os));
    setMostrarDetalhe(true);
    setErroAcao("");
  };
  const escolherItem = (i: Item) => {
    setSelId(i.id);
    setObs("");
    setErroAcao("");
  };

  async function acao(fn: () => Promise<unknown>) {
    setOcupado(true);
    setErroAcao("");
    try {
      await fn();
      setObs("");
      await carregar();
    } catch (e) {
      setErroAcao(e instanceof Error ? e.message : "Falha.");
      if (e instanceof ErroApi && e.status === 409) await carregar();
    } finally {
      setOcupado(false);
    }
  }

  const clientes = unicos(servicos.map((s) => s.cliente));
  const tipos = unicos(servicos.map((s) => s.tipo));

  return (
    <div style={{ minHeight: "100vh" }}>
      <header className="topo">
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span className="sobre">Grupo Suporte · PCM</span>
          <h1>Peças, materiais e serviços das OS</h1>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          {painel && <span className="pilula">Atualizado: {new Date(painel.gerado_em).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</span>}
          {painel && painel.aguardando_agente > 0 && <span className="pilula aviso">{painel.aguardando_agente} OS aguardando o agente</span>}
          <span className="pilula">{eu.nome} · Nível {eu.nivel}</span>
          <button type="button" className="pilula" onClick={aoSair}>Sair</button>
        </div>
      </header>
      <nav aria-label="Seções do painel" className="abas">
        <a href="/" aria-current="page">Fila de aprovação</a>
        <a href="/celular">Tela do celular</a>
      </nav>

      <main className="fila">
        {erroCarga && <p className="erro-caixa" role="alert">{erroCarga}</p>}

        <section aria-label="Fases do processo" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", justifyContent: "space-between" }}>
            <h2 style={{ margin: 0, fontSize: 15, lineHeight: "22px", fontWeight: 700 }}>Onde cada item está</h2>
            <span className="sub">Clique numa fase para filtrar os serviços. Clique de novo para ver todos.</span>
          </div>
          <div className="fases">
            {(painel?.fases ?? []).map((fa) => (
              <button key={fa.chave} type="button" className="fase" aria-pressed={f.fase === fa.chave}
                onClick={() => setF({ ...f, fase: f.fase === fa.chave ? "" : fa.chave })}>
                <span className="rotulo">{fa.nome}</span>
                <span className="qtd nunito num">{fa.qtd}</span>
                <span className="p12 sub">{fa.chave === "relatorio" && painel!.aguardando_agente ? `${fa.quem} · ${painel!.aguardando_agente} OS na fila` : fa.quem}</span>
              </button>
            ))}
          </div>
        </section>

        <section aria-label="Filtros" className="filtros">
          <div className="campo">
            <label htmlFor="f-cliente">Cliente</label>
            <select id="f-cliente" value={f.cliente} onChange={(e) => setF({ ...f, cliente: e.target.value })}>
              <option value="">Todos</option>
              {clientes.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="campo" style={{ flexBasis: 190 }}>
            <label htmlFor="f-tipo">Tipo de OS</label>
            <select id="f-tipo" value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })}>
              <option value="">Todos</option>
              {tipos.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="campo" style={{ flexBasis: 170 }}>
            <label htmlFor="f-cls">Classificação</label>
            <select id="f-cls" value={f.cls} onChange={(e) => setF({ ...f, cls: e.target.value })}>
              <option value="">Todas</option>
              <option>Contrato HGG</option>
              <option>Pedido de compra</option>
              <option>A definir</option>
            </select>
          </div>
          <div className="campo">
            <label htmlFor="f-nat">Natureza</label>
            <select id="f-nat" value={f.nat} onChange={(e) => setF({ ...f, nat: e.target.value })}>
              <option value="">Todas</option>
              <option>Peça</option>
              <option>Material</option>
              <option>Serviço</option>
            </select>
          </div>
          <div className="campo largo">
            <label htmlFor="f-busca">Buscar por OS, equipamento, área ou item</label>
            <input id="f-busca" type="search" value={f.busca} placeholder="Ex.: fancoil, 5° andar, compressor, 71741916"
              onChange={(e) => setF({ ...f, busca: e.target.value })} />
          </div>
          <button type="button" className="btn fino" onClick={() => setF(SEM_FILTRO)}>Limpar filtros</button>
        </section>

        <div className="grade">
          <section aria-label="Serviços das OS" className="lista">
            <div className="lista-topo">
              <h2>Serviços das OS</h2>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span className="tip">
                  <button type="button" className="btn fino peq" aria-pressed={todosAbertos} aria-describedby="resumo-lista"
                    onClick={() => setAbertos(todosAbertos ? new Set() : new Set(filtrados.map((s) => s.os)))}>
                    {todosAbertos ? "▴ Recolher todos" : "▾ Abrir todos"}
                  </button>
                  <span id="resumo-lista" role="tooltip" className="bal">{resumo}</span>
                </span>
                <button type="button" className={`btn peq${mostrarDetalhe ? " ativo" : ""}`} aria-pressed={mostrarDetalhe}
                  aria-controls="painel-detalhe" onClick={() => setMostrarDetalhe(!mostrarDetalhe)}>
                  {mostrarDetalhe ? "Ocultar detalhe" : "Apresentar detalhe"}
                </button>
              </div>
            </div>
            <div className="rolagem">
              <div className="tabela">
                <div className="cab-sv">
                  <span style={{ paddingLeft: 30 }}>OS</span><span>Cliente</span><span>Equipamento / Área</span>
                  <span>Tipo de OS</span><span>Itens</span><span>Classificação</span><span>Fase</span>
                </div>
                {filtrados.map((s) => (
                  <LinhaServico key={s.os} s={s} aberto={abertos.has(s.os)} selecionado={sel?.os === s.os} selId={sel?.id}
                    aoAlternar={() => alternar(s.os)} aoApresentar={() => apresentar(s)}
                    aoEscolher={(i) => escolherItem(i)}
                    aoSelecionar={() => s.itens.length && sel?.os !== s.os && setSelId(s.itens[0].id)} />
                ))}
                {painel && filtrados.length === 0 && (
                  <p className="vazio">Nenhum serviço com esses filtros. Limpe os filtros para ver a fila inteira.</p>
                )}
              </div>
            </div>
          </section>

          {mostrarDetalhe && sel && svSel && (
            <Detalhe s={svSel} x={sel} eu={eu} obs={obs} setObs={setObs} erro={erroAcao} ocupado={ocupado}
              aoOcultar={() => setMostrarDetalhe(false)}
              aoDecidir={(a) => acao(() => api.decidir(sel.id, a, obs, sel.versao))}
              aoReclassificar={(c) => acao(() => api.reclassificar(sel.id, c, sel.versao))} />
          )}
        </div>
      </main>
    </div>
  );
}

function LinhaServico(p: {
  s: Servico; aberto: boolean; selecionado: boolean; selId?: number;
  aoAlternar: () => void; aoApresentar: () => void; aoEscolher: (i: Item) => void; aoSelecionar: () => void;
}) {
  const { s, aberto } = p;
  const bloco = `acomp-${s.os}`;
  const rotulo = `${aberto ? "Ocultar" : "Mostrar"} o acompanhamento da OS ${s.os}`;
  const n = s.itens.length;
  return (
    <div className={`servico${p.selecionado ? " sel" : ""}`}>
      <div className="linha-sv">
        <span style={{ display: "flex", alignItems: "center", gap: 2 }}>
          <button type="button" className="seta" onClick={p.aoAlternar} aria-expanded={aberto} aria-controls={bloco}
            aria-label={rotulo} title={rotulo}>{aberto ? "▾" : "▸"}</button>
          <button type="button" className="os-btn num" onClick={p.aoApresentar} aria-controls="painel-detalhe"
            title={`Apresentar o detalhe da OS ${s.os}`}>{s.os}</button>
        </span>
        <span style={{ fontWeight: 600 }}>{s.cliente}</span>
        <button type="button" className="celula-btn" onClick={p.aoSelecionar} aria-pressed={p.selecionado}>
          <span style={{ fontWeight: s.equipamento ? 600 : 500, color: s.equipamento ? "var(--tinta)" : "var(--sub)" }}>
            {s.equipamento || "Equipamento não informado"}
          </span>
          <span className="p12 sub">{s.area}</span>
        </button>
        <span>{s.tipo}</span>
        <span style={{ display: "flex", flexDirection: "column" }}>
          <span style={{ fontWeight: 600 }}>{n === 1 ? "1 item" : `${n} itens`}</span>
          <span className="p12 sub">{s.mix}</span>
        </span>
        <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 2 }}>
          <span className={`chip ${classeCls(s.cls)}`}>{s.cls}</span>
          {s.cls_sub && <span className="sub" style={{ fontSize: 11, lineHeight: "14px" }}>{s.cls_sub}</span>}
        </span>
        <span><span className="chip fase-chip">{s.fase_nome}</span></span>
      </div>

      {aberto && (
        <div className="acomp-fora">
          <section id={bloco} aria-label={`Acompanhamento da OS ${s.os}`} className="acomp">
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
              <h3>Acompanhamento da OS {s.os} · {s.equipamento || s.area}</h3>
              <button type="button" className="btn sem-borda" onClick={p.aoAlternar} aria-controls={bloco}>Ocultar ▴</button>
            </div>
            <Etapas etapas={s.etapas} />
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <EtapaAtual agora={s.agora} />
              <span className="p12 sub">Programação: {s.prog_txt} {s.prog_meta}</span>
            </div>
            {n > 0 && (
              <div style={{ display: "flex", flexDirection: "column" }}>
                <div className="itens-cab">
                  <span>Materiais, peças e serviços ({n})</span><span>Qtd.</span><span>Classificação</span>
                  <span>Confiança</span><span>Fase</span>
                </div>
                {s.itens.map((i) => (
                  <div key={i.id} className={`item-linha${i.id === p.selId ? " sel" : ""}`}>
                    <button type="button" className="celula-btn" onClick={() => p.aoEscolher(i)} aria-pressed={i.id === p.selId}>
                      <span style={{ fontWeight: 600 }}>{i.item}</span>
                      <span className="p12 sub">{i.natureza} · {i.situacao}</span>
                    </button>
                    <span className="num" style={{ display: "flex", flexDirection: "column" }}>
                      <span>{i.qtd}</span>{i.presumida && <span className="presumida">presumida</span>}
                    </span>
                    <span><span className={`chip ${classeCls(i.cls)}`} style={{ padding: "2px 8px" }}>{i.cls}</span></span>
                    <span className={`conf-${i.conf}`} style={{ fontWeight: 700 }}>{CONF_SIMB[i.conf]} {i.conf}</span>
                    <span className="sub" style={{ fontWeight: 600 }}>{i.fase_nome}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function Detalhe(p: {
  s: Servico; x: Item; eu: Usuario; obs: string; setObs: (v: string) => void; erro: string; ocupado: boolean;
  aoOcultar: () => void; aoDecidir: (a: "aprovar" | "devolver" | "reprovar") => void; aoReclassificar: (c: string) => void;
}) {
  const { s, x, eu } = p;
  const pos = s.itens.findIndex((i) => i.id === x.id) + 1;
  const minhaFase = eu.nivel === 1 ? "n1" : "n2";
  const podeAgir = x.fase === minhaFase;
  const ehN1 = x.fase === "n1" && eu.nivel === 1;
  const bloqueado = ehN1 && x.cls === "A definir";
  const conflito = eu.nivel === 2 && s.conflito_n2;
  const contratoTxt = s.cliente !== "HGG"
    ? "Contrato não avaliado para este cliente. O agente só identifica o item e a necessidade de Pedido."
    : x.contrato_item || "Catálogo do contrato HGG não conferido para este item.";
  const status: Record<string, string> = {
    relatorio: "O relatório precisa ser corrigido no Auvo, ou o agente refaz a identificação na próxima rodada.",
    n1: "Aguardando o Nível 1 (Hely).",
    n2: "Aguardando o Nível 2 (Renato).",
    whats: "Solicitação de orçamento pronta para o orçamentista.",
    pedido: "Item no Pedido. Aguardando o Pedido ser criado e vinculado à OS.",
    fim: "Item concluído. A trilha completa fica guardada para auditoria.",
    reprovado: "Item reprovado. A justificativa fica registrada na trilha.",
  };
  return (
    <aside id="painel-detalhe" aria-label="Detalhe do item" className="detalhe">
      <div style={{ display: "flex", justifyContent: "flex-end", margin: "-10px -8px -14px 0" }}>
        <button type="button" className="btn sem-borda peq" style={{ color: "var(--sub)" }} onClick={p.aoOcultar}>Ocultar ✕</button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", justifyContent: "space-between" }}>
          <span className="os-titulo nunito num">OS {s.os}</span>
          <span className="chip fase-chip">{x.fase_nome}</span>
        </div>
        <span className="sub">{s.cliente} · {s.equipamento || "Equipamento não informado"} · {s.area} · {s.tipo}</span>
        {s.origem && <span className="sub">Pedido de origem no WhatsApp: <strong style={{ color: "var(--tinta)" }}>{s.origem}</strong></span>}
        {s.tem_link && <a href={api.linkAuvo(s.os)} target="_blank" rel="noopener noreferrer" style={{ fontWeight: 600 }}>Abrir a OS no Auvo</a>}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span className="rotulo">Item selecionado · {pos} de {s.itens.length} do serviço</span>
        <span style={{ fontSize: 16, lineHeight: "22px", fontWeight: 700 }}>{x.item}</span>
        <span className="sub">{x.natureza} · {x.situacao} · quantidade {x.qtd}{x.presumida ? " (presumida)" : ""}</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span className="rotulo">Evidência no relatório</span>
        <blockquote>{s.relato || "Relatório vazio no Auvo."}</blockquote>
        {x.evidencia && <span className="p12 sub">Trecho usado pelo agente: <strong style={{ color: "var(--tinta)" }}>“{x.evidencia}”</strong></span>}
        <span className="sub">Campo "Utilizou peça" no Auvo: <strong style={{ color: "var(--tinta)" }}>{s.utilizou || "—"}</strong></span>
        <span className={x.val_ok ? "ok" : "aviso"}>{x.val_ok ? "●" : "▲"} {x.val_txt}</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span className="rotulo">Sugestão do agente</span>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
          <span className={`chip ${classeCls(x.cls)}`}>{x.cls}</span>
          <span className={`conf-${x.conf}`} style={{ fontWeight: 700 }}>{CONF_SIMB[x.conf]} Confiança {x.conf}</span>
        </div>
        <span className="sub">{contratoTxt}</span>
        {ehN1 && (
          <div className="campo">
            <label htmlFor="d-cls" style={{ fontSize: 12, color: "var(--tinta)" }}>Corrigir a classificação</label>
            <select id="d-cls" value={x.cls} disabled={p.ocupado} onChange={(e) => p.aoReclassificar(e.target.value)}>
              {s.cliente === "HGG" && <option>Contrato HGG</option>}
              <option>Pedido de compra</option>
              <option>A definir</option>
            </select>
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span className="rotulo">Trilha de aprovação</span>
        {x.trilha.map((t) => (
          <div key={t.nivel} className="trilha-linha">
            <span><strong>{t.nivel}</strong> · {t.quem}</span>
            <span style={{ fontWeight: 700, color: t.estado === "Aprovado" ? "var(--ok)" : t.estado === "Reprovado" ? "var(--erro)" : t.estado === "Aguardando" ? "var(--atencao)" : "var(--sub)" }}>
              {t.estado === "Aprovado" ? "● " : t.estado === "Reprovado" ? "▼ " : t.estado === "Aguardando" ? "▲ " : ""}{t.estado}
            </span>
          </div>
        ))}
      </div>

      {podeAgir ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingTop: 4 }}>
          <span style={{ fontWeight: 700 }}>Decisão de Nível {eu.nivel} · {eu.nome}</span>
          {conflito && <span className="aviso">▲ Você é o técnico autor desta OS. A observação é obrigatória.</span>}
          <div className="campo">
            <label htmlFor="d-obs" style={{ fontSize: 12, color: "var(--tinta)" }}>Observação (obrigatória para reprovar ou devolver)</label>
            <textarea id="d-obs" rows={3} value={p.obs} placeholder="Escreva o motivo ou a correção" onChange={(e) => p.setObs(e.target.value)} />
          </div>
          {bloqueado && <span className="aviso">▲ Escolha entre Contrato HGG e Pedido de compra antes de confirmar.</span>}
          {p.erro && <span className="aviso" role="alert">▲ {p.erro}</span>}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button type="button" className="btn cheio" style={{ flex: "1 1 150px" }} disabled={bloqueado || p.ocupado} onClick={() => p.aoDecidir("aprovar")}>
              {ehN1 ? "Confirmar sugestão" : "Aprovar"}
            </button>
            <button type="button" className="btn" style={{ flex: "1 1 150px" }} disabled={p.ocupado} onClick={() => p.aoDecidir("devolver")}>
              {ehN1 ? "Devolver ao agente" : "Devolver para correção"}
            </button>
            <button type="button" className="btn perigo" style={{ flex: "1 1 110px" }} disabled={p.ocupado} onClick={() => p.aoDecidir("reprovar")}>Reprovar</button>
          </div>
        </div>
      ) : (
        <p className="caixa-info">{status[x.fase]}</p>
      )}
    </aside>
  );
}
