import { StrictMode, useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import { Celular } from "./telas/Celular";
import { Entrar } from "./telas/Entrar";
import { Fila } from "./telas/Fila";
import { NiveisTela } from "./telas/NiveisTela";
import { Pedido } from "./telas/Pedido";
import type { Usuario } from "./tipos";
import "./estilo.css";

function App() {
  const [eu, setEu] = useState<Usuario | null | undefined>(undefined);
  useEffect(() => {
    api.eu().then(setEu).catch(() => setEu(null));
  }, []);
  const sair = useCallback(() => {
    api.sair().catch(() => undefined).finally(() => setEu(null));
  }, []);

  if (eu === undefined) return null;
  if (eu === null) return <Entrar aoEntrar={setEu} />;
  const caminho = location.pathname.replace(/\/$/, "") || "/";
  if (caminho === "/pedido") return <Pedido eu={eu} aoSair={sair} />;
  if (caminho === "/niveis") return <NiveisTela eu={eu} aoSair={sair} />;
  // /celular = tela do aprovador no telefone; no celular, a raiz também abre ela.
  if (caminho === "/celular" || (caminho === "/" && window.innerWidth < 640)) return <Celular eu={eu} aoSair={sair} />;
  return <Fila eu={eu} aoSair={sair} />;
}

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
