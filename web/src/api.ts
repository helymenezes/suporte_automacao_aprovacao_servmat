import type { Painel, Usuario } from "./tipos";

export class ErroApi extends Error {
  constructor(public status: number, mensagem: string) {
    super(mensagem);
  }
}

async function chamar<T>(caminho: string, metodo = "GET", corpo?: unknown): Promise<T> {
  const r = await fetch(caminho, {
    method: metodo,
    credentials: "same-origin",
    headers: corpo !== undefined ? { "Content-Type": "application/json", "X-Servmat": "1" } : { "X-Servmat": "1" },
    body: corpo !== undefined ? JSON.stringify(corpo) : undefined,
  });
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

export const api = {
  eu: () => chamar<Usuario>("/api/eu"),
  entrar: (usuario: string, senha: string) => chamar<Usuario>("/api/login", "POST", { usuario, senha }),
  sair: () => chamar<{ ok: boolean }>("/api/logout", "POST", {}),
  painel: () => chamar<Painel>("/api/painel"),
  decidir: (id: number, acao: "aprovar" | "devolver" | "reprovar", obs: string, versao: number) =>
    chamar<{ fase: string; fase_nome: string }>(`/api/itens/${id}/decisao`, "POST", { acao, obs, versao }),
  reclassificar: (id: number, cls: string, versao: number) =>
    chamar<{ cls: string }>(`/api/itens/${id}/classificacao`, "POST", { cls, versao }),
  linkAuvo: (os: string) => `/api/os/${encodeURIComponent(os)}/auvo`,
};
