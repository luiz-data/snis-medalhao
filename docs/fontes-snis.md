# Catálogo de fontes — SNIS

Este catálogo documenta a **fonte base** do projeto — a tabela do SNIS
distribuída pela Base dos Dados. Segue o mesmo padrão de
[`fontes-ibge.md`](fontes-ibge.md): nada entra no projeto sem uma linha aqui.

---

## SNIS-AE — Município: água e esgoto

- **ID interno:** SNIS-AE
- **Nome (conjunto):** Sistema Nacional de Informações sobre Saneamento (SNIS)
- **Nome (tabela):** `municipio_agua_esgoto` *(nome técnico — não informado na
  página; sustentado por [`contagens.md`](contagens.md) e
  [`spec-ingestao.md`](spec-ingestao.md))*
- **Origem:** Base dos Dados (distribuição); fonte original **Ministério do
  Desenvolvimento Regional (MDR)** / Secretaria Nacional de Saneamento (SNS) —
  conforme a página.
- **URL (página da tabela):**
  https://basedosdados.org/dataset/2a543ad8-3cdb-4047-9498-efe7fb8ed697?table=df7cf198-4889-4baf-bb77-4e0e28eb90ca
- **Identificadores do site** (códigos da URL, **não do BigQuery**):
  - `dataset` (UUID): `2a543ad8-3cdb-4047-9498-efe7fb8ed697`
  - `table` (UUID): `df7cf198-4889-4baf-bb77-4e0e28eb90ca`
