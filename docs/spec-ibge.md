# Spec da ingestão e transformação do IBGE (bronze → silver)

| | |
|---|---|
| **Status** | aprovada (D7–D10 em 2026-11-08); D7 provisória, revisar após 1ª medição |
| **Versão** | 1 |
| **Data** | 2026-11-08 |
| **Responsável** | Luiz |
| **Banco** | `snis.duckdb` (o mesmo do SNIS) · schemas `bronze` e `silver` |
| **Fontes** | IBGE-POP, IBGE-DTB, IBGE-PIB (ver [`fontes-ibge.md`](fontes-ibge.md)) |

> **Referências de leitura obrigatória:** catálogo [`fontes-ibge.md`](fontes-ibge.md);
> fórmulas e uso nos marts [`indicadores.md`](indicadores.md); decisões
> **D1–D6 APROVADAS em 2026-11-08** [`decisoes.md`](decisoes.md); specs-modelo
> [`spec-ingestao.md`](spec-ingestao.md) (bronze SNIS) e
> [`spec-transformacao.md`](spec-transformacao.md) (silver SNIS, alertas A1–A4).

Esta spec é **só documentação**. Não cria código, não altera dados nem outras
specs. Estende o pipeline medalhão do SNIS com **três fontes IBGE** no mesmo
banco, respeitando as mesmas regras de bronze (espelho fiel, tudo `VARCHAR`) e
de silver (tipagem estrita, sem `TRY_CAST`, alertas bloqueantes e não
bloqueantes) já aprovadas para o SNIS.

---

## 0. Objetivo

Trazer para o `snis.duckdb` as três fontes externas de que os marts dependem,
porque **nenhuma delas existe na silver do SNIS** (D1): não há população total,
nem PIB, nem UF/região. Sem elas, 9 dos 10 marts não fecham.

| Fonte | Tabela silver | Dá ao projeto | Marts que dependem (D1) |
|---|---|---|---|
| IBGE-POP | `silver.ibge_populacao_municipio` | população residente total do município por ano | **6, 7, 8, 9, 10** |
| IBGE-PIB | `silver.ibge_pib_municipio` | PIB municipal nominal por ano | **9, 10** |
| IBGE-DTB | `silver.ibge_dtb_municipio` | UF e região por município (substitui a seed de UF) | **1, 3, 4, 5, 7, 8** |

Só o **mart 2** (`esgoto_coleta_tratamento_ano`) é 100% SNIS e não usa nenhuma
fonte IBGE.

---

## 1. Escopo

**Dentro:**

- Bronze das três fontes: espelho fiel do arquivo baixado, **todas as colunas
  `VARCHAR`**, uma tabela por fonte.
- Silver das três fontes: tipada, renomeada, validada, com `id_municipio` de
  **7 dígitos como texto**.
- **Teste de cobertura de junção** de cada fonte IBGE contra a silver do SNIS
  (seção 8).
- Integração no `executar.py` e novos testes (seção 9).

**Fora** (responsabilidade da gold, como no SNIS):

- cálculo de indicadores, razões ou per capita;
- deflação ou qualquer correção monetária do PIB (valores ficam **nominais**);
- correção manual de emancipações/fusões/renomeações de municípios (D6);
- recorte da janela 2010–2021 — a **bronze e a silver carregam a série
  completa**; o recorte temporal acontece **só nos marts** (seção 7);
- nomes de município (a silver carrega `id_municipio`; o nome fica na DTB apenas
  como rótulo descritivo, ver seção 5.3).

---

## 2. Grão e chave

| Fonte | Grão | Chave | Unicidade esperada |
|---|---|---|---|
| IBGE-POP | município × ano | `(ano, id_municipio)` | 0 duplicatas, 0 nulos |
| IBGE-PIB | município × ano | `(ano, id_municipio)` | 0 duplicatas, 0 nulos |
| IBGE-DTB | município (fotografia de **2025**, D6) | `id_municipio` | 0 duplicatas, 0 nulos |

`id_municipio` sempre com **7 dígitos, como texto**, preservando zeros à esquerda
(os 2 primeiros dígitos são o código da UF).

---

## 3. Origem dos arquivos e como obtê-los

