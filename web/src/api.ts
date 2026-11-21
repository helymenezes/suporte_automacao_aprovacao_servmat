import type { Envio, Niveis, Nivel, Painel, Pedidos, Usuario } from "./tipos";

export class ErroApi extends Error {
  constructor(public status: number, mensagem: string) {
    super(mensagem);
  }
}

async function tratar<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `Erro ${r.status}`;
    try {
      const j = await r.json();
      if (typeof j.detail === "string") msg = j.detail;
    } catch {
      /* resposta sem JSON */
    }
    throw new ErroApi(r.status, msg);
  }
  return r.json() as Promise<T>;
}

async function chamar<T>(caminho: string, metodo = "GET", corpo?: unknown): Promise<T> {
  const r = await fetch(caminho, {
    method: metodo,
    credentials: "same-origin",
    headers: corpo !== undefined ? { "Content-Type": "application/json", "X-Servmat": "1" } : { "X-Servmat": "1" },
    body: corpo !== undefined ? JSON.stringify(corpo) : undefined,
  });
  return tratar<T>(r);
}

export type Acao = "aprovar" | "devolver" | "reprovar";

export const api = {
  eu: () => chamar<Usuario>("/api/eu"),
  entrar: (usuario: string, senha: string) => chamar<Usuario>("/api/login", "POST", { usuario, senha }),
  sair: () => chamar<{ ok: boolean }>("/api/logout", "POST", {}),
  painel: () => chamar<Painel>("/api/painel"),
  decidir: (id: number, acao: Acao, obs: string, versao: number, audio_id?: string) =>
    chamar<{ fase: string; fase_nome: string }>(`/api/itens/${id}/decisao`, "POST", { acao, obs, versao, audio_id }),
  reclassificar: (id: number, cls: string, versao: number) =>
    chamar<{ cls: string }>(`/api/itens/${id}/classificacao`, "POST", { cls, versao }),
  linkAuvo: (os: string) => `/api/os/${encodeURIComponent(os)}/auvo`,
  enviarAudio: async (id: number, blob: Blob) =>
    tratar<{ id: string; transcricao: string; transcrito: boolean; transcricao_ligada: boolean }>(
      await fetch(`/api/itens/${id}/audio`, {
        method: "POST", credentials: "same-origin", body: blob,
        headers: { "Content-Type": blob.type || "audio/webm", "X-Servmat": "1" },
      })),
  niveis: () => chamar<Niveis>("/api/niveis"),
  salvarNiveis: (niveis: Nivel[], contratos: Record<string, boolean>) =>
    chamar<{ versao: number }>("/api/niveis", "PUT", {
      niveis: niveis.map(({ papel, usuario, compra, contrato, ativo }) => ({ papel, usuario, compra, contrato, ativo })),
      contratos,
    }),
  pedidos: () => chamar<Pedidos>("/api/pedidos"),
  solicitar: (os: string, tipo: string) => chamar<Envio>(`/api/pedidos/${os}/${tipo}/solicitar`, "POST", {}),
  cobrar: (os: string, tipo: string) => chamar<Envio>(`/api/pedidos/${os}/${tipo}/cobranca`, "POST", {}),
  registrar: (os: string, tipo: string, campos: Record<string, string>) =>
    chamar<{ ok: boolean }>(`/api/pedidos/${os}/${tipo}/registro`, "POST", { campos }),
  conferirEnvio: (id: number, decisao: "entregue" | "nao_entregue") =>
    chamar<Envio>(`/api/envios/${id}/conferir`, "POST", { decisao }),
};
