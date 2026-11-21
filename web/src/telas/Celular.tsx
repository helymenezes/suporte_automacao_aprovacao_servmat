import { useCallback, useEffect, useRef, useState } from "react";
import { api, ErroApi } from "../api";
import { classeCls, EtapaAtual, Etapas } from "../componentes/Etapas";
import type { Painel, Usuario } from "../tipos";

type Acao = "aprovar" | "reprovar" | "devolver";
const OPCOES: { acao: Acao; nome: string }[] = [
  { acao: "aprovar", nome: "Aprovar" },
  { acao: "reprovar", nome: "Reprovar" },
  { acao: "devolver", nome: "Devolver para correção" },
];

function tipoGravacao(): string {
  for (const t of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"]) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t)) return t;
  }
  return "";
}

/** Tela do celular: cada pessoa vê só os serviços com itens esperando o nível dela. */
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
  const [gravando, setGravando] = useState(false);
  const [audioId, setAudioId] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState("");
  const [transcricao, setTranscricao] = useState("");
  const [avisoAudio, setAvisoAudio] = useState("");
  const gravador = useRef<MediaRecorder | null>(null);
  const carregar = useCallback(async () => {
    try {
      setPainel(await api.painel());
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) aoSair();
      else setErro(e instanceof Error ? e.message : "Falha ao carregar.");
    }
  }, [aoSair]);
  useEffect(() => { carregar(); }, [carregar]);

  const fila = (painel?.servicos ?? []).filter((s) => s.itens.some((i) => i.minha_vez));
  const s = (painel?.servicos ?? []).find((x) => x.os === osSel);
  const x = s?.itens.find((i) => i.id === itemSel) ?? s?.itens.find((i) => i.minha_vez) ?? s?.itens[0];
  const podeDecidir = !!x && x.minha_vez;
  const exige = decisao === "reprovar" || decisao === "devolver" || (podeDecidir && !!s?.conflito);
  const textoFinal = [obs.trim(), transcricao.trim() ? `[Áudio] ${transcricao.trim()}` : ""].filter(Boolean).join("\n");
  const pode = podeDecidir && !!decisao && (!exige || !!textoFinal) && !ocupado && !gravando;

  function limparAudio() {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioId(null); setAudioUrl(""); setTranscricao(""); setAvisoAudio("");
  }

  function abrir(os: string) {
    setOsSel(os); setItemSel(null); setAcomp(false); setDetalhe(false); setDecisao(""); setObs(""); setMsg(""); setErro("");
    limparAudio();
  }

  async function alternarGravacao() {
    if (!x) return;
    if (gravando) {
      gravador.current?.stop();
      return;
    }
    setAvisoAudio("");
    const tipo = tipoGravacao();
    if (!tipo || !navigator.mediaDevices?.getUserMedia) {
      setAvisoAudio("Este navegador não grava áudio. Escreva a observação.");
      return;
    }
    try {
      const fluxo = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(fluxo, { mimeType: tipo });
      const partes: Blob[] = [];
      rec.ondataavailable = (e) => e.data.size && partes.push(e.data);
      rec.onstop = async () => {
        fluxo.getTracks().forEach((t) => t.stop());
        setGravando(false);
        const blob = new Blob(partes, { type: tipo.split(";")[0] });
        limparAudio();
        setAudioUrl(URL.createObjectURL(blob));
        setAvisoAudio("Enviando o áudio…");
        try {
          const r = await api.enviarAudio(x.id, blob);
          setAudioId(r.id);
          setTranscricao(r.transcricao);
          setAvisoAudio(r.transcrito ? "Confira o texto antes de enviar." :
            r.transcricao_ligada ? "Não foi possível transcrever. Escreva o que disse no áudio." :
              "Transcrição automática desligada. Escreva o resumo do áudio.");
        } catch (e) {
          setAvisoAudio(e instanceof Error ? e.message : "Falha ao enviar o áudio.");
        }
      };
      gravador.current = rec;
      rec.start();
      setGravando(true);
    } catch {
      setAvisoAudio("Sem permissão para usar o microfone.");
    }
  }

  async function enviar() {
    if (!x || !decisao) return;
    setOcupado(true); setErro("");
    try {
      const r = await api.decidir(x.id, decisao, textoFinal, x.versao, audioId ?? undefined);
      setMsg(`${x.item}: ${r.fase_nome}.`);
      setDecisao(""); setObs(""); setItemSel(null); limparAudio();
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
            {eu.niveis.length ? `Nível ${eu.niveis.join(" e ")}` : "Consulta"} · {eu.nome.split(" ")[0]}
          </span>
          <h1>Avaliação no celular</h1>
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
                  {f.itens.filter((i) => i.minha_vez).length} de {f.itens.length}<br />itens
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
                <button type="button" className="btn fino" style={{ flex: "1 1 0", whiteSpace: "nowrap", padding: "0 8px" }} aria-expanded={acomp} aria-controls="m-acomp"
                  onClick={() => setAcomp(!acomp)}>{acomp ? "▴ Ocultar etapas" : "▾ Acompanhamento"}</button>
                <button type="button" className={`btn${detalhe ? " ativo" : ""}`} style={{ flex: "1 1 0", whiteSpace: "nowrap", padding: "0 8px" }} aria-pressed={detalhe}
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
                  onClick={() => { setItemSel(i.id); setDecisao(""); setObs(""); setErro(""); limparAudio(); }}>
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
                {s.conflito && <span className="aviso p12">▲ Você é o técnico autor desta OS. A observação é obrigatória.</span>}
                <section aria-label="Decisão" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span className="p12" style={{ fontWeight: 700 }}>Sua decisão · {x.item}</span>
                  <div className="decisoes">
                    {OPCOES.filter((o) => !(o.acao === "aprovar" && x.pode_reclassificar && x.cls === "A definir")).map((o) => (
                      <button key={o.acao} type="button" className={`decisao d-${o.acao}`} aria-pressed={decisao === o.acao}
                        onClick={() => { setDecisao(o.acao); setMsg(""); }}>{o.nome}</button>
                    ))}
                  </div>
                </section>
                <div className="campo">
                  <label htmlFor="a-obs" style={{ fontSize: 12, color: "var(--tinta)", fontWeight: 700 }}>Observação{exige ? " (obrigatória)" : ""}</label>
                  <textarea id="a-obs" rows={2} value={obs} placeholder="Motivo da reprovação ou a correção técnica" onChange={(e) => setObs(e.target.value)} />
                </div>
                <section aria-label="Áudio" className="cartao">
                  <button type="button" className={`btn ${gravando ? "gravando" : ""}`} aria-pressed={gravando} onClick={alternarGravacao}
                    style={{ minHeight: 48, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
                    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0" /><path d="M12 18v3" /></svg>
                    <span>{gravando ? "Gravando… toque para parar" : audioId ? "Gravar outro áudio" : "Gravar áudio"}</span>
                  </button>
                  {audioUrl && <audio controls src={audioUrl} style={{ width: "100%" }} />}
                  {avisoAudio && <span className="p12 sub" role="status">{avisoAudio}</span>}
                  {audioId && (
                    <div className="campo">
                      <label htmlFor="a-transc" style={{ fontSize: 12, color: "var(--tinta)", fontWeight: 700 }}>Transcrição do áudio</label>
                      <textarea id="a-transc" rows={3} value={transcricao} placeholder="O texto do áudio aparece aqui para você conferir"
                        onChange={(e) => setTranscricao(e.target.value)} />
                      <span className="p12 sub">O áudio original fica anexado à decisão.</span>
                    </div>
                  )}
                </section>
              </>
            ) : (
              <p className="caixa-info">
                {x.fase === "nivel" ? `Este item aguarda ${x.nivel_quem || "outro aprovador"} no ${x.fase_nome}.` : `Item em ${x.fase_nome}.`}
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
