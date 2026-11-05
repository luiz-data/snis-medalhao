# SNIS — Pipeline medalhão

Pipeline de dados com arquitetura medalhão sobre o **SNIS** (Sistema Nacional
de Informações sobre Saneamento), tabela `municipio_agua_esgoto`, cobrindo
**1995 a 2022** (119.256 registros, 133 variáveis, 5.549 municípios).

## Arquitetura

| Camada | Status | Descrição |
|---|---|---|
| **bronze** | ✅ feita | Espelho fiel do CSV — tudo como texto, sem transformações. |
| **silver** | 🔜 próxima | Tipagem, limpeza e padronização. |
| **gold** | 🔜 próxima | Indicadores e agregações para análise. |

Spec da ingestão: [`docs/spec-ingestao.md`](docs/spec-ingestao.md)

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

## Estrutura de pastas

```
.
├── data/raw/                  # fonte (somente leitura, fora do repo)
├── docs/
│   ├── contagens.md           # contagens de referência da fonte
│   └── spec-ingestao.md       # spec da camada bronze
├── pipeline/
│   ├── db.py                  # caminhos e conexão com o banco
│   ├── conferir.py            # validação rápida do CSV
│   └── ingestao.py            # ingestão da camada bronze
├── tests/
│   └── test_bronze.py         # testes da bronze
├── executar.py                # orquestrador do pipeline
└── pyproject.toml
```
