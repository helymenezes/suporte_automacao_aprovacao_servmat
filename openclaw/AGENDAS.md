# Agendas do servmat no OpenClaw (VPS02)

Entregues **desligadas**. Crie cada uma no OpenClaw só depois do checklist de implantação (`deploy/servmat/README.md`).
Fuso: America/Sao_Paulo. Aviso de falha no Telegram, como nas rotinas HGG/Camil.

| Agenda | Tipo | Quando | O que faz |
|---|---|---|---|
| `servmat-coleta` | `script`, **sem modelo** | 07:05 às 19:05, de hora em hora, seg–sáb | Lê as OS finalizadas pela central e grava o relato. Não usa IA. |
| `servmat-identificar` | **agente com modelo** + skill `servmat-identificar` | 07:20 às 19:20, de hora em hora, seg–sáb | Lê as OS pendentes e envia as sugestões de materiais, peças e serviços. |

A aprovação (Nível 1 e Nível 2) **não passa pelo OpenClaw**: é só no painel, por pessoa autenticada. Assim não há
modelo no caminho do clique (mesma decisão D-06 do fechamento-os).

## `servmat-coleta` (script)

```bash
curl -sS --fail-with-body --max-time 300 -X POST \
  -H "Authorization: Bearer ${SERVMAT_RUN_TOKEN}" \
  "${SERVMAT_URL}/run/coleta"
```

Saída ≠ 0 (HTTP 502 = listagem incompleta na central; 503 = central não configurada) dispara o aviso de falha.

## `servmat-identificar` (agente)

Instale a pasta `openclaw/skills/servmat-identificar` nas skills do workspace do OpenClaw e dê ao agente as variáveis
`SERVMAT_URL` e `SERVMAT_AGENTE_TOKEN` (cofre). Mensagem da agenda:

> Use a skill servmat-identificar. Identifique os materiais, peças e serviços de todas as OS pendentes no painel
> servmat e me mande só o resumo final (nº de OS, itens enviados e erros).

Sugestão de modelo: o mesmo das rotinas atuais com fallback. A skill limita o trabalho a 10 OS por execução.

## `servmat-catalogo` (agente, sob demanda)

Não é agenda: roda à mão quando o Hely quiser montar ou refazer o catálogo de uso de um cliente.

1. No servidor: `docker compose ... exec servmat python -m servmat historico --desde 2026-02-01 --clientes HGG,CAMIL`.
2. No OpenClaw, com a skill `openclaw/skills/servmat-catalogo` instalada:
   > Use a skill servmat-catalogo. Monte o catálogo de uso da CAMIL desde 2026-02-01 e me mande o resumo.
   (repita para o HGG).
3. Conferir: `python -m servmat catalogo --cliente CAMIL --saida /tmp/camil.json` e, se estiver bom,
   `python -m servmat catalogo --aprovar <id> --por hely` (ou pelo `POST /api/catalogo-proposto/{id}/aprovar`).

## Ensaio da identificação (antes de ligar a coleta)

`python -m servmat ensaio --forcar` (as 11 OS do esboço, sem itens) ou `python -m servmat ensaio --do-historico 10
--cliente CAMIL`. Depois, uma execução manual da `servmat-identificar` e o Hely confere as sugestões no painel.
O `--forcar` apaga as OS e itens do banco: só num banco de teste.

## Endereço do serviço visto de dentro do OpenClaw

O serviço escuta em `SERVMAT_HOST:SERVMAT_PORTA`. Duas opções (decidir na implantação, item S-02):
- `network_mode: host` e `SERVMAT_HOST` = IP do `docker0` (ex.: `172.17.0.1`) → `SERVMAT_URL=http://172.17.0.1:8792`;
- ou ligar o contêiner `servmat` à rede Docker do OpenClaw e usar `SERVMAT_URL=http://servmat:8792`.

Em nenhum caso a porta fica aberta para a internet. O painel das pessoas sai pela Tailscale (`tailscale serve`).
