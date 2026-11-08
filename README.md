# SNIS — Pipeline medalhão

Pipeline de dados com arquitetura medalhão sobre o **SNIS** (Sistema Nacional
de Informações sobre Saneamento), tabela `municipio_agua_esgoto`, cobrindo
**1995 a 2022** (119.256 registros, 133 variáveis, 5.549 municípios).

## Arquitetura

| Camada | Status | Descrição |
|---|---|---|
| **bronze** | ✅ feita | Espelho fiel do CSV — tudo como texto, sem transformações. |
| **silver** | ✅ feita | Tipagem fiel da bronze e correção de um erro de digitação de coluna. |
| **gold** | 🔜 próxima | Indicadores e agregações para análise. |
| **dashboard** | 🔜 próxima | Visualização em Streamlit. |

Specs: [`docs/spec-ingestao.md`](docs/spec-ingestao.md) (bronze) ·
[`docs/spec-transformacao.md`](docs/spec-transformacao.md) (silver).

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
uv run python executar.py      # apaga o banco e roda a ingestão do zero
uv run pytest -v               # testes
uv run ruff check .            # linter
```

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
│   ├── contagens.md               # contagens de referência da fonte
│   ├── investigacao-silver.md     # base dos números da silver
│   ├── spec-ingestao.md           # spec da camada bronze
│   └── spec-transformacao.md      # spec da camada silver
├── pipeline/
│   ├── db.py                  # caminhos e conexão com o banco
│   ├── conferir.py            # validação rápida do CSV
│   ├── ingestao.py            # ingestão da camada bronze
│   └── transformacao.py       # transformação da camada silver
├── tests/
│   ├── test_bronze.py         # testes da bronze
│   └── test_silver.py         # testes da silver
├── executar.py                # orquestrador do pipeline
└── pyproject.toml
```

## Limitações conhecidas

- **Unidades** das medidas (volume, extensão, consumo elétrico) a confirmar no
  dicionário do SNIS; a silver **não converte** unidade nenhuma.
- **Valores monetários** são provavelmente **nominais** (reais da data da
  coleta); não há deflação na silver.
- `populacao_urbana_atendida_esgoto` é **100% nula em 2022** — mudança
  metodológica da fonte ou falha de carga, não confirmado.
