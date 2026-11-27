---
name: servmat-catalogo
description: Lê o histórico de OS de um cliente (HGG ou CAMIL, desde fevereiro de 2026) no painel servmat e propõe o catálogo de uso daquele cliente, com um item por peça, material ou serviço, nome padronizado, sinônimos, ocorrências e evidência. Use quando o Hely pedir para montar ou refazer o catálogo de um cliente. A proposta é só rascunho; quem aprova é o Hely.
---

# Montar o catálogo de uso de um cliente (servmat)

Você lê o que os técnicos escreveram nas OS de um cliente e monta a **lista padronizada** dos materiais, peças e
serviços que aparecem. Essa lista ajuda o agente de identificação a usar sempre o mesmo nome para o mesmo item.
Você **não aprova** a lista e **não decide contrato**: a proposta vai como rascunho, e o Hely aprova no servidor.

## Ferramenta

```bash
S={baseDir}/scripts/servmat.sh            # {baseDir} = a pasta desta skill
$S catalogo                               # catálogo do contrato HGG (números dos itens) e o catálogo de uso aprovado
$S historico CAMIL                        # 1ª página (40 OS) do histórico do cliente
$S historico CAMIL <proximo> [2026-02-01] # próxima página: passe o "proximo" da página anterior
$S propor arquivo.json                    # envia a proposta do cliente
```

Variáveis no cofre do OpenClaw: `SERVMAT_URL` e `SERVMAT_AGENTE_TOKEN`.

## Passo a passo

1. Rode `$S catalogo` uma vez (para o HGG, você vai precisar dos números do contrato).
2. Leia **todas** as páginas de `$S historico <CLIENTE> "" 2026-02-01` até `proximo` vir `null`. Em cada OS, leia
   `relato` e `utilizou` (resposta do campo "Utilizou peça").
3. Anote cada material, peça ou serviço citado, com a OS e o trecho exato do texto onde ele aparece.
4. Junte o que é a mesma coisa escrita de jeitos diferentes ("contactora 40A", "contatora 40 A", "contator 40A") num
   item só: o nome padronizado em `nome` e as outras grafias em `sinonimos`.
5. Monte o JSON abaixo, grave num arquivo e rode `$S propor <arquivo>`. Se voltar 422, leia `erros`, corrija e
   envie de novo (no máximo 3 tentativas).
6. Responda só o resumo: cliente, nº de OS lidas, nº de itens propostos e o `id` da proposta.

## Formato (um cliente por envio)

```json
{
  "cliente": "CAMIL",
  "desde": "2026-02-01",
  "itens": [
    {
      "nome": "Contatora 40 A 220 V",
      "natureza": "Peça",
      "sinonimos": ["contactora 40A", "contator 40 A"],
      "ocorrencias": 7,
      "os_exemplo": ["81234567", "81234999"],
      "evidencia": "01 contactora 220v 40A",
      "contrato_num": null,
      "obs": ""
    }
  ]
}
```

- `nome`: curto e padronizado: o que é, depois a medida (potência, bitola, corrente, BTU, modelo). Sem marca, a menos
  que o relato só cite a marca.
- `natureza`: `Peça`, `Material` (solda, isolamento, gás, fluido, filtro de ar) ou `Serviço` (rebobinar,
  recondicionar, usinagem).
- `ocorrencias`: em quantas OS o item aparece.
- `os_exemplo`: de 1 a 5 OS onde o item aparece. `evidencia`: **copie** o trecho de uma delas. O servidor recusa
  evidência que não está no texto das OS de exemplo.
- `contrato_num`: só para o **HGG**, quando o item é claramente um item do catálogo do contrato (`$S catalogo`).
  Na dúvida, deixe `null` e explique em `obs`. Para a CAMIL, sempre `null`.

## Regras que não mudam

- Só entra item que aparece escrito numa OS. Não complete a lista com itens "típicos" que ninguém citou.
- Ferramenta da equipe (alicate, manifold) e gasto de teste (nitrogênio de teste) não entram, a menos que o relato
  diga que foram aplicados no equipamento.
- Itens de clientes diferentes nunca se misturam: um envio por cliente.
- Nunca escreva no Auvo, no WhatsApp ou no Telegram por esta skill.
- Não copie relatos para a resposta final (LGPD): só contagens e o `id` da proposta.
