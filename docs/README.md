# Documentação — guia de leitura

Leia nesta ordem. Os documentos se dividem em **contrato** (o que o código deve
respeitar: specs e decisões) e **histórico** (como chegamos aqui: investigações e
conferências).

## Contrato

1. [`spec-ingestao.md`](spec-ingestao.md) — spec da camada **bronze** (SNIS): espelho fiel do CSV.
2. [`spec-transformacao.md`](spec-transformacao.md) — spec da camada **silver** (SNIS): tipagem fiel, regras bloqueantes e alertas.
3. [`spec-ibge.md`](spec-ibge.md) — spec da ingestão e silver do **IBGE** (DTB, população, PIB).
4. [`fontes-ibge.md`](fontes-ibge.md) — catálogo obrigatório das fontes IBGE: IDs, URLs, chaves e limitações.
5. [`spec-gold.md`](spec-gold.md) — spec da camada **gold** (11 marts), grão, fórmulas e limitações conhecidas (§8).
6. [`indicadores.md`](indicadores.md) — fichas dos indicadores: fórmula e grão de cada mart.
7. [`spec-dashboard.md`](spec-dashboard.md) — spec do **dashboard** Streamlit sobre a gold.
8. [`decisoes.md`](decisoes.md) — registro das decisões aprovadas (D1–D40); referência cruzada de todas as specs.

## Histórico

- [`investigacao-silver.md`](investigacao-silver.md) — base empírica dos números da silver (negativos, alertas, nulos).
- [`contagens.md`](contagens.md) — contagens da fonte e de todas as tabelas (bronze, silver, gold) e tempo de reconstrução.
