# Spec da ingestão (bronze)

| | |
|---|---|
| **Camada** | bronze (equivale ao `raw` da aula) |
| **Fonte** | `data/raw/br_mdr_snis_municipio_agua_esgoto.csv.gz` (somente leitura) |
| **Destino** | banco `snis.duckdb` · schema `bronze` · tabela `municipio_agua_esgoto` |

> **Referências:** fonte, identificadores, hash e obtenção em
> [`docs/fontes-snis.md`](fontes-snis.md); contagens em
> [`docs/contagens.md`](contagens.md) (119.256 linhas, 133 colunas); leitura de
> referência já existente em [`pipeline/conferir.py`](../pipeline/conferir.py).

---

## 1. Mapa de tabelas

| Arquivo | Tabela | Linhas esperadas |
|---|---|---|
| `br_mdr_snis_municipio_agua_esgoto.csv.gz` | `bronze.municipio_agua_esgoto` | 119.256 |

A tabela tem as mesmas **133 colunas** do arquivo, com os mesmos nomes e na
mesma ordem.

---

## 2. Proibições

A bronze é um espelho fiel da fonte. É proibido:

- converter tipos, filtrar linhas, remover duplicatas ou apagar colunas;
- renomear colunas, tratar nulos ou aparar espaços;
- adicionar colunas que não existem no arquivo;
- escrever qualquer coisa dentro de `data/raw/`.

Correções só acontecem na passagem da bronze para a silver.

---

## 3. Reexecução

Rodar a ingestão duas vezes dá o mesmo resultado: a tabela é recriada a cada
execução, sem acumular linhas. O schema `bronze` é criado se não existir.

---

## 4. Leitura

- Leitura direta do `.csv.gz`, sem descompactar.
- Encoding `utf-8` declarado explicitamente.
- Separador vírgula, com cabeçalho na primeira linha.
- Leitura feita pelo DuckDB, sem pandas.

---

## 5. Tipagem

Todas as colunas entram como texto (`VARCHAR`). Células vazias viram `NULL`.
Nada é interpretado como número, data ou booleano.

---

## 6. Saída na tela

Ao final, o script imprime:

- o nome da tabela gravada;
- a quantidade de linhas e de colunas gravadas.

---

## 7. Tratamento de erro

O script termina com `sys.exit(1)` e uma mensagem clara quando:

- o arquivo de origem não existe;
- a contagem de linhas na tabela difere da contagem lida do arquivo;
- o número de colunas na tabela difere do número no arquivo.

A gravação roda numa única transação: se qualquer validação falhar, a
transação é desfeita e nenhuma tabela parcial fica no banco.

> **Nota:** a contagem esperada é a lida do próprio arquivo na execução. O
> valor de [`docs/contagens.md`](contagens.md) (119.256 linhas, 133 colunas) é
> referência para os testes, não uma constante do código.

---

## Responsabilidades dos módulos

| Módulo | Responsabilidade |
|---|---|
| `pipeline/db.py` | Caminho da raw, caminho do banco (`snis.duckdb` na raiz do projeto) e a função de conexão. Não conhece nomes de tabela, não lê CSV e não imprime nada. |
| `pipeline/ingestao.py` | Lê o CSV e grava na bronze. |

Nenhuma conexão global: cada execução abre e fecha a sua.
