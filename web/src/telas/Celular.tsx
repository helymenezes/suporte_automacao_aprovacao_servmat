import { useCallback, useEffect, useState } from "react";
import { api, ErroApi } from "../api";
import { classeCls, EtapaAtual, Etapas } from "../componentes/Etapas";
import type { Painel, Usuario } from "../tipos";

type Acao = "aprovar" | "reprovar" | "devolver";
const OPCOES: { acao: Acao; nome: string }[] = [
  { acao: "aprovar", nome: "Aprovar" },
  { acao: "reprovar", nome: "Reprovar" },
  { acao: "devolver", nome: "Devolver para correção" },
];

/** Tela do celular: o avaliador vê só os serviços com itens no nível dele (Renato = Nível 2, Hely = Nível 1). */
export function Celular({ eu, aoSair }: { eu: Usuario; aoSair: () => void }) {
  const [painel, setPainel] = useState<Painel | null>(null);
  const [osSel, setOsSel] = useState<string | null>(null);
  const [itemSel, setItemSel] = useState<number | null>(null);
  const [acomp, setAcomp] = useState(false);
  const [detalhe, setDetalhe] = useState(false);
  const [decisao, setDecisao] = useState<Acao | "">("");
  const [obs, setObs] = useState("");
  const [msg, setMsg] = useState("");
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const minhaFase = eu.nivel === 1 ? "n1" : "n2";
  const carregar = useCallback(async () => {
    try {
      setPainel(await api.painel());
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) aoSair();
      else setErro(e instanceof Error ? e.message : "Falha ao carregar.");
    }
  }, [aoSair]);
  useEffect(() => { carregar(); }, [carregar]);

  const fila = (painel?.servicos ?? []).filter((s) => s.itens.some((i) => i.fase === minhaFase));
  const s = (painel?.servicos ?? []).find((x) => x.os === osSel);
  const x = s?.itens.find((i) => i.id === itemSel) ?? s?.itens.find((i) => i.fase === minhaFase) ?? s?.itens[0];
  const podeDecidir = !!x && x.fase === minhaFase;
  const exige = decisao === "reprovar" || decisao === "devolver" || (eu.nivel === 2 && !!s?.conflito_n2);
  const pode = podeDecidir && !!decisao && (!exige || !!obs.trim()) && !ocupado;

  function abrir(os: string) {
    setOsSel(os); setItemSel(null); setAcomp(false); setDetalhe(false); setDecisao(""); setObs(""); setMsg(""); setErro("");
  }

  async function enviar() {
    if (!x || !decisao) return;
    setOcupado(true); setErro("");
    try {
      const r = await api.decidir(x.id, decisao, obs, x.versao);
      setMsg(`${x.item}: ${r.fase_nome}.`);
      setDecisao(""); setObs(""); setItemSel(null);
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao enviar.");
      if (e instanceof ErroApi && e.status === 409) await carregar();
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="cel">
      <header className="cel-topo">
        <div style={{ display: "flex", flexDirection: "column" }}>
          <span style={{ fontSize: 11, lineHeight: "16px", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" }}>
            Nível {eu.nivel} · {eu.nome.split(" ")[0]}
          </span>
          <h1>{eu.nivel === 2 ? "Avaliação técnica" : "Confirmação do PCM"}</h1>
        </div>
        <button type="button" className="pilula" onClick={aoSair}>Sair</button>
      </header>

      <main>
        {!s && (
          <section aria-label="Fila" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span className="p12" style={{ fontWeight: 700 }}>Serviços aguardando você ({fila.length})</span>
            {msg && <span className="ok" role="status">● {msg}</span>}
            {painel && fila.length === 0 && <p className="caixa-info">Nada para avaliar agora.</p>}
            {fila.map((f) => (
              <button key={f.os} type="button" className="item-cel" onClick={() => abrir(f.os)}>
                <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                  <span className="num" style={{ fontWeight: 800 }}>OS {f.os}</span>
                  <span style={{ fontWeight: 600 }}>{f.equipamento || "Equipamento não informado"}</span>
                  <span className="p12 sub">{f.cliente} · {f.area}</span>
                </span>
                <span className="p12 sub" style={{ flexShrink: 0, textAlign: "right" }}>
                  {f.itens.filter((i) => i.fase === minhaFase).length} de {f.itens.length}<br />itens
                </span>
              </button>
            ))}
          </section>
        )}

        {s && x && (
          <>
            <button type="button" className="btn sem-borda peq" style={{ alignSelf: "flex-start", padding: 0 }} onClick={() => setOsSel(null)}>‹ Voltar à fila</button>
            <section aria-label="Serviço" className="cartao">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <button type="button" className="os-btn num" aria-controls="m-detalhe" onClick={() => setDetalhe(true)}
                  title="Apresentar o detalhe da OS">OS {s.os}</button>
                {s.tem_link && <a href={api.linkAuvo(s.os)} target="_blank" rel="noopener noreferrer" style={{ fontWeight: 600, fontSize: 13 }}>Abrir no Auvo</a>}
              </div>
              <div style={{ display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: 15, lineHeight: "21px", fontWeight: 700 }}>{s.equipamento || "Equipamento não informado"}</span>
                <span className="sub" style={{ fontSize: 13, lineHeight: "18px" }}>{s.cliente} · {s.area} · {s.tipo}</span>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button type="button" className="btn fino" style={{ flex: "1 1 0" }} aria-expanded={acomp} aria-controls="m-acomp"
                  onClick={() => setAcomp(!acomp)}>{acomp ? "▴ Ocultar etapas" : "▾ Acompanhamento"}</button>
                <button type="button" className={`btn${detalhe ? " ativo" : ""}`} style={{ flex: "1 1 0" }} aria-pressed={detalhe}
                  aria-controls="m-detalhe" onClick={() => setDetalhe(!detalhe)}>{detalhe ? "Ocultar detalhe" : "Apresentar detalhe"}</button>
              </div>
              {acomp && (
                <div id="m-acomp" style={{ borderTop: "1px solid var(--linha)", paddingTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                  <Etapas etapas={s.etapas} compacta />
                  <EtapaAtual agora={s.agora} mostrarPosicao />
                </div>
              )}
            </section>

            <section aria-label="Materiais, peças e serviços" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span className="p12" style={{ fontWeight: 700 }}>Materiais, peças e serviços ({s.itens.length}) · toque para avaliar</span>
              {s.itens.map((i) => (
                <button key={i.id} type="button" className="item-cel" aria-pressed={i.id === x.id}
                  onClick={() => { setItemSel(i.id); setDecisao(""); setObs(""); setErro(""); }}>
                  <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                    <span style={{ fontWeight: 700, fontSize: 14, lineHeight: "19px" }}>{i.item}</span>
                    <span className="p12 sub">{i.natureza} · {i.qtd}{i.presumida ? " (presumida)" : ""}</span>
                  </span>
                  <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2, flexShrink: 0 }}>
                    <span className={`chip ${classeCls(i.cls)}`} style={{ fontSize: 11, padding: "2px 8px" }}>{i.cls}</span>
                    <span className="sub" style={{ fontSize: 11, lineHeight: "14px", fontWeight: 600 }}>{i.fase_nome}</span>
                  </span>
                </button>
              ))}
            </section>

            {detalhe && (
              <section id="m-detalhe" aria-label="Detalhe do item" className="cartao" style={{ gap: 6 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                  <span className="rotulo">Detalhe · {x.item}</span>
                  <button type="button" className="btn sem-borda peq" style={{ color: "var(--sub)", flexShrink: 0 }} onClick={() => setDetalhe(false)}>Ocultar ✕</button>
                </div>
                <blockquote style={{ margin: 0, padding: "8px 10px", background: "var(--claro)", borderRadius: 6, fontSize: 13 }}>{s.relato}</blockquote>
                <span className="p12 sub">Campo "Utilizou peça" no Auvo: <strong style={{ color: "var(--tinta)" }}>{s.utilizou || "—"}</strong></span>
                <span className={`p12 ${x.val_ok ? "ok" : "aviso"}`}>{x.val_ok ? "●" : "▲"} {x.val_txt}</span>
                <span className="p12 sub">{x.contrato_item}</span>
                <span className="p12" style={{ fontWeight: 700 }}>{x.trilha.map((t) => `${t.nivel}: ${t.estado}`).join(" · ")}</span>
              </section>
            )}

            {podeDecidir ? (
              <>
                {s.conflito_n2 && eu.nivel === 2 && <span className="aviso p12">▲ Você é o técnico autor desta OS. A observação é obrigatória.</span>}
                <section aria-label="Decisão" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span className="p12" style={{ fontWeight: 700 }}>Sua decisão · {x.item}</span>
                  <div className="decisoes">
                    {OPCOES.filter((o) => !(o.acao === "aprovar" && x.fase === "n1" && x.cls === "A definir")).map((o) => (
                      <button key={o.acao} type="button" className={`decisao d-${o.acao}`} aria-pressed={decisao === o.acao}
                        onClick={() => { setDecisao(o.acao); setMsg(""); }}>{o.nome}</button>
                    ))}
                  </div>
                </section>
                <div className="campo">
                  <label htmlFor="a-obs" style={{ fontSize: 12, color: "var(--tinta)", fontWeight: 700 }}>Observação{exige ? " (obrigatória)" : ""}</label>
                  <textarea id="a-obs" rows={3} value={obs} placeholder="Motivo da reprovação ou a correção técnica" onChange={(e) => setObs(e.target.value)} />
                </div>
              </>
            ) : (
              <p className="caixa-info">
                {x.fase === "n1" ? "Este item ainda aguarda o Nível 1 (Hely). Você avalia depois que ele confirmar a classificação." : `Item em ${x.fase_nome}.`}
              </p>
            )}
          </>
        )}
      </main>

      {s && x && (
        <footer className="cel-rodape">
          {msg && <span className="ok p12" role="status">● {msg}</span>}
          {erro && <span className="aviso p12" role="alert">▲ {erro}</span>}
          <button type="button" className="btn cheio" disabled={!pode} onClick={enviar}>Enviar avaliação</button>
        </footer>
      )}
    </div>
  );
}
