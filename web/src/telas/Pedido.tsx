import { useCallback, useEffect, useState } from "react";
import { api, ErroApi } from "../api";
import { Cabecalho } from "../componentes/Cabecalho";
import type { Envio, LinhaPedido, Pedidos, Usuario } from "../tipos";

const quando = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";

function Duas({ cima, baixo, cor }: { cima: string; baixo?: string; cor?: string }) {
  return (
    <span style={{ display: "flex", flexDirection: "column" }}>
      <span style={{ fontWeight: 700, color: cor ?? "var(--tinta)" }}>{cima}</span>
      {baixo && <span className="p12 sub">{baixo}</span>}
    </span>
  );
}

function envioTxt(e: Envio | null, aguardando: boolean): { cima: string; baixo?: string; cor?: string } {
  if (!e) return { cima: "Não enviada", baixo: aguardando ? "Aguarda os níveis internos" : "", cor: "var(--sub)" };
  switch (e.estado) {
    case "ENVIADO": return { cima: "● Enviada", baixo: `${quando(e.em)} · ${e.destino} · recibo ${e.recibo.slice(-10)}`, cor: "var(--ok)" };
    case "SIMULADO": return { cima: "● Simulada", baixo: `${quando(e.em)} · piloto, nada saiu`, cor: "var(--info)" };
    case "INCERTO": return { cima: "▲ Incerta", baixo: "A conexão caiu: confira no WhatsApp", cor: "var(--atencao)" };
    case "FALHOU": return { cima: "▼ Falhou", baixo: e.motivo, cor: "var(--erro)" };
    default: return { cima: "Enviando…", cor: "var(--sub)" };
  }
}

const VINCULO: Record<string, [string, string]> = {
  vinculado: ["● Pedido", "var(--ok)"],
  a_conferir: ["▲ Vínculo a conferir", "var(--atencao)"],
  nao_localizado: ["▼ Pedido não localizado", "var(--erro)"],
};
const ACEITE: Record<string, [string, string]> = {
  aceito: ["● Aceito", "var(--ok)"], parcial: ["● Aceite parcial", "var(--ok)"], recusado: ["▼ Recusado", "var(--erro)"],
  aguardando: ["▲ Aguardando", "var(--atencao)"],
};
const CELSO: Record<string, [string, string]> = {
  autorizado: ["● Celso autorizou", "var(--ok)"], aguardando: ["▲ Aguardando Celso", "var(--atencao)"],
  devolvido: ["▲ Celso devolveu", "var(--atencao)"], reprovado: ["▼ Celso reprovou", "var(--erro)"],
};
const EXEC: Record<string, string> = { concluida: "Concluída", agendada: "Agendada", a_agendar: "A agendar" };

