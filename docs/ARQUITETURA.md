# Arquitetura · servmat

Origem: esboço "Painel de Peças e Serviços" (canvas no claude.ai, 21/11/2026), com as OS reais lidas pela central em
20/11/2026 e a classificação sugerida à mão com as regras das rotinas da VPS02. Telas: Fila de aprovação,
Acompanhamento do Pedido, Níveis de aprovação e Avaliação no celular.

## Decisões

| ID | Decisão | Motivo |
|---|---|---|
| S-D1 | Serviço Python próprio (FastAPI + SQLite WAL), contêiner `servmat`, 256 MB. | Mesmo padrão do fechamento-os (D-01); não pesa no contêiner do OpenClaw. |
| S-D2 | O OpenClaw entra de dois jeitos: agenda `script` sem modelo para a coleta, e **agente com modelo** só para identificar itens do relato, pela skill `servmat-identificar`. | A leitura do relato precisa de IA; o resto não. |
| S-D3 | **O agente só sugere.** O máximo que ele faz é pôr o item no 1º nível. Aprovar, devolver e reprovar só por pessoa autenticada no painel. | Sem modelo no caminho do clique (como D-06). |
| S-D4 | Toda sugestão traz `evidencia`, conferida no servidor contra o relato e o campo "Utilizou peça" (sem acento, pontuação e caixa). | Barra item inventado pelo modelo. |
| S-D5 | Identificação idempotente por `(OS, hash do relato, rodada)`. Relato mudou → `409` e nova leitura. | Repetir a agenda não duplica itens. |
| S-D6 | "Devolver ao agente" (1º nível) abre uma **rodada nova** da OS com o motivo, que o agente recebe em `devolucoes_do_nivel_1`. Nos outros níveis, devolver volta um nível. | O Hely corrige o agente sem sair do painel. |
| S-D7 | Relato corrigido no Auvo: sem decisão humana → apaga as sugestões e volta para o agente; com decisão → só alerta na trilha. | Não apaga trabalho de pessoa. |
| S-D8 | Concorrência otimista: toda decisão manda a `versao` do item; diferente → `409`. | Duas pessoas podem estar com a tela aberta ao mesmo tempo. |
| S-D9 | Técnico autor = aprovador do nível (ex.: OS 82447493, Renato Bonfim) → a decisão exige observação. | Aviso do esboço transformado em regra. |
| S-D10 | O link do Auvo (`taskUrl`, com chave) nunca vai no JSON: só em `GET /api/os/{os}/auvo`, autenticado, que redireciona. | A chave não vaza em log, cache nem print. |
| S-D11 | Painel só pela Tailscale; cookie `HttpOnly`, `SameSite=Strict`, `Secure`; escrita exige `X-Servmat: 1`; 5 senhas erradas → 10 min de espera. | Sem porta pública (D-11 do fechamento-os). |
| S-D12 | **Rota versionada.** A tela Níveis grava uma versão nova (imutável) a cada mudança; o item guarda a versão com que entrou. A rota de cada item depende da classificação (Pedido ou Contrato). Só o administrador grava. | Mudar a rota no meio do mês não muda a regra de quem já está na fila. |
| S-D13 | Quem decide sai da rota (usuário do nível), não de um papel fixo. Só o 1º nível corrige a classificação; reclassificar para uma rota mais curta pula para a fase seguinte. | Acrescentar "Gerência" ou "Celso" como nível não exige código. |
| S-D14 | **Acompanhamento do Pedido** por OS e rota (compra/contrato). Pedido, vínculo, NF, Celso e execução vêm do sistema comercial; aceite, da planilha. Até existirem os leitores, o administrador registra à mão (fica na trilha como `manual:<usuário>`). | O painel lê; não inventa estado comercial. |
| S-D15 | **WhatsApp ao orçamentista** pelo WAHA (`sendText`), com fila `envios`, chave de idempotência e recibo. Sem resposta do WAHA = `INCERTO`, que nunca reenvia sozinho; o administrador marca "Chegou" ou "Não chegou". Sem `SERVMAT_ENVIO_REAL=1`, `SIMULADO`. | Mesmo cuidado da fila do fechamento-os: nunca mandar duas vezes. |
| S-D16 | Cobrança enviada (compra) ou Celso autorizado + execução concluída (contrato) → itens vão para Concluído. | O fluxo termina sozinho quando a última etapa é registrada. |
| S-D17 | **Áudio** gravado no navegador, guardado em `dados/audios/` e ligado à decisão. Transcrição opcional por serviço compatível com `POST /v1/audio/transcriptions`; o texto sempre passa pela pessoa antes de entrar na observação. | Avaliação rápida no campo, sem depender de um fornecedor. |