**Convenção de pasta** (do catálogo): cada extração vai para
`data/raw/ibge/<fonte>/<data_extracao>/`, com um `MANIFEST.md` contendo
**origem, data de extração, nº de linhas e checksum** (ex.: `sha256`) de cada
arquivo. `<fonte>` ∈ `{populacao, pib, dtb}`; `<data_extracao>` no formato
`AAAA-MM-DD`. Nada em `data/raw/` é editado depois de gravado.

> O MANIFEST é a âncora dos critérios de aceite: a bronze valida linhas e
> colunas **contra os números do MANIFEST** da extração usada (seção 4).

### 3.1 IBGE-POP — via Base dos Dados (BigQuery)

Exportar a tabela `br_ibge_populacao.municipio` (ver [`fontes-ibge.md`](fontes-ibge.md))
salvando como CSV em `data/raw/ibge/populacao/<data_extracao>/`.

Consulta sugerida (**nomes de coluna a confirmar no BigQuery**):

```sql
-- a confirmar no BigQuery: nomes exatos de ano/id_municipio/populacao
SELECT
  ano,
  id_municipio,
  populacao
FROM `basedosdados.br_ibge_populacao.municipio`
ORDER BY ano, id_municipio;
```

Carregar a **série completa** disponível (1991–2025 segundo o catálogo).

### 3.2 IBGE-PIB — via Base dos Dados (BigQuery)

Exportar a tabela de PIB municipal (origem IBGE / SIDRA 5938) para
`data/raw/ibge/pib/<data_extracao>/`.

Consulta sugerida (**nome de tabela e de coluna de PIB a confirmar no BigQuery**;
o dataset de PIB municipal na Base dos Dados costuma ser `br_ibge_pib.municipio`):

```sql
-- a confirmar no BigQuery: dataset/tabela (br_ibge_pib.municipio?) e
-- nome da coluna de PIB nominal (pib? valor?)
SELECT
  ano,
  id_municipio,
  pib
FROM `basedosdados.br_ibge_pib.municipio`
ORDER BY ano, id_municipio;
```

Carregar a série completa (2002–2021; **2002–2009 retropolada**, seção 7).

### 3.3 IBGE-DTB 2025 (D6, D8)

**Fonte principal (D8) — arquivo oficial do IBGE:** o **relatório de municípios
da DTB 2025** (Divisão Territorial Brasileira), publicado em
`https://www.ibge.gov.br/.../divisao-territorial-brasileira.html` (arquivo
`.xls`/`.ods`/`.zip`). Procedimento:

1. **Preservar o original** exatamente como baixado em
   `data/raw/ibge/dtb/<data_extracao>/` (planilha/zip íntegro, somente leitura).
2. **Converter para CSV como passo separado e documentado** (no MANIFEST:
   ferramenta usada, aba de origem, encoding, colunas selecionadas), salvando o
   CSV ao lado do original na mesma pasta.
3. Da planilha, extrair **código do município (7 dígitos), UF e macrorregião**
   (e o nome do município como rótulo). Os **nomes exatos de coluna da DTB** vão
   para a seção 10 (*a confirmar na extração*).

A **versão é 2025** (D6) e deve constar no MANIFEST.

**Alternativa — Base dos Dados (só com a versão documentada):** diretório de
municípios (`br_bd_diretorios_brasil.municipio` — *a confirmar no BigQuery*), que
já traz `id_municipio`, `sigla_uf`, nome e região. Só usar se a **versão
territorial publicada estiver documentada** e corresponder a 2025 (D8).

```sql
-- alternativa; a confirmar no BigQuery: nome do diretório e das colunas de UF/região
SELECT
  id_municipio,
  nome,
  sigla_uf,
  nome_regiao
FROM `basedosdados.br_bd_diretorios_brasil.municipio`
ORDER BY id_municipio;
```

---

## 4. Bronze — espelho fiel (tudo `VARCHAR`)

Segue a [`spec-ingestao.md`](spec-ingestao.md): a bronze **não converte, não
filtra, não renomeia, não trata nulo**. Uma tabela por fonte:

| Fonte | Tabela bronze |
|---|---|
| IBGE-POP | `bronze.ibge_populacao_municipio` |
| IBGE-PIB | `bronze.ibge_pib_municipio` |
| IBGE-DTB | `bronze.ibge_dtb_municipio` |

**Regras de leitura:**

- Leitura direta do CSV pelo DuckDB (`read_csv`), **sem pandas**, sem
  descompactar manualmente.