export function Pedido({ eu, aoSair }: { eu: Usuario; aoSair: () => void }) {
  const [dados, setDados] = useState<Pedidos | null>(null);
  const [filtro, setFiltro] = useState("");
  const [aberta, setAberta] = useState<string | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setDados(await api.pedidos());
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) aoSair();
      else setErro(e instanceof Error ? e.message : "Falha ao carregar.");
    }
  }, [aoSair]);
  useEffect(() => { carregar(); }, [carregar]);

  async function acao(fn: () => Promise<unknown>) {
    setOcupado(true); setErro("");
    try { await fn(); await carregar(); } catch (e) { setErro(e instanceof Error ? e.message : "Falha."); } finally { setOcupado(false); }
  }

  const linhas = (dados?.linhas ?? []).filter((l) => !filtro || l.grupo === filtro);
  const nOs = new Set(linhas.map((l) => l.os)).size;
  const integ = dados?.integracoes;

  return (
    <div style={{ minHeight: "100vh" }}>
      <Cabecalho eu={eu} aoSair={aoSair} pilulas={dados && <>
        <span className={`pilula${integ?.comercial ? "" : " aviso"}`}>Sistema comercial: {integ?.comercial ? `leitura ${quando(integ.comercial.ultima_em)}` : "sem leitura"}</span>
        <span className={`pilula${integ?.planilha ? "" : " aviso"}`}>Planilha do cliente: {integ?.planilha ? `leitura ${quando(integ.planilha.ultima_em)}` : "sem leitura"}</span>
        <span className={`pilula${dados.envio_real ? "" : " aviso"}`}>{dados.envio_real ? `WhatsApp real · ${dados.destino}` : "Envio simulado (piloto)"}</span>
      </>} />

      <main className="fila">
        {erro && <p className="erro-caixa" role="alert">{erro}</p>}
        <section aria-label="Situação dos Pedidos" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", justifyContent: "space-between" }}>
            <h2 style={{ margin: 0, fontSize: 18, lineHeight: "24px", fontWeight: 700 }}>Do Pedido à cobrança</h2>
            <span className="sub">Clique numa situação para filtrar. Clique de novo para ver todas.</span>
          </div>
          <div className="fases">
            {(dados?.grupos ?? []).map((g) => (
              <button key={g.chave} type="button" className="fase" aria-pressed={filtro === g.chave}
                onClick={() => setFiltro(filtro === g.chave ? "" : g.chave)}>
                <span className="rotulo">{g.nome}</span>
                <span className="qtd nunito num">{g.qtd}</span>
              </button>
            ))}
          </div>
        </section>

        <section aria-label="Pedidos por OS" className="lista" style={{ flex: "none" }}>
          <div className="lista-topo">
            <h2>Pedidos por OS</h2>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span className="sub">{nOs} OS · {linhas.length} linhas</span>
              <button type="button" className="btn fino peq" onClick={carregar}>Atualizar</button>
            </div>
          </div>
          <div className="rolagem">
            <div style={{ minWidth: 1180 }}>
              <div className="cab-ped">
                <span>OS</span><span>Cliente e itens</span><span>Solicitação</span><span>Pedido</span>
                <span>Cliente / Celso</span><span>Execução</span><span>Cobrança</span><span>NF</span>
              </div>
              {linhas.map((l) => {
                const chave = `${l.os}-${l.tipo}`;
                return (
                  <LinhaPed key={chave} l={l} adm={!!dados?.pode_agir} ocupado={ocupado} aberta={aberta === chave}
                    aoAbrir={() => setAberta(aberta === chave ? null : chave)}
                    aoSolicitar={() => acao(() => api.solicitar(l.os, l.tipo))}
                    aoCobrar={() => acao(() => api.cobrar(l.os, l.tipo))}
                    aoConferir={(id, d) => acao(() => api.conferirEnvio(id, d))}
                    aoRegistrar={(c) => acao(async () => { await api.registrar(l.os, l.tipo, c); setAberta(null); })} />
                );
              })}
              {dados && linhas.length === 0 && <p className="vazio">Nenhuma linha nesta situação.</p>}
            </div>
          </div>
        </section>

        <div className="sub" style={{ display: "flex", flexDirection: "column", gap: 4, maxWidth: 980 }}>
          <p style={{ margin: 0 }}>Pedido, vínculo com a OS, NF, Celso e execução vêm do sistema comercial; o aceite do cliente vem da planilha. Enquanto essas leituras não existem, o PCM registra à mão em "Registrar", e o registro fica na trilha da OS.</p>
          <p style={{ margin: 0 }}>"Solicitar ao orçamentista" e "Solicitar cobrança" são mensagens separadas, cada uma com destinatário, escopo, data e recibo. Envio incerto nunca é repetido sozinho: confira no WhatsApp e marque.</p>
        </div>
      </main>
    </div>
  );
}

function LinhaPed(p: {
  l: LinhaPedido; adm: boolean; ocupado: boolean; aberta: boolean; aoAbrir: () => void; aoSolicitar: () => void;
  aoCobrar: () => void; aoConferir: (id: number, d: "entregue" | "nao_entregue") => void; aoRegistrar: (c: Record<string, string>) => void;
}) {
  const { l } = p;
  const escopo = l.itens.map((i) => `${i.qtd}${i.presumida ? " (presumida)" : ""}`).join(" + ");
  const nomes = l.itens.map((i) => i.item).join(", ");
  const solic = envioTxt(l.solicitacao, l.aguardando);
  const vinc = VINCULO[l.vinculo];
  const cli = l.tipo === "contrato" ? CELSO[l.celso] : ACEITE[l.aceite];
  const cob = l.tipo === "contrato"
    ? { cima: l.grupo === "cobs" ? "● Faturamento" : "—", baixo: "Envio ao faturamento após a autorização de Celso", cor: l.grupo === "cobs" ? "var(--ok)" : "var(--sub)" }
    : envioTxt(l.cobranca, false);
  return (
    <div style={{ borderTop: "1px solid var(--linha)", background: l.pode_cobrar ? "#eef8f1" : "#fff" }}>
      <div className="linha-ped">
        <span style={{ display: "flex", flexDirection: "column" }}>
          <a href="/" className="num" style={{ fontWeight: 700 }}>{l.os}</a>
          <span className="p12 sub">{l.tipo === "contrato" ? "Contrato" : "Pedido de compra"}</span>
        </span>
        <span style={{ display: "flex", flexDirection: "column" }}>
          <span><strong>{l.cliente}</strong> · {nomes}</span>
          <span className="p12 sub">{escopo}{l.equipamento ? ` · ${l.equipamento}` : ""}</span>
        </span>
        <span style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
          <Duas {...solic} />
          {p.adm && l.pode_solicitar && (
            <button type="button" className="btn peq" disabled={p.ocupado} onClick={p.aoSolicitar}>
              {l.solicitacao?.estado === "FALHOU" ? "Tentar de novo" : "Solicitar ao orçamentista"}
            </button>
          )}
          {p.adm && l.solicitacao?.estado === "INCERTO" && <Conferir id={l.solicitacao.id} {...p} />}
        </span>
        <Duas cima={vinc ? `${vinc[0]}${l.vinculo === "vinculado" && l.pedido_num ? ` ${l.pedido_num}` : ""}` : (l.grupo === "vinc" ? "▲ Vínculo a conferir" : "—")}
          baixo={l.grupo === "vinc" && l.todos_aplicados && !l.vinculo ? "Peça já aplicada: pode existir Pedido" : (l.vinculo !== "vinculado" ? l.pedido_num : "")}
          cor={vinc?.[1] ?? (l.grupo === "vinc" ? "var(--atencao)" : "var(--sub)")} />
        <Duas cima={cli ? cli[0] : (l.tipo === "contrato" ? "—" : "Sem informação")} baixo={l.aceite_obs} cor={cli?.[1] ?? "var(--sub)"} />
        <Duas cima={EXEC[l.execucao] ?? "—"} baixo={l.todos_aplicados ? "Na visita de origem" : l.execucao_meta}
          cor={l.execucao === "concluida" ? "var(--ok)" : "var(--sub)"} />
        <span style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
          {p.adm && l.pode_cobrar ? (
            <button type="button" className="btn" style={{ borderWidth: 2, borderColor: "var(--ok)", color: "var(--ok)" }}
              disabled={p.ocupado} onClick={p.aoCobrar}>Solicitar cobrança ao orçamentista</button>
          ) : <Duas {...cob} />}
          {p.adm && l.cobranca?.estado === "INCERTO" && <Conferir id={l.cobranca.id} {...p} />}
        </span>
        <span style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
          <span className="num" style={{ fontWeight: 700 }}>{l.nf || "—"}</span>
          {p.adm && <button type="button" className="btn sem-borda peq" style={{ padding: 0 }} aria-expanded={p.aberta} onClick={p.aoAbrir}>Registrar</button>}
        </span>
      </div>
      {p.aberta && <Registro l={l} ocupado={p.ocupado} aoSalvar={p.aoRegistrar} aoFechar={p.aoAbrir} />}
    </div>
  );
}

