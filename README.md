# suporte_automacao_aprovacao_servmat

Painel de aprovação de **peças, materiais e serviços das OS** (Grupo Suporte · PCM), ligado ao agente de IA do
OpenClaw na VPS02.

```
Auvo ──(central, só leitura)──▶ coleta ──▶ OS com relato (pendente)
                                              │
                    OpenClaw · agente + skill servmat-identificar
                                              │  sugere itens com evidência
                                              ▼
              níveis da rota (padrão: Hely ──▶ Renato; configurável na tela Níveis)
                                              │  painel web e celular (áudio com transcrição)
                                              ▼
        Acompanhamento do Pedido: solicitação ao orçamentista (WhatsApp) ──▶ Pedido ──▶ cliente / Celso
                                  ──▶ execução ──▶ cobrança ao orçamentista (WhatsApp)
```

- **Uma linha por serviço (OS)**, com Equipamento / Área para busca. Os materiais, peças e serviços ficam dentro do
  acompanhamento, que só aparece quando pedido (seta ou número da OS).
- **O agente só sugere.** Toda sugestão traz um trecho do relato como evidência, e o servidor recusa trecho que não
  está no texto. A aprovação é sempre de uma pessoa autenticada, sem IA no clique.
- **Níveis de aprovação configuráveis** (ordem, quem aprova, rota de Pedido e/ou de Contrato, ligado/desligado). Cada
  gravação cria uma versão nova da rota; os itens já na fila seguem a versão com que entraram.
- **Acompanhamento do Pedido** do fim dos níveis até a cobrança, com entrada para o sistema comercial e a planilha do
  cliente e registro manual enquanto essas leituras não existem.
- **Mensagens ao orçamentista pelo WhatsApp** (WAHA): solicitação e cobrança, com recibo; simuladas até ligar
  `SERVMAT_ENVIO_REAL=1`. Envio incerto nunca se repete sozinho.
- **Áudio no celular** com transcrição opcional (qualquer serviço compatível com a API de transcrição da OpenAI), sempre
  conferida antes de enviar.
- **Trilha de auditoria** de cada item (quem decidiu, de que fase para qual, observação, áudio, hora).

## Pastas

| Pasta | O quê |
|---|---|
| `servmat/` | Serviço Python 3.12: FastAPI + SQLite WAL. Regras puras em `regras.py`, entrada do agente em `agente.py`, coleta em `coleta.py`. |
| `web/` | Telas React + Vite: fila de aprovação, Acompanhamento do Pedido, Níveis de aprovação e avaliação no celular. |
| `openclaw/` | Skills `servmat-identificar` (sugere os itens de cada OS) e `servmat-catalogo` (monta o catálogo de uso de HGG e CAMIL pelo histórico), e as agendas para o OpenClaw da VPS02. |
| `deploy/servmat/` | Dockerfile, docker-compose e `.env.example`, no padrão do fechamento-os. |
| `docs/ARQUITETURA.md` | Decisões, API, modelo de dados e pendências. |

## Rodar no PC (teste)

```bash
# serviço
cd servmat
pip install -r requirements.txt
export SERVMAT_SEGREDO=$(python -c 'import secrets;print(secrets.token_urlsafe(48))') SERVMAT_COOKIE_SEGURO=0
# a senha (10+ caracteres) é pedida no terminal, ou vem de SERVMAT_SENHA
python -m servmat usuario --usuario hely --nome "Hely R Menezes" --admin
python -m servmat usuario --usuario renato --nome "Renato Bonfim"   # com os dois, nasce a rota padrão
python -m servmat seed-esboco                       # as 11 OS do esboço, nada aprovado (exige hely e renato)
python -m pytest -q                                 # 57 testes

# telas (outro terminal)
cd web && npm ci && npm run build                   # o serviço passa a servir web/dist
cd ../servmat && python -m servmat servico          # http://127.0.0.1:8792
# telas: /  ·  /pedido  ·  /niveis  ·  /celular
```

Para testar a skill do agente sem a coleta: `python -m servmat ensaio --forcar` põe as 11 OS do esboço como pendentes,
sem itens (ver `openclaw/AGENDAS.md`).

Para desenvolver as telas com recarga automática: `cd web && npm run dev` (o Vite repassa `/api` para a porta 8792).

## Implantar na VPS02

Checklist em [`deploy/servmat/README.md`](deploy/servmat/README.md).