## Fases do item

`relatorio` (agente / relatório sem informação) → `nivel` com posição 0, 1, 2… na rota do item → `whats` (Pedido de
compra: solicitação ao orçamentista) ou `pedido` (Contrato HGG) → `fim`. `reprovado` guarda a posição em que foi
reprovado.

O serviço (OS) mostra a fase mais atrasada entre os itens vivos. As etapas do acompanhamento (Programação inicial,
Classificação PCM, Pedido, Autorização de Celso, Aprovação do cliente, Programação da execução, Finalização,
Cobrança) são calculadas dos itens e da situação do Pedido em `regras.etapas_servico`, nunca guardadas.

## API

| Rota | Quem | O quê |
|---|---|---|
| `POST /api/login`, `POST /api/logout`, `GET /api/eu` | pessoa | sessão (com os níveis da pessoa na rota atual) |
| `GET /api/painel` | pessoa | fases, serviços, itens (`minha_vez`), etapas, trilha |
| `POST /api/itens/{id}/decisao` `{acao, obs, versao, audio_id?}` | aprovador do nível | aprovar · devolver · reprovar |
| `POST /api/itens/{id}/classificacao` `{cls, versao}` | 1º nível | corrigir a sugestão |
| `POST /api/itens/{id}/audio` (corpo = áudio) · `GET /api/audios/{id}` | pessoa | gravar e ouvir |
| `GET /api/itens/{id}/eventos` | pessoa | trilha do item |
| `GET /api/os/{os}/auvo` | pessoa | redireciona para a OS no Auvo |
| `GET /api/niveis` · `PUT /api/niveis` | pessoa · admin | rota e critério de contrato por cliente |
| `GET /api/pedidos` | pessoa | Acompanhamento do Pedido |
| `POST /api/pedidos/{os}/{tipo}/solicitar` · `/cobranca` · `/registro` | admin | WhatsApp ao orçamentista · registro manual |
| `POST /api/envios/{id}/conferir` `{decisao}` | admin | resolver envio INCERTO |
| `POST /api/integracao/comercial` · `/planilha` `{registros}` | leitor | Pedido/NF/Celso/execução · aceite |
| `GET /api/agente/pendentes`, `GET /api/agente/catalogo` | agente | o que identificar |
| `POST /api/agente/identificacoes` | agente | sugestões de uma OS (formato na SKILL.md) |
| `POST /run/coleta`, `GET /run/status` | agenda | coleta pela central · contagens |
| `GET /health` | todos | saúde |

## Modelo de dados

`os` (relato, hash, rodada, situação da identificação) · `itens` (sugestão, fase, posição no nível, versão da rota,
versão do item) · `eventos` (só acréscimo) · `usuarios` (scrypt, admin) · `niveis` (rota em edição) · `rotas` (versões
imutáveis) · `contratos_cliente` · `pedidos` (OS × rota) · `envios` (fila do WhatsApp) · `audios` · `integracoes`
(última leitura) · `identificacoes` (idempotência do agente). Esquema em `servmat/servmat/banco.py`.

## Pendências

- **P-01** Nomes de campo do Auvo na central (relato, "Utilizou peça", equipamento): `config/coleta.json`.
- **P-02** Catálogo completo do contrato HGG (39 itens) em `config/catalogo.json`.
- **P-03** Leitores do sistema comercial e da planilha do cliente: a rota de entrada existe; falta quem leia.
- **P-04** Instância WAHA e número do orçamentista; teste de envio antes de `SERVMAT_ENVIO_REAL=1`.
- **P-05** Serviço de transcrição e retenção dos áudios (dado pessoal: voz).
- **P-06** "Nova OS de execução aprovada por Hely no Telegram" e "envio ao faturamento" aparecem na rota como etapas
  fixas; a execução e o faturamento entram por registro ou integração, sem automação própria neste serviço.