- `all_varchar = true` — todas as colunas entram como `VARCHAR`.
- `encoding = 'utf-8'` explícito. Se o arquivo oficial do IBGE vier em
  `latin-1`/`windows-1252`, **converter para utf-8 na extração** (não na bronze)
  e registrar no MANIFEST; a bronze sempre lê utf-8.
- Separador e cabeçalho conforme o arquivo exportado (vírgula + cabeçalho na
  Base dos Dados); `header = true`.
- Célula vazia vira `NULL` (idêntico ao contrato da bronze SNIS).
- `CREATE SCHEMA IF NOT EXISTS bronze`; `CREATE OR REPLACE TABLE` (idempotente,
  recriada a cada execução, sem acumular).

**Transação e validação (ROLLBACK):** a gravação roda em **uma transação
única**. Validações bloqueantes (derrubam tudo com `ROLLBACK` + `sys.exit(1)`):

| # | Condição |
|---|---|
| BB1 | arquivo de origem ausente na pasta da extração |
| BB2 | nº de **linhas** gravadas ≠ nº de linhas do arquivo/MANIFEST |
| BB3 | nº de **colunas** gravadas ≠ nº de colunas do arquivo/MANIFEST |

A bronze imprime, ao final: nome da tabela, nº de linhas e nº de colunas
gravadas (igual ao SNIS).

---

## 5. Silver — tipada e validada

Segue o espírito da [`spec-transformacao.md`](spec-transformacao.md): **`CAST`
estrito em SQL** (sem `TRY_CAST` no caminho de gravação — `TRY_CAST` só em
diagnóstico depois de uma falha), **regex de pré-validação antes do `CAST`**,
transação única com `ROLLBACK`, alertas no modelo A1–A4. `id_municipio` sempre
`VARCHAR` de 7 dígitos.

### 5.1 `silver.ibge_populacao_municipio`

| Coluna silver | Origem (bronze) | Tipo | Observação |
|---|---|---|---|
| `ano` | `ano` | `INTEGER` | 4 dígitos |
| `id_municipio` | `id_municipio` | `VARCHAR` | 7 dígitos, zeros à esquerda |
| `populacao_total_ibge` | `populacao` | `INTEGER` | nome usado nas fórmulas dos marts (D10); inteiro, máx. ~12,4 mi cabe em `INTEGER` |

- **Pré-validação (regex, antes do CAST):** `ano` casa `^[0-9]{4}$`;
  `id_municipio` casa `^[0-9]{7}$`; `populacao` casa `^[0-9]+$` (inteiro não
  negativo, sem decimais).
- **Faixas válidas:** `ano` em 1991–2025; `populacao_total_ibge` ≥ 0 e abaixo do
  teto de `INTEGER` (maior município < 2,1 bi, folga ampla).
- **Checagem de revisão de série (não bloqueante, IA5):** comparar o valor
  ingerido de **São Paulo (`id_municipio = 3550308`) em 2021** com a referência
  IBGE de **12.396.372 habitantes**. A diferença (absoluta e %) é **registrada no
  relatório da execução**; não bloqueia (a série pode ser revisada entre
  publicações), mas um desvio grande sinaliza fonte ou ano trocados.

### 5.2 `silver.ibge_pib_municipio`

| Coluna silver | Origem (bronze) | Tipo | Observação |
|---|---|---|---|
| `ano` | `ano` | `INTEGER` | 4 dígitos |
| `id_municipio` | `id_municipio` | `VARCHAR` | 7 dígitos |
| `pib_municipio` | `pib` | `DECIMAL(18,2)` | **valor nominal** (seção 7); mesma escolha do SNIS para dinheiro |

- **Pré-validação (regex):** `ano` `^[0-9]{4}$`; `id_municipio` `^[0-9]{7}$`;
  `pib` casa `^[0-9]+(\.[0-9]{1,2})?$` (não negativo, **no máximo 2 casas
  decimais** — mesma regra B4 do SNIS: checar casas **no texto** antes do
  `CAST`, porque `CAST(... AS DECIMAL(_,2))` arredonda em silêncio).
- **Faixas válidas:** `ano` em 2002–2021; `pib_municipio` ≥ 0.
- **Unidade mantida como na fonte (D9):** bronze e silver **preservam o valor
  como veio** (a Base dos Dados costuma publicar em **R$ 1.000**/milhares); a
  **unidade é registrada em [`fontes-ibge.md`](fontes-ibge.md)** na 1ª extração.
  A **conversão/per capita é só na gold**, com comentário explícito. A silver
  **não converte**.
