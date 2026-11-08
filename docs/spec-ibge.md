# Spec da ingestão e transformação do IBGE (bronze → silver)

| | |
|---|---|
| **Status** | aprovada (D7–D17 em 2026-11-08); D7 provisória, revisar após 1ª medição |
| **Versão** | 2 (ajustada aos arquivos reais baixados em 2026-11-08) |
| **Data** | 2026-11-08 |
| **Responsável** | Luiz |
| **Banco** | `snis.duckdb` (o mesmo do SNIS) · schemas `bronze` e `silver` |
| **Fontes** | IBGE-POP, IBGE-DTB, IBGE-PIB (ver [`fontes-ibge.md`](fontes-ibge.md)) |

> **Referências de leitura obrigatória:** catálogo [`fontes-ibge.md`](fontes-ibge.md);
> fórmulas e uso nos marts [`indicadores.md`](indicadores.md); decisões
> **D1–D17 APROVADAS em 2026-11-08** [`decisoes.md`](decisoes.md); specs-modelo
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
| IBGE-POP | `silver.ibge_populacao_municipio` | população residente total (urbana + rural, ref. 1º/jul; D14) do município por ano | **6, 7, 8, 9, 10** |
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
| IBGE-POP | município × ano | `(ano, id_municipio)` | 0 duplicatas na chave; **`populacao` nula é permitida** (fatos conhecidos, D13); **1 linha sem `id_municipio`** (ano 2025) é excluída da silver (D13) |
| IBGE-PIB | município × ano | `(ano, id_municipio)` | 0 duplicatas, 0 nulos na chave; **`valor` pode ser símbolo de ausência** do SIDRA (vira NULL, D11) |
| IBGE-DTB | município (fotografia de **2025**, D6) | `id_municipio` | 0 duplicatas, 0 nulos; **5.571 linhas** (5.570 instalados + 1 criado e ainda sem população, D12) |

`id_municipio` sempre com **7 dígitos, como texto**, preservando zeros à esquerda
(os 2 primeiros dígitos são o código da UF). Medido na extração de 2026-11-08: na
população, **todos** os `id_municipio` não vazios têm 7 dígitos; há **1** registro
de `id_municipio` vazio (ano 2025, população 5.877).

---

## 3. Origem dos arquivos e como obtê-los

**Convenção de pasta** (do catálogo): cada extração vai para
`data/raw/ibge/<fonte>/AAAA-MM-DD/`, com um `MANIFEST.md` contendo
**origem, data de extração, nº de linhas e checksum** (ex.: `sha256`) de cada
arquivo. `<fonte>` ∈ `{populacao, pib, dtb}`. **A extração atual é a de
`2026-11-08`** — todas as três fontes estão em
`data/raw/ibge/<fonte>/2026-11-08/`. Nada em `data/raw/` é editado depois de
gravado.

> O MANIFEST é a âncora dos critérios de aceite: a bronze valida linhas e
> colunas **contra os números do MANIFEST** da extração usada (seção 4).

### 3.1 IBGE-POP — via Base dos Dados (BigQuery) — **baixado em 2026-11-08**

Exportado pelo **console do BigQuery** (tabela `br_ibge_populacao.municipio`) e
salvo como CSV em `data/raw/ibge/populacao/2026-11-08/populacao_municipio.csv`.
Ver [`fontes-ibge.md`](fontes-ibge.md) e o
[`MANIFEST.md`](../data/raw/ibge/populacao/2026-11-08/MANIFEST.md) da pasta.

Consulta usada (nomes de coluna **confirmados** na extração):

```sql
SELECT ano, id_municipio, populacao
FROM `basedosdados.br_ibge_populacao.municipio`
ORDER BY ano, id_municipio;
```

**Layout real do CSV** (3 colunas, UTF-8, vírgula, com cabeçalho):
`ano`, `id_municipio`, `populacao`.

**Medições da extração (confirmadas em 2026-11-08):** 191.099 linhas de dados;
anos **1991–2025**; **5.570** municípios/ano em 2012–2025 e **5.565** em 2010–2011;
**0** duplicatas na chave `(ano, id_municipio)`; **534** populações nulas (**533**
em 1996, **1** em 2009, **nenhuma** em 2010–2021); **1** linha sem `id_municipio`
(ano 2025, população 5.877). `sha256` e detalhe no MANIFEST.

Carregar a **série completa** (1991–2025). As peculiaridades acima (nulos e linha
sem id) são **fatos conhecidos** tratados na silver por D13 (seção 5.1), não
erros de extração.

### 3.2 IBGE-PIB — via API do SIDRA, tabela 5938 (D11) — **baixado em 2026-11-08**

