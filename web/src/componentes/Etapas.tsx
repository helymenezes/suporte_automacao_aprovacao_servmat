import type { Agora, Etapa } from "../tipos";

const SIMBOLO: Record<string, string> = { feito: "✓", atual: "", pendente: "", na: "–", seminfo: "?", reprovado: "×" };
const ESTADO: Record<string, string> = {
  feito: "Concluída", atual: "Em andamento", pendente: "Pendente", na: "Não se aplica",
  seminfo: "Sem informação", reprovado: "Reprovado",
};

/** Barra de etapas. `compacta` = só as bolinhas (celular); senão bolinhas com o nome embaixo. */
export function Etapas({ etapas, compacta = false }: { etapas: Etapa[]; compacta?: boolean }) {
  return (
    <ol aria-label="Etapas do serviço" className={compacta ? "etapas compacta" : "etapas"}>
      {etapas.map((e) => (
        <li key={e.nome} className={`e-${e.estado}`}>
          {compacta ? (
            <>
              <span aria-hidden="true" className="bola">{SIMBOLO[e.estado]}</span>
              <span className="sr">{e.nome} · {ESTADO[e.estado]}</span>
              <span aria-hidden="true" className="traco" />
            </>
          ) : (
            <>
              <span aria-hidden="true" style={{ display: "flex", alignItems: "center" }}>
                <span className="bola">{SIMBOLO[e.estado]}</span>
                <span className="traco" />
              </span>
              <span className="rot">
                {e.nome}
                <span className="sr"> · {ESTADO[e.estado]}</span>
              </span>
            </>
          )}
        </li>
      ))}
    </ol>
  );
}

export function EtapaAtual({ agora, mostrarPosicao = false }: { agora: Agora | null; mostrarPosicao?: boolean }) {
  if (!agora) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {mostrarPosicao && <span className="p12 sub">Etapa {agora.pos} de {agora.total}</span>}
      <p style={{ margin: 0 }}>
        <strong className={`cor-${agora.estado}`}>{agora.nome}</strong> · {agora.txt}
      </p>
      {agora.quem && (
        <span className="p12 sub">
          {agora.prox && <>Próxima ação: <strong style={{ color: "var(--tinta)" }}>{agora.prox}</strong> · </>}
          Responsável: <strong style={{ color: "var(--tinta)" }}>{agora.quem}</strong>
        </span>
      )}
    </div>
  );
}

const CLS_CLASSE: Record<string, string> = {
  "Contrato HGG": "cls-Contrato", "Pedido de compra": "cls-Pedido", "A definir": "cls-Adefinir", Misto: "cls-Misto",
};

export function classeCls(cls: string): string {
  return CLS_CLASSE[cls] ?? "cls-Adefinir";
}
