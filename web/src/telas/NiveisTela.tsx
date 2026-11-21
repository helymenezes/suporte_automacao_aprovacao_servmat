import { useCallback, useEffect, useState } from "react";
import { api, ErroApi } from "../api";
import { Cabecalho } from "../componentes/Cabecalho";
import type { Nivel, Niveis, Usuario } from "../tipos";

const FIXOS_PEDIDO = ["Solicitação de orçamento ao orçamentista", "Pedido e proposta ao cliente",
  "Aprovação do cliente pela planilha", "Nova OS de execução, aprovada por Hely no Telegram", "Finalização e cobrança ao orçamentista"];
const FIXOS_CONTRATO = ["Pedido criado e vinculado à OS", "Celso autoriza o Pedido", "Envio ao faturamento",
  "Pendência de lançamento no contrato, até a fonte responsável registrar"];
const FORA = [
  { quem: "Celso", oque: "autoriza o Pedido de contrato HGG", quando: "Depois do Pedido criado e vinculado à OS. Aprovar dispara o envio ao faturamento; devolver e reprovar exigem motivo." },
  { quem: "Cliente", oque: "aceite comercial", quando: "Lido na planilha de aprovação. Aceite parcial libera só os itens e quantidades aceitos." },
  { quem: "Hely", oque: "nova OS e mudança de programação no Auvo", quando: "Nova OS: aprovação no Telegram. Data ou técnico: proposta com OTP na central." },
];

function Seta({ cima }: { cima: boolean }) {
  return (
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d={cima ? "M6 15l6-6 6 6" : "M6 9l6 6 6-6"} />
    </svg>
  );
}

