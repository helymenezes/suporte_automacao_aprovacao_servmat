# Arquitetura · servmat

Origem: esboço "Painel de Peças e Serviços" (canvas no claude.ai, 21/11/2026), com as OS reais lidas pela central em
20/11/2026 e a classificação sugerida à mão com as regras das rotinas da VPS02.

## Decisões

| ID | Decisão | Motivo |
|---|---|---|
| S-D1 | Serviço Python próprio (FastAPI + SQLite WAL), contêiner `servmat`, 256 MB. | Mesmo padrão do fechamento-os (D-01); não pesa no contêiner do OpenClaw. |
| S-D2 | O OpenClaw entra de dois jeitos: agenda `script` sem modelo para a coleta, e **agente com modelo** só para identificar itens do relato, pela skill `servmat-identificar`. | A leitura do relato precisa de IA; o resto não. |
| S-D3 | **O agente só sugere.** Fase máxima que ele produz: Nível 1. Aprovar, devolver e reprovar só por pessoa autenticada no painel. | Sem modelo no caminho do clique (como D-06). |
| S-D4 | Toda sugestão traz `evidencia`, conferida no servidor contra o relato e o campo "Utilizou peça" (sem acento, pontuação e caixa). | Barra item inventado pelo modelo. |
| S-D5 | Identificação idempotente por `(OS, hash do relato, rodada)`. Relato mudou → `409` e nova leitura. | Repetir a agenda não duplica itens. |
| S-D6 | "Devolver ao agente" (Nível 1) abre uma **rodada nova** da OS com o motivo, que o agente recebe em `devolucoes_do_nivel_1`. | O Hely corrige o agente sem sair do painel. |
| S-D7 | Relato corrigido no Auvo: sem decisão humana → apaga as sugestões e volta para o agente; com decisão → só alerta na trilha. | Não apaga trabalho de pessoa. |
| S-D8 | Concorrência otimista: toda decisão manda a `versao` do item; diferente → `409`. | Hely e Renato podem estar com a tela aberta ao mesmo tempo. |
| S-D9 | Técnico autor = avaliador do Nível 2 (ex.: OS 82447493, Renato Bonfim) → a decisão exige observação. | Aviso do esboço transformado em regra. |
| S-D10 | O link do Auvo (`taskUrl`, com chave) nunca vai no JSON: só em `GET /api/os/{os}/auvo`, autenticado, que redireciona. | A chave não vaza em log, cache nem print. |
| S-D11 | Painel só pela Tailscale; cookie `HttpOnly`, `SameSite=Strict`, `Secure`; escrita exige `X-Servmat: 1`; 5 senhas erradas → 10 min de espera. | Sem porta pública (D-11 do fechamento-os). |

## Fases do item

`relatorio` (agente / relatório sem informação) → `n1` (Hely) → `n2` (Renato) → `whats` (Pedido de compra: solicitação
ao orçamentista) ou `pedido` (Contrato HGG) → `fim`. `reprovado` guarda em que nível foi reprovado.

O serviço (OS) mostra a fase mais atrasada entre os itens vivos. As etapas do acompanhamento (Programação inicial,
Classificação PCM, Pedido, Autorização de Celso, Aprovação do cliente, Programação da execução, Finalização,
Cobrança) são calculadas dos itens em `regras.etapas_servico`, nunca guardadas.

## API

| Rota | Quem | O quê |
|---|---|---|
| `POST /api/login`, `POST /api/logout`, `GET /api/eu` | pessoa | sessão |
| `GET /api/painel` | pessoa | fases, serviços, itens, etapas, trilha |
| `POST /api/itens/{id}/decisao` `{acao, obs, versao}` | Nível 1 ou 2 | aprovar · devolver · reprovar |
| `POST /api/itens/{id}/classificacao` `{cls, versao}` | Nível 1 | corrigir a sugestão |
| `GET /api/itens/{id}/eventos` | pessoa | trilha do item |
| `GET /api/os/{os}/auvo` | pessoa | redireciona para a OS no Auvo |
| `GET /api/agente/pendentes`, `GET /api/agente/catalogo` | agente | o que identificar |
| `POST /api/agente/identificacoes` | agente | sugestões de uma OS (formato na SKILL.md) |
| `POST /run/coleta`, `GET /run/status` | agenda | coleta pela central · contagens |
| `GET /health` | todos | saúde |

## Modelo de dados

`os` (relato, hash, rodada, situação da identificação) · `itens` (sugestão + fase + versão) · `eventos` (só acréscimo)
· `usuarios` (scrypt) · `identificacoes` (idempotência do agente). Esquema em `servmat/servmat/banco.py`.

## Pendências

- **P-01** Nomes de campo do Auvo na central (relato, "Utilizou peça", equipamento): `config/coleta.json`.
- **P-02** Catálogo completo do contrato HGG (39 itens) em `config/catalogo.json`.
- **P-03** Telas "Acompanhamento do Pedido" e "Níveis de aprovação" do esboço: dependem do acesso ao sistema
  comercial e à planilha do cliente. Ficam para o próximo PR.
- **P-04** Gravação de áudio com transcrição na tela do celular: fora deste PR (a observação é por texto).
- **P-05** Envio da solicitação ao orçamentista (WhatsApp): hoje o item só muda de fase. No piloto, simulado.
