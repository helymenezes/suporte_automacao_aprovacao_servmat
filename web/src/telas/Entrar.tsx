import { useState } from "react";
import { api } from "../api";
import type { Usuario } from "../tipos";

export function Entrar({ aoEntrar }: { aoEntrar: (u: Usuario) => void }) {
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setOcupado(true);
    setErro("");
    try {
      aoEntrar(await api.entrar(usuario, senha));
    } catch (er) {
      setErro(er instanceof Error ? er.message : "Falha ao entrar.");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="entrar">
      <form onSubmit={enviar}>
        <div>
          <span className="rotulo">Grupo Suporte · PCM</span>
          <h1 style={{ margin: "2px 0 0", fontSize: 20, lineHeight: "26px", fontWeight: 800 }}>Peças, materiais e serviços</h1>
        </div>
        <div className="campo">
          <label htmlFor="u">Usuário</label>
          <input id="u" autoComplete="username" value={usuario} onChange={(e) => setUsuario(e.target.value)} required />
        </div>
        <div className="campo">
          <label htmlFor="s">Senha</label>
          <input id="s" type="password" autoComplete="current-password" value={senha} onChange={(e) => setSenha(e.target.value)} required />
        </div>
        {erro && <span className="aviso" role="alert">▲ {erro}</span>}
        <button type="submit" className="btn cheio" disabled={ocupado}>Entrar</button>
      </form>
    </div>
  );
}
