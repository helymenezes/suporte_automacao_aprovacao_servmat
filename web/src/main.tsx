import { StrictMode, useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import { Celular } from "./telas/Celular";
import { Entrar } from "./telas/Entrar";
import { Fila } from "./telas/Fila";
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
  // /celular = tela do avaliador no telefone; no celular, a raiz também abre ela.
  const celular = location.pathname.startsWith("/celular") || (location.pathname === "/" && window.innerWidth < 640);
  return celular ? <Celular eu={eu} aoSair={sair} /> : <Fila eu={eu} aoSair={sair} />;
}

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
