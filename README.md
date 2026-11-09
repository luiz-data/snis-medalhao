# SNIS — Pipeline medalhão

Pipeline de dados com arquitetura medalhão sobre o **SNIS** (Sistema Nacional
de Informações sobre Saneamento), tabela `municipio_agua_esgoto`, cobrindo
**1995 a 2022** (119.256 registros, 133 variáveis, 5.549 municípios).

## Arquitetura

| Camada | Status | Descrição |
|---|---|---|
| **bronze** | ✅ feita | Espelho fiel do CSV — tudo como texto, sem transformações. |
| **silver** | ✅ feita | Tipagem fiel da bronze e correção de um erro de digitação de coluna. |
| **gold** | ✅ feita | **10 marts** de indicadores e agregações para análise. |
| **dashboard** | 🔜 próxima | Visualização em Streamlit. |

O pipeline cruza o SNIS com o **IBGE** (DTB de municípios, estimativas de
**população** 1991–2025 e **PIB** municipal 2010–2021, via API do SIDRA), usados
como denominador de cobertura, recorte territorial (UF/região) e eixo de renda.

Specs: [`docs/spec-ingestao.md`](docs/spec-ingestao.md) (bronze) ·
[`docs/spec-transformacao.md`](docs/spec-transformacao.md) (silver) ·
[`docs/spec-ibge.md`](docs/spec-ibge.md) (IBGE) ·
[`docs/spec-gold.md`](docs/spec-gold.md) (gold).

## A camada silver

A silver faz **uma coisa só**: tipa fielmente a bronze, sem semântica de
negócio. 119.256 linhas entram e 119.256 saem; 133 colunas, na mesma ordem da
bronze.

- **Tipos:** 26 `INTEGER`, 2 `VARCHAR` (`id_municipio`, `sigla_uf`),
  105 `DECIMAL(18,2)`.
- **Único rename:** `populacao_atentida_esgoto` → `populacao_atendida_esgoto`
  (corrige erro de digitação da fonte).
- **Regras bloqueantes** (`ROLLBACK` + saída com erro): valor que não converte,
  fora de faixa, `DECIMAL` com mais de 2 casas, `ano` fora de `AAAA`,
  `id_municipio` fora de 7 dígitos, chave `(ano, id_municipio)` nula/repetida,
  contagem de linhas ou colunas diferente da bronze, célula vazia ou só espaços.
- **Alertas** (preserva o dado, só conta e reporta): 43 colunas com negativos,
  47.934 linhas com `populacao_atendida_agua > populacao_urbana`, 23 colunas
  `indice_*` acima de 100, `populacao_urbana_atendida_esgoto` 100% nula em 2022.

Anomalias **não são corrigidas** na silver — isso é responsabilidade da gold.

## A camada gold — os 10 marts

Cada mart é um `SELECT` em `sql/gold/NN_nome.sql`; o executor
([`pipeline/gold.py`](pipeline/gold.py)) compõe o `CREATE TABLE` e recria o schema
`gold` do zero. Grão, fórmulas e decisões estão em
[`docs/spec-gold.md`](docs/spec-gold.md) e [`docs/indicadores.md`](docs/indicadores.md).

| # | Tabela (`gold.`) | Pergunta de negócio |
|---|---|---|
| 1 | `atendimento_uf_ano` | Qual % da população **urbana** tem água e esgoto, por UF e ano? |
| 2 | `esgoto_coleta_tratamento_ano` | Quanto do esgoto é **coletado e tratado** no Brasil, ano a ano? |
| 3 | `perdas_consumo_uf_ano` | Quanta água se **perde** na distribuição e quanto se **consome** por pessoa, por UF e ano? |
| 4 | `ranking_atendimento_variacao` | Quais municípios mais **melhoraram/pioraram** no atendimento urbano de água entre 2010 e 2021? |
| 5 | `financeiro_uf_ano` | Quanto se **investe e gasta** por UF e ano (tarifa, despesa unitária), em R$ nominais? |
| 6 | `atendimento_porte_ano` | Como variam as coberturas de água e esgoto por **faixa de porte** do município? |
| 7 | `populacao_sem_servico_uf_ano` | Quantos habitantes, em **números absolutos**, estão sem água e sem coleta de esgoto, por UF? |
| 8 | `investimento_per_capita_uf_ano` | Quanto se **investe por habitante**, por UF e ano, em R$ nominais? |
| 9 | `atendimento_vs_pib_2021` | Como cobertura, perdas e investimento se relacionam com o **PIB per capita** do município em 2021? |
| 10 | `avanco_por_renda_painel` | O atendimento urbano de água **avançou mais** entre 2010 e 2021 em municípios de maior ou menor **renda**? |

