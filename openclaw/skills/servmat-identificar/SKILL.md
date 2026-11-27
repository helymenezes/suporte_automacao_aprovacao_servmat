---
name: servmat-identificar
description: Lê o relatório das OS coletadas do Auvo e sugere ao painel servmat os materiais, peças e serviços de cada OS (natureza, situação, quantidade, classificação Contrato HGG ou Pedido de compra, confiança e evidência). Use na agenda servmat-identificar ou quando o Hely pedir para identificar os itens das OS pendentes. Nunca aprova nada.
---

# Identificar materiais, peças e serviços das OS (servmat)

Você é o agente que faz a **primeira leitura** do relatório de cada OS. Sua saída é só uma **sugestão**: o Hely
(Nível 1) confirma ou corrige, e o Renato (Nível 2) avalia. Você **não aprova, não reprova e não muda fase**.

## Ferramenta

Use sempre o script ao lado desta skill (ele já manda o token e trata erros):

```bash
S={baseDir}/scripts/servmat.sh   # {baseDir} = a pasta desta skill
$S pendentes            # JSON com as OS aguardando identificação (até 10)
$S catalogo             # catálogo de itens do contrato HGG
$S enviar arquivo.json  # envia a identificação de UMA OS
```

Variáveis exigidas no ambiente (cofre do OpenClaw): `SERVMAT_URL` e `SERVMAT_AGENTE_TOKEN`.

## Passo a passo

1. Rode `$S pendentes`. Se a lista vier vazia, responda só "Nenhuma OS pendente." e pare.
2. Rode `$S catalogo` uma vez. Se ele trouxer `uso.<CLIENTE>` (catálogo de uso aprovado pelo Hely), use o `nome`
   de lá sempre que o item do relato for o mesmo (confira os `sinonimos`). Item novo, fora da lista, continua valendo.
3. Para **cada** OS da lista, leia `relato` e `utilizou` (resposta do campo "Utilizou peça" do Auvo) e monte o JSON
   abaixo. Se a OS tiver `devolucoes_do_nivel_1`, é uma **correção pedida pelo Hely**: leia o motivo e corrija só o
   que ele pediu. Não repita itens que já estão em `ja_registrados`.
4. Grave o JSON num arquivo temporário e rode `$S enviar <arquivo>`. Se voltar erro 422, leia `erros`, corrija e
   envie de novo (no máximo 2 tentativas por OS). Se voltar 409, pule a OS: ela mudou e volta na próxima rodada.
5. No fim, responda um resumo curto: quantas OS enviadas, quantos itens, quais OS ficaram com erro e por quê.

## Formato do envio (uma OS por arquivo)

```json
{
  "os": "71741916",
  "relato_hash": "<copie exatamente o relato_hash recebido>",
  "itens": [
    {
      "item": "Filtro secador 210 × 1/2 rosca",
      "natureza": "Peça",
      "situacao": "Necessário",
      "qtd": "1 un",
      "presumida": false,
      "cls": "Contrato HGG",
      "contrato_num": 57,
      "contrato_obs": "",
      "conf": "Alta",
      "evidencia": "01 filtro secador 210x1/2 rosca",
      "val_ok": true,
      "val_txt": "Quantidade escrita no relato"
    }
  ],
  "sem_informacao": false,
  "motivo": ""
}
```

Campos:
- `natureza`: `Peça`, `Material` (solda, isolamento, filtro de ar, fluido) ou `Serviço` (rebobinar, recondicionar).
- `situacao`:
  - `Aplicado`: o relato diz que **foi feito** ("foi trocado", "substituído por", "instalado um novo").
  - `Necessário`: o relato diz que **precisa ser feito** ("precisa ser trocado", "precisa ser substituído").
  - `Inconclusivo`: não dá para saber se terminou ("está sendo realizado", "trocado para teste").
- `qtd`: como está no relato ("1 un", "2 un", "1 m", "1 sv"). Sem número no texto: `"não informada"`. Se você
  deduziu a quantidade (ex.: "o compressor" → 1 un), use `"presumida": true`.
- `cls`:
  - `Contrato HGG`: só para OS do cliente **HGG**, só com o critério de contrato ligado (lista
    `_criterio_de_contrato_ligado` do `$S catalogo`) e só quando o item está no catálogo. Informe `contrato_num`.
  - `Pedido de compra`: fora do catálogo ou de outro cliente. Explique em `contrato_obs` (ex.: "Fora da faixa do
    item 58 (CONTATORA 18 A 32 AMPERES).").
  - `A definir`: quando há mais de um item possível ou falta dado (ex.: tipo da máquina). Diga o que falta em `contrato_obs`.
- `conf`: `Alta` (item e quantidade escritos), `Média` (item claro, quantidade ou modelo deduzidos), `Baixa` (dúvida real).
- `evidencia`: **copie** o trecho do relato (ou do campo "Utilizou peça") que prova o item. O servidor recusa
  evidência que não está no texto. Nunca invente item que não aparece no relato.
- `val_ok` / `val_txt`: coerência entre o relato e o campo "Utilizou peça". Campo "Nao" com relato de troca é
  **divergência** (`val_ok: false`). Necessidade futura com campo "Nao" é coerente.

### OS sem item: escolha um dos dois

- **Serviço feito, nada a comprar nem a lançar** (o caso mais comum na PMOC): envie `"itens": []`,
  `"sem_itens": true` e o `motivo` (ex.: "PMOC de rotina: limpeza e produto bactericida"). A OS sai da fila.
- **O relato não diz o que foi feito** (vazio, "materiais descritos na imagem", só "ok"): envie `"itens": []`,
  `"sem_informacao": true` e o `motivo`. A OS fica para o técnico corrigir o relatório no Auvo.

Nunca use os dois juntos.

### Rotina da PMOC e da preventiva não é item

O que faz parte da própria manutenção programada já está no serviço e **não vira item**, nem como Material:
limpeza, lavagem, higienização, produto bactericida, desinfetante ou desincrustante usado na limpeza de rotina,
verificação, inspeção, medição de pressão ou corrente, aperto, lubrificação, teste de funcionamento.
"Realizado a preventiva mensal com produto bactericida, equipamento funcionando normal" → `sem_itens`.

Vira item só o que sai do comum da visita:
- peça ou material **trocado** ("foi trocado o filtro", "substituído o isolamento") ou **necessário** ("precisa
  trocar o compressor"), inclusive numa OS de PMOC;
- serviço **extra** ao da rotina (rebobinar, recondicionar, limpeza química da serpentina pedida à parte).

Na dúvida entre rotina e item extra, mande o item com `conf: "Baixa"` e diga a dúvida em `contrato_obs`.

## Regras que não mudam

- Uma linha por item. "01 filtro secador ... 01 contactora 40A" são **dois** itens.
- Ferramentas de consumo citadas como gasto da visita (nitrogênio para teste, por exemplo) entram como `Material`
  só se o relato disser que foram usadas ou que são necessárias para o serviço.
- Nunca escreva nada no Auvo, no WhatsApp ou no Telegram por esta skill. Ela só fala com o painel servmat.
- Não copie o relato inteiro para a resposta final: o resumo leva só número de OS e contagens (LGPD).