- **Identificadores do BigQuery / slugs:**
  - `dataset_id`: `br_mdr_snis` · `table_id`: `municipio_agua_esgoto` — conforme o
    repositório ([`contagens.md`](contagens.md) e
    [`pipeline/ingestao.py`](../pipeline/ingestao.py)); **não informados na página**.
  - **BigQuery:** `basedosdados.br_mdr_snis.municipio_agua_esgoto` — **caminho
    derivado da convenção da Base dos Dados** (projeto `basedosdados`, formato
    `basedosdados.<conjunto>.<tabela>`, ver
    [docs de acesso via BigQuery](https://basedosdados.org/en/docs/access_data_bq));
    **confira na aba de acesso da página da tabela** (não verificado aqui).
- **Data de acesso:** 2026-11-08
- **Frequência de atualização:** não informado na página. A página diz apenas:
  *"Anualmente, o SNIS coleta dados dos municípios e dos prestadores de
  serviços"*.
- **Data da última atualização (publicação):** não informado na página.

### O que a tabela contém

- **Grão:** uma linha por **(ano, município)**. A chave `(ano, id_municipio)`
  é única — **0 duplicatas** ([`contagens.md`](contagens.md)).
- **Cobertura temporal:** **1995–2022** (28 anos) — conforme a página
  ("1995 - 2022") e [`contagens.md`](contagens.md).
- **Abrangência:** **27 UFs** e **5.549 municípios distintos**
  ([`contagens.md`](contagens.md)).
- **Volume:** **119.256 registros** × **133 colunas**
  ([`contagens.md`](contagens.md); confere com o arquivo, ver abaixo).
- **Uso no projeto:** é a tabela base de todo o pipeline — vira
  `bronze.municipio_agua_esgoto` ([`spec-ingestao.md`](spec-ingestao.md)) e,
  tipada, `silver.municipio_agua_esgoto`; alimenta os 11 marts da gold.

### Arquivo bruto

| Item | Valor |
|---|---|
| Caminho | `data/raw/br_mdr_snis_municipio_agua_esgoto.csv.gz` |
| Tamanho | **23.227.167 bytes** (≈ 22,2 MiB); descompactado ≈ 59.266.190 bytes |
| sha256 | `09a578b190ad891a9661944270bd7c5cd73cc102a1cf6da241c7fe31d16ffe3c` |
| Linhas | **119.256** (+ 1 cabeçalho = 119.257 no arquivo) |
| Colunas | **133** |
| Criação do arquivo (evidência) | **2026-11-04 22:01:49** (data de nascimento no
  disco; **muda se o arquivo for copiado** — por isso é indício, não prova da data
  de extração) |

> O `.csv.gz` **não é descompactado** e **não é versionado** (`data/raw/` está no
> `.gitignore`). A leitura é feita direto do `.gitignore`d pelo DuckDB
> (`read_csv(..., all_varchar=true, header=true, delim=',', encoding='utf-8')`),
> ver [`pipeline/ingestao.py`](../pipeline/ingestao.py).

### Como reproduzir a obtenção

Só caminhos sustentados pela página ou pelo repositório. Qualquer passo não
verificável está marcado **a confirmar**.

> **Evidência: cabeçalho gzip SEM nome original e SEM data de modificação**
> (`FLG=0x00`, `MTIME=0x00000000`, `OS=0x00`/FAT — confirmado por `file` e
> `xxd`). Um `gzip arquivo` local no Mac/Linux normalmente gravaria o nome
> original, a data e `OS=Unix`; a ausência deles é **indício de arquivo gerado
> fora deste computador** (stream/export gzipado programaticamente), e não de
> compressão local. É só indício — não identifica qual dos caminhos abaixo foi
> usado.

1. **Download pela página da Base dos Dados** — abrir a URL acima e usar a opção
   de download da tabela. **A confirmar:** se a página entrega o CSV já como
   `.csv.gz` com este nome de arquivo, ou se o `.gz` foi gerado localmente após o
   download (a página não detalha o formato do download).

2. **Exportação pelo console do BigQuery** — mesmo caminho usado para a população
   do IBGE ([`fontes-ibge.md`](fontes-ibge.md)): consultar
   `br_mdr_snis.municipio_agua_esgoto` no console e exportar o resultado como CSV.
   **Exige:** conta Google e um **projeto de faturamento do BigQuery**. **A
   confirmar:** o `project.dataset.table` exato (ver *Identificadores*).

3. **Pacote Python `basedosdados`** — baixar a tabela via biblioteca oficial
   (`basedosdados`). **Exige:** conta Google e **projeto de faturamento do
   BigQuery** (`billing_project_id`). **A confirmar:** `dataset_id`/`table_id`
   exatos aceitos pela biblioteca.

> **Qual caminho foi usado nesta extração: a confirmar.** Os três acima ficam como
> alternativas equivalentes; nenhum está marcado como canônico até confirmação.

### Onde salvar e como conferir

- **Salvar em:** `data/raw/br_mdr_snis_municipio_agua_esgoto.csv.gz` (nome
  esperado por [`pipeline/ingestao.py`](../pipeline/ingestao.py)). **Não
  descompactar.**
- **Conferir integridade:**
  ```bash
  shasum -a 256 data/raw/br_mdr_snis_municipio_agua_esgoto.csv.gz
  # esperado: 09a578b190ad891a9661944270bd7c5cd73cc102a1cf6da241c7fe31d16ffe3c
  ```
- **Conferir contagens:**
  ```bash
  gzcat data/raw/br_mdr_snis_municipio_agua_esgoto.csv.gz | wc -l   # 119257 (inclui cabeçalho)
  gzcat data/raw/br_mdr_snis_municipio_agua_esgoto.csv.gz | head -1 | awk -F',' '{print NF}'  # 133
  ```
  A ingestão ([`spec-ingestao.md`](spec-ingestao.md) §7) também valida linhas e
  colunas na gravação e faz `ROLLBACK` se divergirem.

### Limitações conhecidas

- **Indicadores urbanos só até 2021:** a população urbana autodeclarada é 100%
  nula em 2022; os marts urbanos usam 2021 e nunca 2022 (D2).
- **Alerta A2 (urbana atendida > urbana):** massivo antes de 2010; não plotar
  cobertura urbana antes de 2010 (D5).
- **IN049 (perdas) 2021 não reconciliado** com divulgações oficiais (D40 /
  README).
- **Esgoto urbano "entre informantes"** (viés de seleção, marts 1 e 9) e
  **coleta > 100% em 1998/1999** (mart 2) — ver README e
  [`decisoes.md`](decisoes.md).
- **Semântica fina de investimento/receita** a confirmar no dicionário do SNIS;
  valores **nominais**, sem deflação (marts 5 e 8).

Inventário completo em [`spec-gold.md`](spec-gold.md) §8 e
[`decisoes.md`](decisoes.md).

### Licença / termos de uso

- **Licença:** **não informado na página.**
- **Termos:** a página exibe apenas os links "Termos de uso" e "Política de
  privacidade", **sem o texto** desses termos (não citado aqui para não inventar
  conteúdo). A licença MIT deste repositório cobre **o código, não os dados**.
- **Consulte os termos da fonte** antes de redistribuir:
  [página da tabela na Base dos Dados](https://basedosdados.org/dataset/2a543ad8-3cdb-4047-9498-efe7fb8ed697?table=df7cf198-4889-4baf-bb77-4e0e28eb90ca)
  (links "Termos de uso"/"Política de privacidade") e o SNIS/MDR.
