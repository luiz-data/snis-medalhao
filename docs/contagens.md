# Contagens da fonte (data/raw)

Arquivo: br_mdr_snis_municipio_agua_esgoto.csv.gz
Origem: Base dos Dados, br_mdr_snis.municipio_agua_esgoto

| Item | Valor |
|---|---|
| Linhas | 119256 |
| Colunas | 133 |
| Anos | 1995 a 2022 (28) |
| Municípios distintos | 5549 |
| UFs | 27 |
| Chaves (ano, id_municipio) duplicadas | 0 |

# Contagens por tabela do banco (`snis.duckdb`)

Reconstrução do zero (`executar.py`): **2026-11-08**. Tempo total do pipeline:
**10,48 s** (bronze SNIS 4,29 · silver SNIS 1,75 · bronze IBGE 0,49 · silver IBGE
3,60 · cobertura 0,05 · gold 0,31). Conferência de conteúdo vs. backup anterior:
**EXCEPT nos dois sentidos = 0/0 em todas as 14 tabelas** silver+gold.

## bronze

| Tabela | Linhas | Colunas |
|---|---:|---:|
| `municipio_agua_esgoto` | 119.256 | 133 |
| `ibge_dtb_municipio` | 5.571 | 9 |
| `ibge_pib_municipio` | 66.840 | 6 |
| `ibge_populacao_municipio` | 191.099 | 3 |

## silver

| Tabela | Linhas | Colunas |
|---|---:|---:|
| `municipio_agua_esgoto` | 119.256 | 133 |
| `ibge_dtb_municipio` | 5.571 | 10 |
| `ibge_pib_municipio` | 66.840 | 3 |
| `ibge_populacao_municipio` | 191.098 | 3 |

> `ibge_populacao_municipio`: 191.099 na bronze → **191.098** na silver. A linha
> excluída é **ano 2025, `id_municipio` nulo** (registro malformado), removida pela
> regra **IA6** (**D13**; exclusão só vale fora da janela 2010–2021).

## gold (10 marts + mart de apoio do dashboard)

| # | Tabela | Linhas | Colunas |
|---|---|---:|---:|
| 1 | `atendimento_uf_ano` | 324 | 11 |
| 2 | `esgoto_coleta_tratamento_ano` | 28 | 13 |
| 3 | `perdas_consumo_uf_ano` | 754 | 12 |
| 4 | `ranking_atendimento_variacao` | 4.431 | 10 |
| 5 | `financeiro_uf_ano` | 754 | 16 |
| 6 | `atendimento_porte_ano` | 72 | 11 |
| 7 | `populacao_sem_servico_uf_ano` | 324 | 14 |
| 8 | `investimento_per_capita_uf_ano` | 324 | 12 |
| 9 | `atendimento_vs_pib_2021` | 5.302 | 13 |
| 10 | `avanco_por_renda_painel` | 8 | 6 |
| 11 | `kpis_brasil` (apoio do dashboard, **D34**) | 12 | 15 |

> `kpis_brasil` (mart 11): KPIs nacionais por ano (2010–2021) para os cartões e o
> resumo do dashboard, reproduzindo a fórmula de cada mart de origem (sem cálculo
> na tela). Reconstrução do zero em **2026-11-09**: `executar.py` recria todas as
> tabelas e o **EXCEPT nos dois sentidos = 0/0 nas 11 tabelas gold** contra o
> backup anterior.