- **Critério de aceite de sanidade (D9):** o PIB de **São Paulo
  (`id_municipio = 3550308`) em 2021** deve ser compatível com **≈ R$ 828,98
  bilhões** — `≈ 828.980.000.000` se a unidade for **reais**, ou `≈ 828.980.000`
  se for **milhares de reais**. O valor ingerido deve bater com uma das duas
  leituras; a leitura correta fixa a unidade registrada em `fontes-ibge.md`.

### 5.3 `silver.ibge_dtb_municipio`

| Coluna silver | Origem (bronze) | Tipo | Observação |
|---|---|---|---|
| `id_municipio` | código do município | `VARCHAR` | 7 dígitos |
| `sigla_uf` | UF | `VARCHAR` | 2 letras maiúsculas |
| `nome_municipio` | nome | `VARCHAR` | rótulo descritivo (não é chave) |
| `nome_regiao` | região/macrorregião | `VARCHAR` | uma de 5 regiões |

- **Pré-validação (regex):** `id_municipio` `^[0-9]{7}$`; `sigla_uf` `^[A-Z]{2}$`;
  `nome_regiao` ∈ {Norte, Nordeste, Sudeste, Sul, Centro-Oeste} (**lista a
  confirmar** conforme a grafia da fonte — com ou sem acento/hífen).
- **Coerência de prefixo:** os 2 primeiros dígitos de `id_municipio` devem
  corresponder ao código da `sigla_uf` (tabela de 27 códigos de UF do IBGE).
  Divergência é **alerta** (seção 5.4), não bloqueante, porque a fonte é a
  autoridade territorial.
- **Linhas esperadas:** ~5.570 municípios da DTB 2025 (**número exato a confirmar
  na extração**, seção 10).

### 5.4 Alertas (modelo A1–A4 do SNIS)

Três níveis, como no SNIS: **bloqueante** (`ROLLBACK` + `sys.exit(1)`),
**alerta** (passa, conta e reporta) e **informação** (só conta).

**Bloqueantes (comuns às três silvers):**

| # | Condição |
|---|---|
| IB1 | tabela bronze correspondente ausente |
| IB2 | valor que **não casa a regex** de pré-validação da coluna (antes do `CAST`) |
| IB3 | valor que **não converte** para o tipo-alvo, ou **fora da faixa** do tipo |
| IB4 | valor `DECIMAL` com **mais de 2 casas** no texto (só IBGE-PIB; regra B4) |
| IB5 | `id_municipio` fora de `^[0-9]{7}$` |
| IB6 | chave do grão **nula ou repetida** (`(ano, id_municipio)` para POP/PIB; `id_municipio` para DTB) |
| IB7 | contagem de **linhas/colunas** diferente da bronze |
| IB8 | valor **vazio (`''`) ou só espaços** em qualquer coluna (quebra do contrato da bronze) |

**Alertas não bloqueantes (fatos conhecidos; preservar o dado, imprimir
contagem):**

| # | Alerta | Fonte |
|---|---|---|
| IA1 | `ano` fora da **janela analítica 2010–2021** (série completa é mantida; só marcado) | POP, PIB |
| IA2 | anos com **PIB retropolado** (2002–2009) | PIB |
| IA3 | prefixo de `id_municipio` divergente da `sigla_uf` | DTB |
| IA4 | municípios da DTB **sem par** na silver SNIS, e vice-versa (alimenta a seção 8) | DTB/todas |
| IA5 | **revisão de série de população** — diferença entre o valor ingerido de São Paulo (3550308) em 2021 e a referência IBGE **12.396.372** (seção 5.1); registrada no relatório | POP |

> **Informação (só contar):** nulos por coluna, como no SNIS. Nenhum nulo é
> preenchido.

**Regras transversais (iguais ao SNIS):** `CREATE SCHEMA IF NOT EXISTS silver`;
`CREATE OR REPLACE TABLE` em transação única; bronze nunca é alterada;
`data/raw/` nunca é tocado; sem colunas de auditoria; idempotente.

---

## 6. Janela temporal