**Fonte real: API pública do SIDRA (`apisidra`), tabela 5938** ("Produto interno
bruto a preços correntes — Referência 2010"). **A Base dos Dados não foi usada**
(D11; motivo: a tabela da Base dos Dados não foi confirmada). Salvo em
`data/raw/ibge/pib/2026-11-08/`; ver o
[`MANIFEST.md`](../data/raw/ibge/pib/2026-11-08/MANIFEST.md).

- **Variável `37`** — "Produto Interno Bruto a preços correntes" (código
  confirmado na API de metadados, não de memória).
- **Unidade: Mil Reais** (código de unidade `40`).
- **Nível territorial:** município (`n6`), todos (`all`).
- **Anos baixados: 2010–2021** (12 anos) — cobre exatamente a janela do projeto.

URLs usadas (baixado **ano a ano** para evitar recusa por excesso de células):

```
Metadados: https://servicodados.ibge.gov.br/api/v3/agregados/5938/metadados
Valores:   https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/<ANO>
```

**Arquivos na pasta (2026-11-08):**

- `pib_5938_<ANO>.json` — **12 parciais** (2010…2021), resposta bruta do SIDRA,
  preservados.
- `pib_municipio.csv` — CSV montado a partir dos 12 JSON (passo documentado no
  MANIFEST), **66.840 linhas** (5.570 municípios × 12 anos).

**Layout do JSON bruto do SIDRA** (lista de objetos; o **1º objeto é o
dicionário de rótulos** e é descartado na montagem): campos
`NC`, `NN`, `MC`, `MN` (= "Mil Reais"), `V` (valor), `D1C` (município, 7 díg.),
`D1N` (nome), `D2C` (= "37"), `D2N` (variável), `D3C`/`D3N` (ano). A montagem
mapeia `D1C→id_municipio`, `D1N→nome_municipio`, `D3C→ano`, `D2N→variavel`,
`MN→unidade`, `V→valor`.

**Layout do CSV montado `pib_municipio.csv`** (6 colunas, UTF-8, vírgula, com
cabeçalho):
`id_municipio`, `nome_municipio`, `ano`, `variavel`, `unidade`, `valor`.
`valor` é **inteiro em Mil Reais** (valor nominal, comparar só no mesmo ano);
`nome_municipio` vem no formato `"Nome - UF"` (ex.: `São Paulo - SP`).

**Símbolos de ausência do SIDRA:** o valor `V` pode trazer símbolos em vez de
número. Os símbolos do padrão SIDRA são **`-`** (zero absoluto), **`..`** (não
se aplica), **`...`** (dado não disponível) e **`X`** (omitido para não
identificar o informante). **Medido nesta extração:** o **único** símbolo que
aparece é **`...`**, em **15** células (5 municípios × 3 anos: 2010, 2011 e
2012 — Mojuí dos Campos/PA, Pescaria Brava/SC, Balneário Rincão/SC, Pinto
Bandeira/RS e Paraíso das Águas/MS, municípios instalados depois de 2012). O CSV
montado preserva o símbolo `...` literal nessas linhas; o tratamento é na silver
(seção 5.2, D11).

### 3.3 IBGE-DTB 2025 (D6, D8)

**Fonte principal (D8) — arquivo oficial do IBGE — baixado em 2026-11-08:** o
**relatório de municípios da DTB 2025**, baixado como `DTB_2025.zip` do servidor
`geoftp.ibge.gov.br` (a página oficial retornou HTTP 403 na coleta automatizada).
Procedimento realizado:

1. **Original preservado** em `data/raw/ibge/dtb/2026-11-08/DTB_2025.zip` (zip
   íntegro com 8 planilhas, somente leitura).
2. **Convertido para CSV** como passo separado e documentado (pandas + engine
   `xlrd`, aba única `DTB_Municípios`, cabeçalho na 7ª linha, encoding UTF-8),
   salvo ao lado como `dtb_municipio.csv`. Detalhe no
   [`MANIFEST.md`](../data/raw/ibge/dtb/2026-11-08/MANIFEST.md).

**Layout real do `dtb_municipio.csv`** (9 colunas, UTF-8, vírgula, com
cabeçalho; **5.571 linhas** de dados):
`UF`, `Nome_UF`, `Região Geográfica Intermediária`,
`Nome Região Geográfica Intermediária`, `Região Geográfica Imediata`,
`Nome Região Geográfica Imediata`, `Município`, `Código Município Completo`,
`Nome_Município`.

- `UF` é o **código numérico** de 2 dígitos (ex.: `35` = São Paulo); **não há
  coluna de sigla da UF** (ver seção 5.3 para como obtê-la).
- `Código Município Completo` é o `id_municipio` de **7 dígitos** (texto, com
  zeros à esquerda).
- A DTB traz **região intermediária** e **região imediata** (divisão regional de
  2017), **não** a macrorregião (Norte/Nordeste/…). A macrorregião é derivada do
  código da UF na silver (seção 5.3).

**Linha extra — 5.571 vs. 5.570 municípios (D12):** o esperado são 5.570
municípios instalados, mas o relatório traz 5.571 linhas. A linha extra foi
identificada consultando o CSV: é **`5101837` — Boa Esperança do Norte (MT)**,
único `id_municipio` da DTB que **não** aparece na estimativa de população de
2025 (que tem 5.570 municípios). **Não** é duplicata (0 códigos repetidos),
cabeçalho nem código especial: é um **município novo**, criado por lei estadual
de MT e **presente na base territorial 2025, mas ainda sem população estimada**
pelo IBGE. Portanto o critério de aceite correto da DTB é **5.571 linhas**
(seção 9.3, D12), não 5.570.

A **versão é 2025** (D6, DATA BASE 31/12/2025) e consta no MANIFEST.

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
| `populacao_total_ibge` | `populacao` | `INTEGER` | nome usado nas fórmulas dos marts (D10); **população residente total (urbana + rural), referência 1º de julho (D14)** — **não** é a `populacao_urbana` do SNIS; inteiro, máx. ~12,4 mi cabe em `INTEGER`; **pode ser NULL** (fatos conhecidos, D13) |

- **Exclusão da linha sem `id_municipio` (D13):** a linha com `id_municipio`
  vazio (medida: 1 linha, ano 2025, população 5.877) é **excluída** da silver,
  com **alerta não bloqueante** que a **lista** (IA6). A exclusão só é permitida
  se o `ano` dessa linha estiver **fora de 2010–2021**; uma linha sem
  `id_municipio` **dentro** da janela é **bloqueante** (IB9). A bronze mantém a
  linha (espelho fiel).
- **Pré-validação (regex, antes do CAST), já sem a linha excluída:** `ano` casa
  `^[0-9]{4}$`; `id_municipio` casa `^[0-9]{7}$`; `populacao` casa `^[0-9]+$`
  (inteiro não negativo, sem decimais) **ou é vazio/NULL** — população nula é
  **permitida** (ver abaixo), não reprova a regex.
- **População nula (D13, alerta não bloqueante IA7):** `populacao` nula é
  aceita; conta-se por ano. O esperado é **533 em 1996 e 1 em 2009** (nenhuma em
  2010–2021). **Qualquer** população nula em **2010–2021** é **bloqueante**
  (IB10), porque a janela analítica não admite buraco.
- **Faixas válidas:** `ano` em 1991–2025; `populacao_total_ibge` ≥ 0 (quando não
  nula) e abaixo do teto de `INTEGER` (maior município < 2,1 bi, folga ampla).
- **Checagem de revisão de série (não bloqueante, IA5):** comparar o valor
  ingerido de **São Paulo (`id_municipio = 3550308`) em 2021** com a referência
  IBGE de **12.396.372 habitantes**. A diferença (absoluta e %) é **registrada no
  relatório da execução**; não bloqueia (a série pode ser revisada entre
  publicações), mas um desvio grande sinaliza fonte ou ano trocados.
  **Medido em 2026-11-08:** SP 2021 = **12.396.372** (diferença **0**); SP 2010 =
  **11.253.503** e SP 2022 = **11.451.999** (Censo 2022, repetido em 2023) — batem.
- **Quebra de série 2021 → 2022 (ressalva, não bloqueante):** a população de SP
  cai de 12.396.372 (estimativa 2021) para 11.451.999 (Censo 2022). É mudança de
  método (estimativa → Censo), registrada como **ressalva no catálogo**
  [`fontes-ibge.md`](fontes-ibge.md) e em **D13**. **A janela 2010–2021 não é
  afetada** (usa só valores pré-Censo 2022).

### 5.2 `silver.ibge_pib_municipio`

A bronze reflete o **CSV montado `pib_municipio.csv`** (seção 3.2): 6 colunas,
`valor` em **Mil Reais** e com o símbolo `...` preservado nas 15 linhas de
ausência. A silver tipa e trata os símbolos:

| Coluna silver | Origem (bronze) | Tipo | Observação |
|---|---|---|---|
| `ano` | `ano` | `INTEGER` | 4 dígitos |
| `id_municipio` | `id_municipio` | `VARCHAR` | 7 dígitos (campo `D1C` do SIDRA) |
| `pib_municipio` | `valor` | `BIGINT` | **inteiro em Mil Reais** (variável 37, unidade 40); valor nominal; **pode ser NULL** quando a fonte traz símbolo de ausência (D11). **`BIGINT`, nunca `DECIMAL` (D15):** o SIDRA entrega inteiro em Mil Reais; a conversão para reais é só na gold |

- **Pré-validação (regex, antes do CAST):** `ano` `^[0-9]{4}$`;
  `id_municipio` `^[0-9]{7}$`; `valor` casa **`^-?[0-9]+$`** (inteiro em Mil
  Reais **com sinal** — o SIDRA entrega o PIB em Mil Reais como inteiro, que
  **pode ser negativo**, D17) **ou** é um **símbolo de ausência** do SIDRA ∈
  **{`-`, `..`, `...`, `X`}**.
- **PIB negativo (D17, alerta IA9):** o PIB municipal **pode ser negativo**
  (impostos sobre produtos líquidos de subsídios negativos). O valor é
  **preservado** (`BIGINT` aceita sinal); **IA9** lista cada negativo
  `(id_municipio, ano, valor)`. **Constante nomeada `PIB_NEGATIVOS_MAX = 5`:** se
  o número de negativos **passar de 5**, **IA9 vira bloqueante** (proteção contra
  erro de leitura ou de sinal). **Medido:** 1 caso — **Guamaré/RN (`2404507`),
  2012 = −19.046 Mil Reais**.
- **Tratamento dos símbolos (D11, alerta não bloqueante IA8):** `valor` igual a
  um dos símbolos de ausência vira **NULL**; conta-se por ano. **Medido:** só
  `...`, 15 células (2010/2011/2012, 5 municípios novos). Um `valor` que **não é
  inteiro nem símbolo conhecido** (ex.: texto, decimal, símbolo fora da lista) é
  **inválido → bloqueante (IB11)**: distingue ausência legítima de erro de
  formato/extração.
- **Faixas válidas (B5, D17):** `ano` em **2010–2021** (anos realmente baixados,
  D11); **`pib_municipio` ≥ 0, exceto os negativos reais do SIDRA listados em
  IA9**. `BIGINT` comporta o maior PIB municipal em Mil Reais com folga (SP 2021 =
  828.980.747) e também valores negativos.
- **Unidade mantida como na fonte (D9/D11/D15):** **Mil Reais**, preservada em
  bronze e silver (**`BIGINT`, sem `DECIMAL`**) e registrada em
  [`fontes-ibge.md`](fontes-ibge.md). A **conversão para reais / per capita é só
  na gold**, com **comentário explícito** no código da gold. A silver **não
  converte**.
- **Critério de aceite de sanidade (D9/D11):** o PIB de **São Paulo
  (`id_municipio = 3550308`) em 2021** = **828.980.747 Mil Reais** = **≈ R$ 828,98
  bilhões**, compatível com a referência. Confirma a unidade **Mil Reais**.

### 5.3 `silver.ibge_dtb_municipio`

**Layout real da bronze** (9 colunas, seção 3.3). A silver seleciona e renomeia:

| Coluna silver | Origem (bronze) | Tipo | Observação |
|---|---|---|---|
| `id_municipio` | `Código Município Completo` | `VARCHAR` | 7 dígitos (chave) |
| `cod_uf` | `UF` | `VARCHAR` | código numérico de 2 dígitos (ex.: `35`) |
| `sigla_uf` | **derivada** de `UF` | `VARCHAR` | 2 letras maiúsculas (ver abaixo) |
| `nome_uf` | `Nome_UF` | `VARCHAR` | ex.: `São Paulo` |
| `nome_municipio` | `Nome_Município` | `VARCHAR` | rótulo descritivo (não é chave) |
| `cod_regiao_intermediaria` | `Região Geográfica Intermediária` | `VARCHAR` | código |
| `nome_regiao_intermediaria` | `Nome Região Geográfica Intermediária` | `VARCHAR` | rótulo |
| `cod_regiao_imediata` | `Região Geográfica Imediata` | `VARCHAR` | código |
| `nome_regiao_imediata` | `Nome Região Geográfica Imediata` | `VARCHAR` | rótulo |
| `nome_regiao` | **derivada** do `cod_uf` | `VARCHAR` | macrorregião (uma de 5) |

- **`sigla_uf` não existe no arquivo** (a DTB só traz o **código** da UF e o
  `Nome_UF`). **Proposta (sem inventar):** derivar a sigla por um **mapa estático
  dos 27 códigos de UF do IBGE** → sigla (11→RO, 12→AC, …, 35→SP, …, 53→DF),
  embutido na silver como tabela de-para auditável. Alternativa equivalente:
  mapear a partir de `Nome_UF` (27 nomes oficiais → sigla). **Nenhuma sigla é
  adivinhada por município**: vem só do código/nome da UF, que a fonte garante.
- **`nome_regiao` (macrorregião)** também **não** está no arquivo (a DTB traz
  região **intermediária** e **imediata**, não Norte/Nordeste/…). Deriva-se do
  **1º dígito do `cod_uf`** (1→Norte, 2→Nordeste, 3→Sudeste, 4→Sul, 5→Centro-
  Oeste), no mesmo mapa estático das UFs.
- **Colunas que a gold usará:** `id_municipio`, **`sigla_uf`** (ou `nome_uf`) e
  **`nome_regiao`** (macrorregião) — é o que os marts por UF/região pedem
  ([`fontes-ibge.md`](fontes-ibge.md)). As regiões intermediária/imediata ficam
  disponíveis, mas nenhum mart atual as usa.
- **Pré-validação (regex):** `id_municipio` `^[0-9]{7}$`; `cod_uf` `^[0-9]{2}$`;
  `sigla_uf` `^[A-Z]{2}$`; `nome_regiao` ∈ {Norte, Nordeste, Sudeste, Sul,
  Centro-Oeste} (grafia do mapa estático, com hífen em "Centro-Oeste").
- **Coerência de prefixo:** os 2 primeiros dígitos de `id_municipio` devem bater
  com o `cod_uf` da linha. Divergência é **alerta** (IA3), não bloqueante.
- **Linhas esperadas: 5.571** (DTB 2025, D12) — 5.570 municípios instalados + 1
  criado e ainda sem população (Boa Esperança do Norte/MT, `5101837`). Ver 9.3.

### 5.4 Alertas (modelo A1–A4 do SNIS)

Três níveis, como no SNIS: **bloqueante** (`ROLLBACK` + `sys.exit(1)`),
**alerta** (passa, conta e reporta) e **informação** (só conta).

**Bloqueantes (comuns às três silvers):**

| # | Condição |
|---|---|
| IB1 | tabela bronze correspondente ausente |
| IB2 | valor que **não casa a regex** de pré-validação da coluna (antes do `CAST`) |
| IB3 | valor que **não converte** para o tipo-alvo, ou **fora da faixa** do tipo |
| IB5 | `id_municipio` fora de `^[0-9]{7}$` (ressalva POP: a 1 linha de id vazio é **excluída** antes, não bloqueia — IA6/IB9) |
| IB6 | chave do grão **nula ou repetida** (`(ano, id_municipio)` para POP/PIB; `id_municipio` para DTB) |
| IB7 | contagem de **linhas/colunas** diferente da bronze |
| IB8 | valor **vazio (`''`) ou só espaços** em coluna obrigatória (quebra do contrato da bronze). **Exceções conhecidas (D13):** `populacao` nula (→ IA7/IB10) e `id_municipio` vazio na POP (→ IA6/IB9); `valor` do PIB com símbolo de ausência (→ IA8/IB11) |
| IB9 | **(POP, D13)** linha sem `id_municipio` cujo `ano` está **dentro de 2010–2021** (fora da janela é só IA6) |
| IB10 | **(POP, D13)** `populacao` nula em **2010–2021** (fora da janela é só IA7) |
| IB11 | **(PIB, D11/D17)** `valor` que **não é inteiro com sinal (`^-?[0-9]+$`) nem símbolo de ausência conhecido** {`-`,`..`,`...`,`X`} |

> **IB4 aposentada:** com o PIB do SIDRA em **Mil Reais inteiro** (seção 5.2),
> não há casas decimais a checar; a antiga regra B4/IB4 não se aplica a esta
> fonte.

**Alertas não bloqueantes (fatos conhecidos; preservar o dado, imprimir
contagem):**

| # | Alerta | Fonte |
|---|---|---|
| IA1 | `ano` fora da **janela analítica 2010–2021** (série completa é mantida; só marcado) | POP |
| IA3 | prefixo de `id_municipio` divergente do `cod_uf`/`sigla_uf` | DTB |
| IA4 | municípios da DTB **sem par** na silver SNIS, e vice-versa (alimenta a seção 8) | DTB/todas |
| IA5 | **revisão de série de população** — diferença entre o valor ingerido de São Paulo (3550308) em 2021 e a referência IBGE **12.396.372** (seção 5.1); registrada no relatório | POP |
| IA6 | **(D13)** linha sem `id_municipio` **excluída** da silver, **listada** (esperado: 1, ano 2025, pop. 5.877); só permitida fora de 2010–2021 (senão IB9) | POP |
| IA7 | **(D13)** `populacao` nula, **contada por ano** (esperado: 533 em 1996, 1 em 2009; qualquer uma em 2010–2021 vira IB10) | POP |
| IA8 | **(D11)** `valor` do PIB = símbolo de ausência → NULL, **contado por ano** (esperado: `...`, 15 células em 2010–2012) | PIB |
| IA9 | **(D17)** `pib_municipio` **negativo**, preservado e **listado** `(id_municipio, ano, valor)` (esperado: 1 — Guamaré/RN, 2012, −19.046 Mil Reais); **vira bloqueante se > `PIB_NEGATIVOS_MAX` (5)** | PIB |

> **IA2 aposentada:** a extração do PIB cobre **2010–2021** (D11), sem os anos
> retropolados 2002–2009; não há mais o que marcar.

> **Informação (só contar):** nulos por coluna, como no SNIS. Nenhum nulo é
> preenchido.

**Regras transversais (iguais ao SNIS):** `CREATE SCHEMA IF NOT EXISTS silver`;
`CREATE OR REPLACE TABLE` em transação única; bronze nunca é alterada;
`data/raw/` nunca é tocado; sem colunas de auditoria; idempotente.

---

## 6. Janela temporal

- **Bronze e silver carregam a série baixada** de cada fonte (POP **1991–2025**;
  PIB **2010–2021**; DTB fotografia **2025**). Nada é cortado na ingestão.
- O PIB foi baixado já **restrito a 2010–2021** (D11), coincidindo com a janela
  analítica. Só a POP tem anos fora da janela: um `ano` da POP fora de 2010–2021
  gera o alerta **IA1**, não um bloqueio.
- **D2:** 2021 é o ano de referência dos marts urbanos; **nenhum mart urbano usa
  2022**. Como o PIB vai só até 2021 e a série urbana do SNIS é nula em 2022,
  os marts 9 e 10 fecham naturalmente em 2010–2021.

### 6.1 Notas obrigatórias do PIB

- **Sem retropolação na extração:** a extração do PIB (SIDRA 5938, D11) começa em
  **2010**, então os anos retropolados 2002–2009 **não entram**; o antigo alerta
  IA2 foi aposentado (seção 5.4).
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

> **Limiares como constantes nomeadas (D7, provisório):** os cortes acima
> (**99%** de alerta, **95%** bloqueante e o **máximo de 31 divergências** da
> DTB) são **provisórios** e **devem ser constantes nomeadas no código** (ex.:
> `COBERTURA_ALERTA = 0.99`, `COBERTURA_BLOQUEIO = 0.95`,
> `DTB_MAX_DIVERGENCIAS = 31`), reunidas num único ponto e **fáceis de ajustar
> após a primeira medição real**. Proibido espalhar números mágicos pelo código.
> Revisar os valores depois da 1ª medição e registrar os definitivos em
> [`decisoes.md`](decisoes.md) (D7).

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
  `id_municipio` 7 dígitos, alertas IA1 e IA3–IA8, as sanidades de São Paulo
  (P7, B8), e o **critério de cobertura** da seção 7.

---

## 9. Critérios de aceite numéricos por tabela

### 9.1 `ibge_populacao_municipio`

| # | Critério | Como verificar |
|---|---|---|
| P1 | linhas | bronze = **191.099** (MANIFEST); silver = 191.099 − 1 (linha de id vazio excluída, IA6) = **191.098** |
| P2 | tipos | `ano` INTEGER, `id_municipio` VARCHAR, `populacao_total_ibge` INTEGER (aceita NULL) |
| P3 | chave única | 0 duplicatas em `(ano, id_municipio)`; 0 `id_municipio` nulos **após** excluir a linha de id vazio (IA6) |
| P4 | `id_municipio` | 100% casa `^[0-9]{7}$` (na silver, já sem a linha de id vazio) |
| P5 | faixa | `min(ano)=1991`, `max(ano)=2025`; `populacao_total_ibge ≥ 0` **quando não nula** |
| P6 | soma preservada | `sum(populacao)` da bronze (via `TRY_CAST`, ignorando nulos) = `sum(populacao_total_ibge)` da silver |
| P7 | sanidade de série (não bloqueante) | São Paulo (3550308) em 2021 = **12.396.372** (diferença 0, IA5); 2010 = 11.253.503; 2022 = 11.451.999 |
| P8 | nulos conhecidos (IA7) | `populacao` nula: **533 em 1996, 1 em 2009, 0 em 2010–2021** (qualquer nula em 2010–2021 → IB10) |
| P9 | linha sem id (IA6) | exatamente **1** linha de `id_municipio` vazio, ano **2025** (fora de 2010–2021), excluída e listada |

### 9.2 `ibge_pib_municipio`

| # | Critério | Como verificar |
|---|---|---|
| B1 | linhas bronze = silver = MANIFEST | `count(*)` = **66.840** (5.570 × 12) |
| B2 | tipos | `ano` INTEGER, `id_municipio` VARCHAR, `pib_municipio` BIGINT (aceita NULL) |
| B3 | chave única | 0 duplicatas/nulos em `(ano, id_municipio)` |
| B4 | `id_municipio` 7 dígitos | 100% `^[0-9]{7}$` |
| B5 | faixa | `min(ano)=2010`, `max(ano)=2021`; **`pib_municipio` ≥ 0, exceto os negativos reais do SIDRA listados em IA9** (D17) |
| B6 | soma preservada | `sum(TRY_CAST(valor AS BIGINT))` da bronze (ignorando símbolos) = `sum(pib_municipio)` da silver |
| B7 | símbolos de ausência (IA8) | `valor` = símbolo {`-`,`..`,`...`,`X`} → NULL; **esperado: `...`, 15 células em 2010–2012**; qualquer texto que não case `^-?[0-9]+$` nem seja símbolo → IB11 |
| B9 | PIB negativo (IA9, D17) | `pib_municipio` < 0 preservado e listado; **esperado: 1** (Guamaré/RN `2404507`, 2012, −19.046 Mil Reais); **> `PIB_NEGATIVOS_MAX` (5)** → bloqueante |
| B8 | sanidade de unidade (D9/D11) | São Paulo (3550308) em 2021 = **828.980.747 Mil Reais** ≈ **R$ 828,98 bi**; confirma a unidade **Mil Reais** em `fontes-ibge.md` |

### 9.3 `ibge_dtb_municipio`

| # | Critério | Como verificar |
|---|---|---|
| D1 | linhas = MANIFEST = **5.571** (D12) | `count(*)` = 5.571 (5.570 instalados + `5101837` Boa Esperança do Norte/MT, criado e sem população) |
| D2 | chave única | 0 duplicatas/nulos em `id_municipio` (medido: 0 códigos repetidos) |
| D3 | `id_municipio` 7 dígitos | 100% `^[0-9]{7}$` |
| D4 | UF válida | `cod_uf` ∈ os 27 códigos; `sigla_uf` derivada ∈ as 27 UFs; `count(DISTINCT sigla_uf)=27` |
| D5 | região válida | `nome_regiao` (derivada) ∈ as 5 macrorregiões |
| D6 | cobertura SNIS→DTB | divergências ≤ 31 e todas na lista de ano único (seção 7.3) |

---

## 10. Suposições e pontos "a confirmar"

As grandes decisões desta spec foram fechadas em **D7–D13** (ver
[`decisoes.md`](decisoes.md)). A extração de **2026-11-08** resolveu os pontos
antes em aberto:

**Resolvidos na extração de 2026-11-08:**

1. **Fonte/colunas da POP** — `br_ibge_populacao.municipio`, colunas `ano`,
   `id_municipio`, `populacao`. ✅ confirmado.
2. **Fonte e unidade do PIB** — **SIDRA 5938** via API `apisidra` (D11), variável
   37, unidade **Mil Reais**; a Base dos Dados não foi usada. ✅ confirmado.
3. **Colunas da DTB 2025** — 9 colunas (seção 3.3); não há sigla da UF nem
   macrorregião no arquivo (derivadas na silver, seção 5.3). ✅ confirmado.
4. **Grafia de `nome_regiao`** — a macrorregião é **derivada** (mapa estático),
   grafia **"Centro-Oeste"** com hífen. ✅ resolvido por derivação.
5. **Nº de municípios da DTB 2025** — **5.571** (D12), não ~5.570. ✅ confirmado.
6. **Encoding** — CSVs já gravados em **UTF-8** no passo de conversão/montagem. ✅.
7. **Semântica de `populacao` do IBGE-POP (D14)** — é a **população residente
   total (urbana + rural)**, referência **1º de julho**; **não** é a
   `populacao_urbana` do SNIS. Denominador dos marts 6–8. ✅ **fechado em D14.**
8. **Faixas de porte (mart 6) (D16)** — cortes definidos, **medidos pela
   população de 2021**: até 5 mil · 5 a 20 mil · 20 a 50 mil · 50 a 100 mil ·
   100 a 500 mil · acima de 500 mil habitantes. Regra da **gold** (não afeta esta
   ingestão). ✅ **fechado em D16.**

**Ainda a confirmar (não dependem da extração):** nenhum item em aberto nesta
spec; os pontos 7 e 8 foram fechados por D14 e D16.

---

## 11. Decisões aplicadas (D7–D17, APROVADAS em 2026-11-08)

Esta spec já incorpora as decisões abaixo; não há mais escolhas pendentes com você.

- **D7 — limiares de cobertura (provisórios):** por ano, **alerta < 99%**,
  **bloqueante < 95%**; DTB **≤ 31 divergências**. Devem ser **constantes
  nomeadas no código**, num só ponto, fáceis de ajustar (seção 7.3). **Revisar
  após a 1ª medição real** e registrar o valor final em `decisoes.md`.
- **D8 — DTB pelo arquivo oficial do IBGE** (relatório de municípios DTB 2025),
  original preservado em `data/raw/ibge/dtb/` e conversão para CSV documentada à
  parte; Base dos Dados só como alternativa com versão documentada (seção 3.3).
- **D9 — unidade do PIB como na fonte**, registrada em `fontes-ibge.md`;
  conversão só na gold. Sanidade: São Paulo 2021 ≈ R$ 828,98 bi (B8).
- **D10 — coluna de população = `populacao_total_ibge`** (seções 5.1 e 9.1).
- **D11 — PIB do SIDRA 5938 (API `apisidra`), em Mil Reais**, anos 2010–2021;
  símbolos de ausência {`-`,`..`,`...`,`X`} → NULL com alerta IA8; valor não
  inteiro nem símbolo conhecido é bloqueante (IB11). Base dos Dados como
  alternativa **não usada** (seções 3.2 e 5.2).
- **D12 — DTB tem 5.571 linhas** (critério de aceite D1): a linha extra vs. 5.570
  é **`5101837` Boa Esperança do Norte/MT**, município criado e ainda sem
  população estimada; não é duplicata nem erro (seções 3.3 e 9.3).
- **D13 — nulos e linha sem id da população:** população nula permitida com IA7
  (533 em 1996, 1 em 2009; nula em 2010–2021 → IB10); linha sem `id_municipio`
  excluída da silver com IA6 (1 linha, ano 2025; dentro de 2010–2021 → IB9).
  Quebra de série 2021→2022 (Censo 2022) registrada como ressalva no catálogo
  (seções 5.1 e 5.4).
- **D14 — `populacao` do IBGE-POP = população residente total** (urbana + rural),
  referência **1º de julho**; **não** é a `populacao_urbana` do SNIS. Denominador
  dos marts 6–8 (seções 0, 5.1 e [`fontes-ibge.md`](fontes-ibge.md)).
- **D15 — PIB da silver em `BIGINT` em Mil Reais** (sem `DECIMAL`); conversão
  para reais só na gold, com comentário explícito (seção 5.2).
- **D16 — faixas de porte do mart 6** (regra da **gold**, não desta ingestão),
  medidas na população de **2021**: até 5 mil · 5 a 20 mil · 20 a 50 mil · 50 a
  100 mil · 100 a 500 mil · acima de 500 mil habitantes (seção 10).
- **D17 — PIB municipal pode ser negativo**, preservado na silver com alerta
  **IA9**; regex `^-?[0-9]+$`; B5 = "≥ 0 exceto negativos reais do SIDRA listados
  em IA9". Constante **`PIB_NEGATIVOS_MAX = 5`**: acima disso IA9 bloqueia. Medido:
  1 caso (Guamaré/RN, 2012, −19.046 Mil Reais) (seções 5.2 e 9.2). Marts 9/10: PIB
  per capita negativo permanece, cai no menor quartil, sem log (indicadores.md).

### Pendência a reabrir depois
- **D7 provisória:** depois da primeira medição real de cobertura, revisar os
  limiares e registrar os números definitivos.

---

## 12. Downloads — estado real (extração 2026-11-08)

As três fontes **já foram baixadas** na rodada de **2026-11-08**; cada pasta tem
seu `MANIFEST.md`. Nada em `data/raw/` é editado depois de salvo. Para uma
re-extração futura, repetir o procedimento numa pasta `AAAA-MM-DD` nova.

| Fonte | Pasta | Arquivos | Estado |
|---|---|---|---|
| IBGE-POP | `data/raw/ibge/populacao/2026-11-08/` | `populacao_municipio.csv`, `MANIFEST.md` | ✅ baixado |
| IBGE-PIB | `data/raw/ibge/pib/2026-11-08/` | `pib_municipio.csv`, 12× `pib_5938_<ANO>.json`, `MANIFEST.md` | ✅ baixado |
| IBGE-DTB | `data/raw/ibge/dtb/2026-11-08/` | `DTB_2025.zip` (original), `dtb_municipio.csv`, `MANIFEST.md` | ✅ baixado |

### 12.1 IBGE-POP (população) — **feito**
- Exportado da Base dos Dados (`br_ibge_populacao.municipio`) pelo console do
  BigQuery → `populacao_municipio.csv` (3 colunas, 191.099 linhas, UTF-8).
- `MANIFEST.md` com origem, consulta, data, linhas, colunas, `sha256`, anos e as
  peculiaridades (nulos, linha sem id).

### 12.2 IBGE-PIB — **feito** (SIDRA 5938, D11)
- Baixado da **API `apisidra` (SIDRA 5938)**, variável 37, nível `n6`,
  **ano a ano (2010–2021)** → 12× `pib_5938_<ANO>.json` (parciais preservados),
  montados em `pib_municipio.csv` (6 colunas, 66.840 linhas, **Mil Reais**).
- `MANIFEST.md` com URLs, `sha256` de cada parcial e do CSV, unidade e montagem.

### 12.3 IBGE-DTB 2025 (arquivo oficial, D8) — **feito**
- Baixado `DTB_2025.zip` de `geoftp.ibge.gov.br` (página oficial deu HTTP 403);
  original preservado.
- Convertido para `dtb_municipio.csv` (pandas + `xlrd`, aba `DTB_Municípios`,
  9 colunas, 5.571 linhas, UTF-8) como passo separado documentado no MANIFEST.
- `MANIFEST.md` com origem, URL, data, versão 2025, linhas, `sha256` do zip **e**
  do CSV, e os passos da conversão.

### 12.4 Checklist de MANIFEST (as três pastas)
Cada `MANIFEST.md` deve trazer: **origem/URL**, **data de extração**, **nº de
linhas**, **nº de colunas**, **checksum (`sha256`)** — são esses números que
alimentam os critérios de aceite de linhas/colunas (seções 4 e 9). Para o PIB,
registrar a **unidade**; para a DTB, registrar a **versão (2025)** e os **passos
da conversão**.
