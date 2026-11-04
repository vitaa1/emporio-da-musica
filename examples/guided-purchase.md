# Guided purchase: from a broad request to an exact quote

Recorded with `qwen2.5:3b` and synthetic demo data in the [evaluation run](../evals/results/2026-11-04-readme-examples.json). Each conversation starts a fresh session.

```text
> Quero comprar um violão
Boa escolha! Temos 35 opções em Violões. Os preços de tabela vão de R$ 429,90 a R$ 12.000,00. Algumas marcas: Yamaha, Tagima, Giannini, Rozini, Shelby, Crafter. Você tem preferência de marca ou um valor máximo? Se preferir, peça para eu mostrar as opções.

> Yamaha
1. Yamaha C40 Nylon Natural — R$ 599,90
2. Yamaha C70 Nylon Natural — R$ 849,00
3. Yamaha F310 Aço Natural — R$ 699,90
4. Yamaha FG800 Dreadnought Natural — R$ 1.299,00
5. Yamaha NTX1 Elétrico Nylon Natural — R$ 3.499,00
6. Yamaha APX600 Elétrico Aço Preto — R$ 1.899,00
7. Yamaha CG162S Nylon Natural — R$ 1.699,00
Qual modelo te interessa?

Nada foi comprado ou reservado; valores do catálogo da loja.

> Quero o segundo
2. Yamaha C70 Nylon Natural
Em estoque: 8 unidade(s).
Preço por unidade: R$ 849,00.
Formas de pagamento:
- PIX: R$ 806,55 (5% de desconto)
- Débito: R$ 849,00
- Boleto: R$ 849,00
- Crédito: até 8x sem juros, total de R$ 849,00

Nada foi comprado ou reservado; valores do catálogo da loja.

Para continuar, informe a quantidade, a forma de pagamento.

> 2 unidades no pix
2. Yamaha C70 Nylon Natural — disponível para a quantidade solicitada. Preço de tabela por unidade: R$ 849,00. Desconto PIX: 5%. Total para 2 unidade(s): R$ 1.613,10 (PIX).

Nada foi comprado ou reservado; valores do catálogo da loja.
```