- **Bronze e silver carregam a série completa** de cada fonte (POP 1991–2025;
  PIB 2002–2021; DTB fotografia 2025). Nada é cortado na ingestão.
- O recorte para **2010–2021 acontece só nos marts** (janela analítica do
  catálogo, limitada pela série do PIB). Um `ano` fora dessa janela gera o
  alerta **IA1**, não um bloqueio.
- **D2:** 2021 é o ano de referência dos marts urbanos; **nenhum mart urbano usa
  2022**. Como o PIB vai só até 2021 e a série urbana do SNIS é nula em 2022,
  os marts 9 e 10 fecham naturalmente em 2010–2021.

### 6.1 Notas obrigatórias do PIB

- **Retropolação 2002–2009:** esses anos foram recalculados para a série nova e
  ficam marcados por **IA2**. Dentro da janela do projeto (2010–2021) não há
  retropolação.
- **2024 sem publicação regular:** não houve divulgação em 2024 por mudança de
  ano-base das Contas Nacionais; não afeta a janela 2010–2021, mas fica
  registrado.
- **Valores nominais:** o PIB só pode ser comparado **dentro do mesmo ano**. A
  silver não deflaciona; a gold carrega a flag `valor_nominal = true`.

---

## 7. Teste de cobertura de junção com o SNIS

Antes de qualquer `JOIN` nos marts (convenção do catálogo), medir quanto de
`silver.municipio_agua_esgoto` casa com cada fonte IBGE. É um **teste**, não uma
correção: nenhum município é editado (D6).

### 7.1 O que medir

Para cada fonte e **por ano** (POP e PIB) ou no total (DTB):

1. quantos `id_municipio` distintos da silver SNIS **casam** com a fonte IBGE;
2. a **taxa de cobertura** = casados / distintos do SNIS no ano;
3. a **lista de divergências** — `id_municipio` do SNIS sem par no IBGE (e, para
   a DTB, o inverso também), gravada como saída do teste.

### 7.2 Divergências esperadas (D6)

Os **31 municípios de ano único** da silver SNIS (**12 entrantes em 2022** +
**19 de meio de série**) entram como divergências **esperadas**, sem correção
manual. Seus nomes, emancipações e fusões ficam **"a confirmar na ingestão da
DTB"**. O teste os **conta e lista**, mas eles **não** reprovam o critério.

### 7.3 Critério de aceite numérico

- **DTB (cobertura cadastral):** todos os `id_municipio` da silver SNIS, **exceto
  os 31 de ano único**, devem casar com a DTB 2025. Ou seja, divergências
  SNIS→DTB **≤ 31** e **todas** dentro da lista conhecida → **passa**.
  Divergência fora dessa lista → **bloqueante** (indica erro de extração ou de
  formato, não vigência).
- **POP / PIB (cobertura por ano, dentro de 2010–2021):** cobertura mínima
  **≥ 99%** dos municípios informantes do SNIS em cada ano da janela. Abaixo de
  99% → **alerta** que exige inspeção manual (não bloqueia a carga), porque a
  causa provável é vigência/retropolação, não erro de formato; registrar a
  lista. Cobertura **< 95%** em qualquer ano da janela → **bloqueante** (sinal
  de id_municipio desalinhado entre as fontes).

> **Justificativa dos limiares:** o formato de `id_municipio` já é garantido na
> silver (7 dígitos, IB5), então uma queda grande de cobertura só pode vir de
> fonte errada ou coluna trocada — daí o corte duro em 95%. A faixa 95–99%
> absorve emancipações/vigência (D6) como alerta inspecionável.

---

## 8. Executor (`executar.py`)

As fontes IBGE entram **depois** do SNIS, na ordem:

1. SNIS bronze (`bronze.municipio_agua_esgoto`)
2. SNIS silver (`silver.municipio_agua_esgoto`)
3. **IBGE bronze** (`bronze.ibge_populacao_municipio`, `bronze.ibge_pib_municipio`,
   `bronze.ibge_dtb_municipio`)
4. **IBGE silver** (`silver.ibge_populacao_municipio`, `silver.ibge_pib_municipio`,
   `silver.ibge_dtb_municipio`)
5. **Teste de cobertura de junção** (seção 7), que exige SNIS silver + IBGE
   silver prontos.

Cada etapa abre e fecha a própria conexão (sem conexão global, como no SNIS). A
silver do IBGE depende da bronze do IBGE; o teste de cobertura depende das duas
silvers.

