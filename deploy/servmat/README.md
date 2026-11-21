# Implantação na VPS02

Entregue **sem nada ligado**: o contêiner sobe, mas as agendas do OpenClaw só entram depois dos itens S-01 a S-04.

## Antes (conferências)

- **S-01 · Central:** confirmar que a central expõe na listagem de tarefas os campos do relato do técnico, das
  respostas do questionário ("Utilizou peça") e o nome do equipamento. Ajustar `servmat/config/coleta.json`
  (`campo_relato`, `campo_equipamento`, `pergunta_utilizou`). Sem o nome do equipamento na listagem, a coluna mostra
  "Equipamento não informado" até a central ganhar uma rota só de leitura para equipamentos.
- **S-02 · Rede:** decidir como o OpenClaw alcança a API: `SERVMAT_HOST` = IP do `docker0` ou rede Docker
  compartilhada (ver `openclaw/AGENDAS.md`). A porta nunca abre para a internet.
- **S-03 · Catálogo:** trocar `servmat/config/catalogo.json` pelo `itens.json` completo do contrato HGG (39 itens) e
  tirar o `_incompleto`.
- **S-04 · Memória:** a VPS02 usa swap todo dia. O contêiner fica limitado a 256 MB e 0,5 CPU.

## Subir

```bash
sudo mkdir -p /opt/servmat/dados && sudo chown 1000:1000 /opt/servmat/dados
cp deploy/servmat/.env.example /opt/servmat/.env && chmod 600 /opt/servmat/.env   # preencher os segredos
export SERVMAT_HOST_DIR=/opt/servmat
docker compose -f deploy/servmat/docker-compose.yml build
docker compose -f deploy/servmat/docker-compose.yml up -d
docker compose -f deploy/servmat/docker-compose.yml exec servmat python -m servmat usuario --usuario hely --nome "Hely R Menezes" --nivel 1
docker compose -f deploy/servmat/docker-compose.yml exec servmat python -m servmat usuario --usuario renato --nome "Renato Bonfim" --nivel 2
tailscale serve --bg --https=8443 http://127.0.0.1:8792
```

Opcional, para conferir as telas antes da coleta real:
`... exec servmat python -m servmat seed-esboco` (depois, `seed-esboco --forcar` apaga e recarrega).

## Ligar o OpenClaw

1. Cofre do OpenClaw: `SERVMAT_URL`, `SERVMAT_AGENTE_TOKEN`, `SERVMAT_RUN_TOKEN`.
2. Copiar `openclaw/skills/servmat-identificar/` para as skills do workspace.
3. Testar à mão: `servmat.sh pendentes` dentro do contêiner do OpenClaw.
4. Criar as agendas `servmat-coleta` e `servmat-identificar` (`openclaw/AGENDAS.md`), primeiro com uma execução
   manual de cada e o Hely conferindo as sugestões no painel.

## Voltar atrás

`docker compose -f deploy/servmat/docker-compose.yml down` e apagar as duas agendas. O banco fica em
`/opt/servmat/dados/servmat.sqlite` (fora do backup MEGA até decidir a cota, como no fechamento-os).