function Conferir({ id, ocupado, aoConferir }: { id: number; ocupado: boolean; aoConferir: (id: number, d: "entregue" | "nao_entregue") => void }) {
  return (
    <span style={{ display: "flex", gap: 6 }}>
      <button type="button" className="btn peq" disabled={ocupado} onClick={() => aoConferir(id, "entregue")}>Chegou</button>
      <button type="button" className="btn fino peq" disabled={ocupado} onClick={() => aoConferir(id, "nao_entregue")}>Não chegou</button>
    </span>
  );
}

function Registro({ l, ocupado, aoSalvar, aoFechar }: { l: LinhaPedido; ocupado: boolean; aoSalvar: (c: Record<string, string>) => void; aoFechar: () => void }) {
  const [c, setC] = useState<Record<string, string>>({
    pedido_num: l.pedido_num, vinculo: l.vinculo, nf: l.nf, execucao: l.todos_aplicados ? "" : l.execucao,
    ...(l.tipo === "contrato" ? { celso: l.celso } : { aceite: l.aceite, aceite_obs: l.aceite_obs }),
  });
  const campo = (k: string, rotulo: string, opcoes?: [string, string][]) => (
    <div className="campo" key={k}>
      <label htmlFor={`r-${l.os}-${l.tipo}-${k}`}>{rotulo}</label>
      {opcoes ? (
        <select id={`r-${l.os}-${l.tipo}-${k}`} value={c[k] ?? ""} onChange={(e) => setC({ ...c, [k]: e.target.value })}>
          {opcoes.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
        </select>
      ) : (
        <input id={`r-${l.os}-${l.tipo}-${k}`} value={c[k] ?? ""} maxLength={120} onChange={(e) => setC({ ...c, [k]: e.target.value })} />
      )}
    </div>
  );
  const enviar = () => {
    const mudou: Record<string, string> = {};
    for (const [k, v] of Object.entries(c)) if (k !== "execucao" || !l.todos_aplicados) mudou[k] = v;
    aoSalvar(mudou);
  };
  return (
    <div style={{ padding: "0 16px 16px" }}>
      <div className="filtros" style={{ background: "var(--fundo)" }}>
        {campo("pedido_num", "Nº do Pedido")}
        {campo("vinculo", "Vínculo com a OS", [["", "—"], ["a_conferir", "A conferir"], ["vinculado", "Vinculado"], ["nao_localizado", "Não localizado"]])}
        {l.tipo === "contrato"
          ? campo("celso", "Celso", [["", "—"], ["aguardando", "Aguardando"], ["autorizado", "Autorizou"], ["devolvido", "Devolveu"], ["reprovado", "Reprovou"]])
          : <>{campo("aceite", "Cliente (planilha)", [["", "—"], ["aguardando", "Aguardando"], ["aceito", "Aceito"], ["parcial", "Aceite parcial"], ["recusado", "Recusado"]])}{campo("aceite_obs", "Obs. do aceite")}</>}
        {!l.todos_aplicados && campo("execucao", "Execução", [["", "—"], ["a_agendar", "A agendar"], ["agendada", "Agendada"], ["concluida", "Concluída"]])}
        {campo("nf", "NF")}
        <button type="button" className="btn cheio" disabled={ocupado} onClick={enviar}>Salvar registro</button>
        <button type="button" className="btn fino" onClick={aoFechar}>Cancelar</button>
      </div>
    </div>
  );
}
