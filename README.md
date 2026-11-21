# suporte_automacao_aprovacao_servmat

Painel de aprovação de **peças, materiais e serviços das OS** (Grupo Suporte · PCM), ligado ao agente de IA do
OpenClaw na VPS02.

```
Auvo ──(central, só leitura)──▶ coleta ──▶ OS com relato (pendente)
                                              │
                    OpenClaw · agente + skill servmat-identificar
                                              │  sugere itens com evidência
                                              ▼
                     Nível 1 (Hely) ──▶ Nível 2 (Renato) ──▶ Solicitação / Pedido
                         painel web            celular
```

- **Uma linha por serviço (OS)**, com Equipamento / Área para busca. Os materiais, peças e serviços ficam dentro do
  acompanhamento, que só aparece quando pedido (seta ou número da OS).
- **O agente só sugere.** Toda sugestão traz um trecho do relato como evidência, e o servidor recusa trecho que não
  está no texto. A aprovação é sempre de uma pessoa autenticada, sem IA no clique.
- **Trilha de auditoria** de cada item (quem decidiu, de que fase para qual, observação, hora).

## Pastas

| Pasta | O quê |
|---|---|
| `servmat/` | Serviço Python 3.12: FastAPI + SQLite WAL. Regras puras em `regras.py`, entrada do agente em `agente.py`, coleta em `coleta.py`. |
| `web/` | Telas React + Vite: fila de aprovação (computador) e avaliação no celular. |
| `openclaw/` | Skill `servmat-identificar` e as agendas para o OpenClaw da VPS02. |
| `deploy/servmat/` | Dockerfile, docker-compose e `.env.example`, no padrão do fechamento-os. |
| `docs/ARQUITETURA.md` | Decisões, API, modelo de dados e pendências. |

## Rodar no PC (teste)

```bash
# serviço
cd servmat
pip install -r requirements.txt
export SERVMAT_SEGREDO=$(python -c 'import secrets;print(secrets.token_urlsafe(48))') SERVMAT_COOKIE_SEGURO=0
python -m servmat seed-esboco                       # as 11 OS do esboço, nada aprovado
python -m servmat usuario --usuario hely --nome "Hely R Menezes" --nivel 1
python -m servmat usuario --usuario renato --nome "Renato Bonfim" --nivel 2
python -m pytest -q                                 # 29 testes

# telas (outro terminal)
cd web && npm ci && npm run build                   # o serviço passa a servir web/dist
cd ../servmat && python -m servmat servico          # http://127.0.0.1:8792  (celular: /celular)
```

Para desenvolver as telas com recarga automática: `cd web && npm run dev` (o Vite repassa `/api` para a porta 8792).

## Implantar na VPS02

Checklist em [`deploy/servmat/README.md`](deploy/servmat/README.md).