export function NiveisTela({ eu, aoSair }: { eu: Usuario; aoSair: () => void }) {
  const [dados, setDados] = useState<Niveis | null>(null);
  const [lista, setLista] = useState<Nivel[]>([]);
  const [contratos, setContratos] = useState<Record<string, boolean>>({});
  const [mudou, setMudou] = useState(false);
  const [msg, setMsg] = useState("");
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    try {
      const d = await api.niveis();
      setDados(d);
      setLista(d.niveis);
      setContratos(Object.fromEntries(d.contratos.map((c) => [c.cliente, c.ligado])));
      setMudou(false);
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) aoSair();
      else setErro(e instanceof Error ? e.message : "Falha ao carregar.");
    }
  }, [aoSair]);
  useEffect(() => { carregar(); }, [carregar]);

  const ed = !!dados?.pode_editar;
  const nomes = Object.fromEntries((dados?.usuarios ?? []).map((u) => [u.usuario, u.nome]));
  const troca = (k: number, patch: Partial<Nivel>) => { setLista(lista.map((n, i) => (i === k ? { ...n, ...patch } : n))); setMudou(true); setMsg(""); };
  const mover = (k: number, d: number) => {
    const j = k + d;
    if (j < 0 || j >= lista.length) return;
    const nova = lista.slice();
    [nova[k], nova[j]] = [nova[j], nova[k]];
    setLista(nova); setMudou(true); setMsg("");
  };

  async function salvar() {
    setErro("");
    try {
      const r = await api.salvarNiveis(lista, contratos);
      setMsg(`Rota versão ${r.versao} gravada. Vale para os itens que entrarem a partir de agora.`);
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao gravar.");
    }
  }

  const ativos = lista.filter((n) => n.ativo);
  const humano = (n: Nivel) => `${nomes[n.usuario ?? ""] ?? "[aprovador]"} — ${n.papel}`;
  const rotas = [
    { nome: "Pedido", classe: "cls-Pedido", passos: ["Agente identifica e classifica"], humanos: ativos.filter((n) => n.compra).map(humano), fim: FIXOS_PEDIDO },
    { nome: "Contrato HGG", classe: "cls-Contrato", passos: ["Agente identifica e confere o item do contrato"], humanos: ativos.filter((n) => n.contrato).map(humano), fim: FIXOS_CONTRATO },
  ];

  return (
    <div style={{ minHeight: "100vh" }}>
      <Cabecalho eu={eu} aoSair={aoSair} pilulas={dados && <>
        <span className="pilula aviso">{ativos.length} níveis ligados</span>
        <span className="pilula">Rota versão {dados.versao}{mudou ? " · alterações não gravadas" : ""}</span>
        <span className="pilula">{ed ? "Você pode alterar esta tela" : "Só o administrador altera esta tela"}</span>
      </>} />
      <main className="fila" style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "flex-start", gap: 24 }}>
        <section aria-label="Níveis" style={{ flex: "999 1 620px", minWidth: 0, display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", flexDirection: "column", maxWidth: 640 }}>
              <h2 style={{ margin: 0, fontSize: 15, lineHeight: "22px", fontWeight: 700 }}>Níveis, na ordem em que aprovam</h2>
              <span className="sub">Os níveis internos aprovam antes do Pedido. Cada gravação cria uma nova versão da rota, que vale para os itens que entrarem depois. Os itens já na fila seguem a versão com que entraram.</span>
            </div>
            {ed && (
              <div style={{ display: "flex", gap: 8 }}>
                <button type="button" className="btn" onClick={() => { setLista([...lista, { papel: "", usuario: null, compra: true, contrato: false, ativo: false }]); setMudou(true); }}>Acrescentar nível</button>
                <button type="button" className="btn cheio" disabled={!mudou} onClick={salvar}>Gravar nova versão</button>
              </div>
            )}
          </div>
          {msg && <span className="ok" role="status">● {msg}</span>}
          {erro && <p className="erro-caixa" role="alert">{erro}</p>}

          {lista.map((n, k) => (
            <div key={k} className="cartao" style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 14, padding: "14px 16px", opacity: n.ativo ? 1 : 0.6 }}>
              <span className="nunito num" style={{ fontSize: 28, lineHeight: "32px", color: "var(--teal)", width: 34 }}>{k + 1}</span>
              <div className="campo" style={{ flex: "1 1 170px" }}>
                <label htmlFor={`papel-${k}`}>Papel do nível</label>
                <input id={`papel-${k}`} value={n.papel} disabled={!ed} placeholder="Ex.: Autoriza o Pedido" onChange={(e) => troca(k, { papel: e.target.value })} />
              </div>
              <div className="campo" style={{ flex: "1 1 170px" }}>
                <label htmlFor={`quem-${k}`}>Quem aprova</label>
                <select id={`quem-${k}`} value={n.usuario ?? ""} disabled={!ed} onChange={(e) => troca(k, { usuario: e.target.value || null })}>
                  <option value="">— escolher —</option>
                  {(dados?.usuarios ?? []).map((u) => <option key={u.usuario} value={u.usuario}>{u.nome}</option>)}
                </select>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="p12 sub" style={{ fontWeight: 600 }}>Entra na rota de</span>
                <div style={{ display: "flex", gap: 6 }}>
                  <button type="button" disabled={!ed} aria-pressed={n.compra} className={`alterna alterna-pedido`} onClick={() => troca(k, { compra: !n.compra })}>Pedido</button>
                  <button type="button" disabled={!ed} aria-pressed={n.contrato} className={`alterna alterna-contrato`} onClick={() => troca(k, { contrato: !n.contrato })}>Contrato HGG</button>
                </div>
              </div>
              {ed && (
                <div style={{ display: "flex", gap: 6, alignItems: "flex-end", marginLeft: "auto" }}>
                  <button type="button" className="btn fino peq" style={{ minHeight: 44, minWidth: 96, color: n.ativo ? "var(--ok)" : "var(--sub)" }}
                    aria-pressed={n.ativo} onClick={() => troca(k, { ativo: !n.ativo })}>{n.ativo ? "● Ligado" : "Desligado"}</button>
                  <button type="button" className="icone" aria-label="Subir este nível" onClick={() => mover(k, -1)}><Seta cima /></button>
                  <button type="button" className="icone" aria-label="Descer este nível" onClick={() => mover(k, 1)}><Seta cima={false} /></button>
                  <button type="button" className="icone perigo" aria-label="Remover este nível"
                    onClick={() => { setLista(lista.filter((_, i) => i !== k)); setMudou(true); }}>
                    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 7h16" /><path d="M9 7V4h6v3" /><path d="M6 7l1 13h10l1-13" /></svg>
                  </button>
                </div>
              )}
              {!ed && <span className="p12" style={{ marginLeft: "auto", fontWeight: 700, color: n.ativo ? "var(--ok)" : "var(--sub)" }}>{n.ativo ? "● Ligado" : "Desligado"}</span>}
            </div>
          ))}
          <p className="sub" style={{ margin: 0 }}>Todo nível pode aprovar, reprovar ou devolver com observação. Só o 1º nível corrige a classificação e devolve ao agente. Remover um nível não apaga o histórico do que ele já decidiu.</p>
        </section>

        <aside style={{ flex: "1 1 380px", minWidth: 0, display: "flex", flexDirection: "column", gap: 16 }}>
          <section aria-label="Rotas" className="cartao" style={{ padding: 18, gap: 14 }}>
            <h2 style={{ margin: 0, fontSize: 15, lineHeight: "22px", fontWeight: 700 }}>Como fica o caminho de cada item</h2>
            {rotas.map((r) => (
              <div key={r.nome} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <span><span className={`chip ${r.classe}`}>{r.nome}</span></span>
                <ol style={{ margin: 0, padding: "0 0 0 20px", display: "flex", flexDirection: "column", gap: 4 }}>
                  {r.passos.map((t) => <li key={t} className="sub">{t}</li>)}
                  {r.humanos.map((t, i) => <li key={i} style={{ fontWeight: 700 }}>{t}</li>)}
                  {r.fim.map((t) => <li key={t} className="sub">{t}</li>)}
                </ol>
              </div>
            ))}
          </section>

          <section aria-label="Decisões fora dos níveis" className="cartao" style={{ padding: 18, gap: 10 }}>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <h2 style={{ margin: 0, fontSize: 15, lineHeight: "22px", fontWeight: 700 }}>Decisões fora dos níveis</h2>
              <span className="sub">São independentes da aprovação interna. Uma não substitui a outra.</span>
            </div>
            {FORA.map((f) => (
              <div key={f.quem} style={{ display: "flex", flexDirection: "column", gap: 2, paddingTop: 8, borderTop: "1px solid var(--linha)" }}>
                <span style={{ fontWeight: 700 }}>{f.quem} · {f.oque}</span>
                <span className="sub">{f.quando}</span>
              </div>
            ))}
          </section>

          <section aria-label="Critério de contrato por cliente" className="cartao" style={{ padding: 18, gap: 10 }}>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <h2 style={{ margin: 0, fontSize: 15, lineHeight: "22px", fontWeight: 700 }}>Critério de contrato por cliente</h2>
              <span className="sub">Ligado: o agente confere cada item contra o catálogo do contrato. Desligado: a fila mostra "Contrato não avaliado". Só liga quem tem catálogo carregado.</span>
            </div>
            {(dados?.contratos ?? []).map((c) => {
              const ligado = !!contratos[c.cliente];
              return (
                <div key={c.cliente} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, paddingTop: 8, borderTop: "1px solid var(--linha)" }}>
                  <span style={{ fontWeight: 700 }}>{c.cliente}{!c.tem_catalogo && <span className="p12 sub" style={{ fontWeight: 500 }}> · sem catálogo</span>}</span>
                  <button type="button" className="alterna alterna-contrato" style={{ minWidth: 120 }} aria-pressed={ligado}
                    disabled={!ed || (!c.tem_catalogo && !ligado)}
                    onClick={() => { setContratos({ ...contratos, [c.cliente]: !ligado }); setMudou(true); }}>{ligado ? "● Ligado" : "Desligado"}</button>
                </div>
              );
            })}
          </section>
        </aside>
      </main>
    </div>
  );
}
