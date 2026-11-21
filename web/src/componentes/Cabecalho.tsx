import type { ReactNode } from "react";
import type { Usuario } from "../tipos";

const ABAS = [
  { href: "/", nome: "Fila de aprovação" },
  { href: "/pedido", nome: "Acompanhamento do Pedido" },
  { href: "/niveis", nome: "Níveis de aprovação" },
  { href: "/celular", nome: "Tela do celular" },
];

export function Cabecalho({ eu, aoSair, pilulas }: { eu: Usuario; aoSair: () => void; pilulas?: ReactNode }) {
  const atual = location.pathname.replace(/\/$/, "") || "/";
  return (
    <>
      <header className="topo">
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span className="sobre">Grupo Suporte · PCM</span>
          <h1>Peças, materiais e serviços das OS</h1>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          {pilulas}
          <span className="pilula">
            {eu.nome}{eu.niveis.length ? ` · Nível ${eu.niveis.join(" e ")}` : ""}{eu.admin ? " · Admin" : ""}
          </span>
          <button type="button" className="pilula" onClick={aoSair}>Sair</button>
        </div>
      </header>
      <nav aria-label="Seções do painel" className="abas">
        {ABAS.map((a) => (
          <a key={a.href} href={a.href} aria-current={atual === a.href ? "page" : undefined}>{a.nome}</a>
        ))}
      </nav>
    </>
  );
}