**Nomenclatura dos testes novos** (estilo de `tests/test_silver.py`):

- `tests/test_ibge_bronze.py` — espelho fiel das três bronzes (linhas/colunas vs.
  MANIFEST, tudo `VARCHAR`, idempotência).
- `tests/test_ibge_silver.py` — tipos, renomeações, regex, faixas, chaves únicas,
  `id_municipio` 7 dígitos, alertas IA1–IA5, as sanidades de São Paulo (P7, B8),
  e o **critério de cobertura** da seção 7.

---

## 9. Critérios de aceite numéricos por tabela

### 9.1 `ibge_populacao_municipio`

| # | Critério | Como verificar |
|---|---|---|
| P1 | linhas bronze = linhas silver = MANIFEST | `count(*)` igual nos três |
| P2 | tipos | `ano` INTEGER, `id_municipio` VARCHAR, `populacao_total_ibge` INTEGER |
| P3 | chave única | 0 duplicatas e 0 nulos em `(ano, id_municipio)` |
| P4 | `id_municipio` | 100% casa `^[0-9]{7}$` |
| P5 | faixa | `min(ano) ≥ 1991`, `max(ano) ≤ 2025`, `populacao_total_ibge ≥ 0` |
| P6 | soma preservada | `sum(populacao)` da bronze (via `TRY_CAST`) = `sum(populacao_total_ibge)` da silver |
| P7 | sanidade de série (não bloqueante) | São Paulo (3550308) em 2021 comparado a **12.396.372**; diferença registrada no relatório (IA5) |

### 9.2 `ibge_pib_municipio`

| # | Critério | Como verificar |
|---|---|---|
| B1 | linhas bronze = silver = MANIFEST | `count(*)` |
| B2 | tipos | `ano` INTEGER, `id_municipio` VARCHAR, `pib_municipio` DECIMAL(18,2) |
| B3 | chave única | 0 duplicatas/nulos em `(ano, id_municipio)` |
| B4 | `id_municipio` 7 dígitos | 100% `^[0-9]{7}$` |
| B5 | faixa | `min(ano) ≥ 2002`, `max(ano) ≤ 2021`, `pib_municipio ≥ 0` |
| B6 | soma preservada | `sum(CAST(pib AS DECIMAL(38,6)))` igual em bronze e silver |
| B7 | sem perda de casas | 0 linhas com `> 2` casas decimais no texto da bronze |
| B8 | sanidade de unidade (D9) | São Paulo (3550308) em 2021 ≈ **R$ 828,98 bi** (≈ `828.980.000.000` em reais ou `828.980.000` em milhares); fixa a unidade registrada em `fontes-ibge.md` |

### 9.3 `ibge_dtb_municipio`

| # | Critério | Como verificar |
|---|---|---|
| D1 | linhas = MANIFEST (~5.570, **exato a confirmar**) | `count(*)` |
| D2 | chave única | 0 duplicatas/nulos em `id_municipio` |
| D3 | `id_municipio` 7 dígitos | 100% `^[0-9]{7}$` |
| D4 | UF válida | `sigla_uf` ∈ as 27 UFs; `count(DISTINCT sigla_uf) = 27` |
| D5 | região válida | `nome_regiao` ∈ as 5 regiões |
| D6 | cobertura SNIS→DTB | divergências ≤ 31 e todas na lista de ano único (seção 7.3) |

---

## 10. Suposições e pontos "a confirmar"

As quatro grandes decisões desta spec foram **fechadas em D7–D10** (ver
[`decisoes.md`](decisoes.md)). Ficam **a confirmar na 1ª extração**:

1. **Nomes de tabela/coluna na Base dos Dados** — `br_ibge_populacao.municipio`
   (coluna de população), dataset/tabela do PIB (`br_ibge_pib.municipio`?) e,
   **só se usar a alternativa** (D8), o diretório de municípios da DTB. **A
   confirmar no BigQuery.**
2. **Unidade do PIB** — reais ou milhares? Mantida como na fonte (D9) e
   **registrada em `fontes-ibge.md`**; a sanidade de São Paulo (B8) decide qual é.
3. **Nomes de coluna do relatório oficial da DTB 2025** (código do município, UF,
   macrorregião, nome). **A confirmar na extração.**