Contagens de todas as tabelas (bronze, silver, gold) e tempo de reconstrução em
[`docs/contagens.md`](docs/contagens.md).

## Stack

Python · [uv](https://docs.astral.sh/uv/) · DuckDB · Streamlit · pytest · ruff

## Dados

Os dados **não ficam no repositório**. Para obtê-los:

1. Acesse o [Base dos Dados](https://basedosdados.org/) e baixe a tabela
   `br_mdr_snis.municipio_agua_esgoto`.
2. Salve como `data/raw/br_mdr_snis_municipio_agua_esgoto.csv.gz`
   (**não descompacte**).

## Como rodar

```bash
uv sync                        # instala dependências
uv run python executar.py      # apaga o banco e roda as 6 etapas do zero
uv run pytest -v               # testes (bronze, silver, IBGE e gold)
uv run ruff check .            # linter
```

`executar.py` roda as **6 etapas** em ordem: bronze SNIS → silver SNIS → bronze
IBGE → silver IBGE → cobertura SNIS×IBGE → gold (10 marts). Reconstrução completa
em ~10 s (ver [`docs/contagens.md`](docs/contagens.md)).

## MCP (opcional)

Para explorar o banco via MCP, em modo **somente leitura**:

```bash
claude mcp add --scope project duckdb -- uvx mcp-server-motherduck --db-path snis.duckdb
```

## Estrutura de pastas

```
.
├── data/raw/                  # fonte (somente leitura, fora do repo)
├── docs/
│   ├── contagens.md               # contagens da fonte e de todas as tabelas
│   ├── decisoes.md                # decisões aprovadas (D1–D33)
│   ├── indicadores.md             # fórmulas e grão dos 10 marts
│   ├── fontes-ibge.md             # catálogo das fontes IBGE
│   ├── investigacao-silver.md     # base dos números da silver
│   ├── spec-ingestao.md           # spec da camada bronze
│   ├── spec-transformacao.md      # spec da camada silver
│   ├── spec-ibge.md               # spec da ingestão/silver do IBGE
│   └── spec-gold.md               # spec da camada gold (10 marts)
├── pipeline/
│   ├── db.py                  # caminhos e conexão com o banco
│   ├── conferir.py            # validação rápida do CSV
│   ├── ingestao.py            # bronze SNIS
│   ├── transformacao.py       # silver SNIS
│   ├── ingestao_ibge.py       # bronze IBGE
│   ├── transformacao_ibge.py  # silver IBGE
│   ├── cobertura.py           # cobertura de junção SNIS × IBGE
│   └── gold.py                # executor dos 10 marts
├── sql/gold/                  # um SELECT por mart (NN_nome.sql)
├── tests/
│   ├── test_bronze.py         # testes da bronze
│   ├── test_silver.py         # testes da silver
│   ├── test_ibge_bronze.py    # testes da bronze IBGE
│   ├── test_ibge_silver.py    # testes da silver IBGE
│   └── test_gold.py           # testes dos 10 marts
├── executar.py                # orquestrador do pipeline (6 etapas)
└── pyproject.toml
```

## Limitações conhecidas

Pendências que o **dashboard** precisa respeitar (inventário completo em
[`docs/spec-gold.md`](docs/spec-gold.md) §8 e [`docs/decisoes.md`](docs/decisoes.md)):

- **Esgoto urbano "entre informantes"** (marts 1 e 9): a cobertura urbana de
  esgoto cobre só quem informa esgoto (≈72,5% em 2021), não o Brasil todo — viés
  de seleção; distinta do IN056 por porte/UF (55,8%). Rotular como tal. Ver
  [D32](docs/decisoes.md).
- **Indicadores urbanos só até 2021:** a população urbana autodeclarada é **100%
  nula em 2022**; os marts urbanos (1, 4, 9, 10) usam 2021 e nunca 2022. Ver
  [D2](docs/decisoes.md).
- **Alerta A2 (urbana atendida > urbana):** massivo **antes de 2010**, pequeno na
  janela (41 casos 2010–2021, excluídos com flag). Não plotar cobertura urbana
  antes de 2010. Ver [D5](docs/decisoes.md).
- **Semântica fina de investimento/receita** (prestador vs. município vs. estado;
  direta vs. indireta) nos marts 5 e 8 **a confirmar** no dicionário do SNIS; os
  valores são **nominais** (sem deflação) e mantidos como vêm da fonte — ressalva
  no painel. Ver [`docs/indicadores.md`](docs/indicadores.md).
- **Esgoto importado/exportado (mart 2):** a definição oficial de "volume
  disponibilizado" de esgoto está **a confirmar**; o índice pode passar de 100 por
  importação/exportação. Ver [D23](docs/decisoes.md).

A **silver não converte unidade nenhuma** nem corrige anomalias — isso é papel da
gold (decisões D1–D33).
