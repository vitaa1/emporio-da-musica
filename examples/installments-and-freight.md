# Installments and destination-dependent freight

Recorded with `qwen2.5:3b` and synthetic demo data in the [evaluation run](../evals/results/2026-11-04-readme-examples.json). Each conversation starts a fresh session.

```text
> Quero uma unidade do Takamine GD20 em 10 vezes no crédito
1. Takamine GD20 Dreadnought Natural — disponível para a quantidade solicitada. Preço de tabela por unidade: R$ 2.199,00. Total para 1 unidade(s): R$ 2.199,00 (crédito). Parcelamento sem juros: 10x de R$ 219,90.

Nada foi comprado ou reservado; valores do catálogo da loja.

> Quanto custa o frete de uma unidade do Takamine GD20 no pix para Campo Grande MS?
1. Takamine GD20 Dreadnought Natural — disponível para a quantidade solicitada. Preço de tabela por unidade: R$ 2.199,00. Desconto PIX: 5%. Total para 1 unidade(s): R$ 2.089,05 (PIX).
Entrega em Campo Grande/MS: frete grátis (pedido acima de R$ 500,00). Subtotal dos produtos: R$ 2.089,05; total com frete: R$ 2.089,05.
Prazo estimado pelo manual: 1 a 3 dias úteis, por motoboy próprio. É uma estimativa, não uma data de entrega garantida. (Manual da loja, seção 5.1.)

Nada foi comprado ou reservado; valores do catálogo da loja.

> Quanto custa o frete de uma unidade do Takamine GD20 no boleto para Dourados MS?
Nesta demonstração, só calculo o frete para entregas em Campo Grande/MS. O manual não lista as cidades da região metropolitana, e o frete para outras cidades depende do CEP, do peso e das dimensões do produto, sem integração com Correios ou Jadlog aqui. Pelo manual, os prazos estimados são PAC 5 a 12, SEDEX 2 a 5 e Jadlog 3 a 8 dias úteis, e instrumentos de grande porte podem exigir cotação especial (seção 5.2). A loja precisa confirmar o valor; não solicitei essa cotação.
```