4. **Grafia de `nome_regiao`** — com acento/hífen ("Centro-Oeste" vs.
   "Centro Oeste") conforme a fonte. **A confirmar na extração.**
5. **Nº exato de municípios da DTB 2025** (~5.570). **A confirmar na extração.**
6. **Encoding do arquivo oficial do IBGE** — provavelmente `latin-1`; converter
   para utf-8 no passo de conversão (D8).
7. **Semântica de `populacao` do IBGE-POP** — é a população residente **total**
   (urbana + rural)? É o denominador dos marts 6–8. **A confirmar.**
8. **Faixas de porte (mart 6)** — definidas pela população IBGE; os cortes são
   decisão da gold, não desta spec.

---

## 11. Decisões aplicadas (D7–D10, APROVADAS em 2026-11-08)

Esta spec já incorpora as decisões abaixo; não há mais escolhas pendentes com você.

- **D7 — limiares de cobertura (provisórios):** por ano, **alerta < 99%**,
  **bloqueante < 95%**; DTB **≤ 31 divergências**. **Revisar após a 1ª medição
  real** e registrar o valor final em `decisoes.md` (seção 7.3).
- **D8 — DTB pelo arquivo oficial do IBGE** (relatório de municípios DTB 2025),
  original preservado em `data/raw/ibge/dtb/` e conversão para CSV documentada à
  parte; Base dos Dados só como alternativa com versão documentada (seção 3.3).
- **D9 — unidade do PIB como na fonte**, registrada em `fontes-ibge.md`;
  conversão só na gold. Sanidade: São Paulo 2021 ≈ R$ 828,98 bi (B8).
- **D10 — coluna de população = `populacao_total_ibge`** (seções 5.1 e 9.1).

### Pendência a reabrir depois
- **D7 provisória:** depois da primeira medição real de cobertura, revisar os
  limiares e registrar os números definitivos.

---

## 12. Passo a passo: o que baixar, onde salvar e com que nome

`<data>` = data da extração no formato `AAAA-MM-DD` (a mesma em todos os
arquivos de uma rodada). Nunca editar nada dentro de `data/raw/` depois de salvo.

### 12.1 IBGE-POP (população)
1. Exportar a série completa da Base dos Dados (`br_ibge_populacao.municipio`)
   como CSV.
2. Salvar em: `data/raw/ibge/populacao/<data>/`
   - arquivo: **`populacao_municipio.csv`**
   - manifesto: **`MANIFEST.md`** (origem, URL/consulta, data, nº de linhas,
     nº de colunas, checksum `sha256`).

### 12.2 IBGE-PIB
1. Exportar a série 2002–2021 da Base dos Dados (`br_ibge_pib.municipio`) como CSV.
2. Salvar em: `data/raw/ibge/pib/<data>/`
   - arquivo: **`pib_municipio.csv`**
   - manifesto: **`MANIFEST.md`** (inclua a **unidade do PIB** encontrada —
     reais ou milhares — conferida pela sanidade de São Paulo, D9/B8).

### 12.3 IBGE-DTB 2025 (arquivo oficial, D8)
1. Baixar o **relatório de municípios da DTB 2025** do site do IBGE
   (`.../divisao-territorial-brasileira.html`). **Preservar o original** sem
   alterar.
2. Salvar o original em: `data/raw/ibge/dtb/<data>/`
   - arquivo original: **mantido com o nome/extensão de origem** (ex.
     `RELATORIO_DTB_BRASIL_2025_MUNICIPIOS.xls` ou o `.zip` baixado).
3. **Converter para CSV como passo separado** (documentar no MANIFEST a
   ferramenta, a aba, o encoding e as colunas) e salvar na **mesma pasta**:
   - CSV convertido: **`dtb_municipio.csv`**
   - manifesto: **`MANIFEST.md`** (origem = IBGE DTB 2025, URL, data, versão
     2025, nº de linhas, checksum do original **e** do CSV, passos da conversão).

### 12.4 Checklist de MANIFEST (as três pastas)
Cada `MANIFEST.md` deve trazer: **origem/URL**, **data de extração**, **nº de
linhas**, **nº de colunas**, **checksum (`sha256`)** — são esses números que
alimentam os critérios de aceite de linhas/colunas (seções 4 e 9). Para o PIB,
registrar a **unidade**; para a DTB, registrar a **versão (2025)** e os **passos
da conversão**.
