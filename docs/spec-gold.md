# Spec da camada gold (silver → gold · 10 marts)

| | |
|---|---|
| **Status** | aprovada, aguardando implementação — **só documentação** (nenhum código, SQL ou dado criado) |
| **Versão** | 2 (aplica D18–D21) |
| **Data** | 2026-11-08 |
| **Responsável** | Luiz |
| **Banco** | `snis.duckdb` · schema `gold` (novo) |
| **Origem** | `silver.municipio_agua_esgoto` + `silver.ibge_populacao_municipio` + `silver.ibge_pib_municipio` + `silver.ibge_dtb_municipio` (tudo somente leitura) |
| **Destino** | schema `gold`, uma tabela `gold.<nome_do_mart>` por arquivo `sql/gold/NN_nome.sql` |

> **Leitura obrigatória antes de implementar:** [`indicadores.md`](indicadores.md)
> (fórmulas e grão dos 10 marts), [`decisoes.md`](decisoes.md) (**D1–D21,
> todas APROVADAS em 2026-11-08**; D18–D21 são as decisões da gold), [`fontes-ibge.md`](fontes-ibge.md) (catálogo
> e IDs de fonte), [`investigacao-silver.md`](investigacao-silver.md) (Rodada 3 e
> Verificação das decisões — os números de referência vêm daqui),
> [`spec-transformacao.md`](spec-transformacao.md) e [`spec-ibge.md`](spec-ibge.md)
> (contratos da silver que a gold herda). Modelo conceitual: **aula 3 do curso
> Olist** ("marts"), adaptada para **gold** (schema `gold`, arquivos
> `sql/gold/NN_nome.sql`, executor `pipeline/gold.py`), com o roteiro
> **"grão → chute → SELECT → arquivo"**.

Esta spec é **só documentação**. Não cria código, nem SQL, nem altera dados,
specs existentes ou `data/raw/`. Sem internet. Sem commit. Os fatos numéricos
foram conferidos no `snis.duckdb` via **MCP somente leitura** (seção 12 lista as
consultas usadas); onde o número final só aparece depois do SELECT validado, a
regra está escrita e marcada **"chute a confirmar"**.

---

## 0. Objetivo

A gold entrega as **tabelas de análise** (marts) que respondem às perguntas de
negócio de [`indicadores.md`](indicadores.md). Cada mart é **uma tabela**,
gerada por **um arquivo SQL**, materializada no schema `gold`. A gold é a **única
camada** onde se calcula indicador, se pondera índice, se faz recorte temporal e
se converte unidade (a silver só tipa e espelha — ver
[`spec-transformacao.md`](spec-transformacao.md)).

---

## 1. Fundamentos e convenções

### 1.1 Schema, pasta e nomes de arquivo

- Schema de saída: **`gold`**.
- Pasta dos SQL: **`sql/gold/`**.
- **Um SQL por mart**, nomeado `NN_nome.sql` (01 a 10), gerando **exatamente uma**
  tabela `gold.<nome>` (o `<nome>` é o do mart em [`indicadores.md`](indicadores.md)):

| Arquivo | Tabela gold | Grão | Fontes (IDs) |
|---|---|---|---|
| `01_atendimento_uf_ano.sql` | `gold.atendimento_uf_ano` | ano × UF | SNIS, IBGE-DTB |
| `02_esgoto_coleta_tratamento_ano.sql` | `gold.esgoto_coleta_tratamento_ano` | ano (Brasil) | SNIS |
| `03_perdas_consumo_uf_ano.sql` | `gold.perdas_consumo_uf_ano` | ano × UF | SNIS, IBGE-DTB |
| `04_ranking_atendimento_variacao.sql` | `gold.ranking_atendimento_variacao` | município (2 anos fixos) | SNIS, IBGE-DTB |
| `05_financeiro_uf_ano.sql` | `gold.financeiro_uf_ano` | ano × UF | SNIS, IBGE-DTB |
| `06_atendimento_porte_ano.sql` | `gold.atendimento_porte_ano` | ano × faixa de porte | SNIS, IBGE-POP |
| `07_populacao_sem_servico_uf_ano.sql` | `gold.populacao_sem_servico_uf_ano` | ano × UF | IBGE-POP, SNIS, IBGE-DTB |
| `08_investimento_per_capita_uf_ano.sql` | `gold.investimento_per_capita_uf_ano` | ano × UF | SNIS, IBGE-POP, IBGE-DTB |
| `09_atendimento_vs_pib_2021.sql` | `gold.atendimento_vs_pib_2021` | município (2021) | SNIS, IBGE-PIB, IBGE-POP |
| `10_avanco_por_renda_painel.sql` | `gold.avanco_por_renda_painel` | quartil × 2 anos | SNIS, IBGE-PIB, IBGE-POP |

> `sql/gold/00_teste.sql` (`SELECT 1 AS x`) existe **só** para validar o executor
> e é **apagado** depois (seção 9.4). Ele não é um mart.

### 1.2 Regras globais (herdadas das decisões e da silver)

1. **Índices sempre `sum(numerador)/sum(denominador)`** por grão — nunca
   `avg()` de uma coluna `indice_*`. Numerador e denominador do **mesmo universo**
   (água com água, urbano com urbano, volume com volume). Regra de
   [`indicadores.md`](indicadores.md).
2. **`municipios_informantes`** em todo mart por ano/grão: nº de municípios com
   numerador **e** denominador não nulos naquele grão (definição no glossário,
   seção 3).
3. **Valores em R$ são nominais** → só comparar **dentro do mesmo ano**. Toda
   coluna monetária/per capita carrega a flag **`valor_nominal = true`**. Nenhuma
   comparação inter-anual de R$ sem deflator (não há deflator no projeto).
4. **Comparação entre anos só com painel fixo declarado** (municípios presentes
   nos dois anos com dado não nulo). Marts 4 e 10 o exigem; nenhum outro compara
   anos.
5. **`CAST` estrito herdado da silver**: a silver já é tipada
   ([`spec-transformacao.md`](spec-transformacao.md) §3); a gold não reconverte
   texto. Divisões usam **`/ nullif(den, 0)`** para nunca dividir por zero.
6. **Ano de referência 2021 nos marts urbanos** (1, 4, 9, 10) — **D2**; nenhum
   mart urbano usa 2022 (população urbana autodeclarada 100% nula em 2022).
7. **Janela 2010–2021** para tudo que usa o IBGE (D1, catálogo; limite da série
   do PIB). Marts 6, 7, 8, 9, 10.
8. **Dimensão territorial** (UF, nome da UF, macrorregião) vem **sempre de
   `silver.ibge_dtb_municipio`** (`sigla_uf`, `nome_uf`, `nome_regiao`), por
   junção em `id_municipio` — **nunca** de seed e **nunca** da `sigla_uf` do SNIS
   (esta serve só de conferência; ver teste em
   [`tests/test_ibge_silver.py`](../tests/test_ibge_silver.py)).

### 1.3 Universo dos denominadores (D14)

| Denominador | Coluna | Quando usar |
|---|---|---|
| **População urbana SNIS** | `populacao_urbana` (água), `populacao_urbana_residente_esgoto` (esgoto) | coberturas **urbanas** (marts 1, 4, 10) |
| **População total IBGE** | `populacao_total_ibge` (IBGE-POP; residente total, ref. 1º/jul, D14) | per capita e coberturas sobre o **total** (marts 6, 7, 8, 9, 10-quartil) |
| **Volume SNIS** | `volume_agua_produzido`, `volume_agua_consumido`, `volume_esgoto_coletado` | perdas e esgoto (marts 2, 3) |
| **População atendida SNIS** | `populacao_atendida_agua` | consumo per capita (mart 3) |

**`populacao_total_ibge` (IBGE) ≠ `populacao_urbana` (SNIS)** — são medidas
distintas (D14); nunca misturar numerador de um universo com denominador do
outro.

---

## 2. Fichas dos 10 marts

Cada ficha responde **as três perguntas** (pergunta de negócio · grão · chaves),
dá **colunas + fórmulas exatas**, **regras específicas** das decisões, e os
**critérios de aceite**. Onde o número só se conhece depois do SELECT validado,
está marcado **"chute a confirmar"** (roteiro da aula 3).

> **Convenção de fórmula:** `Σx` = `sum(x)` no grão da linha; toda razão é
> `Σnum / nullif(Σden, 0)`. "× 100" quando o indicador é percentual.

---

### Mart 1 — `gold.atendimento_uf_ano`

- **Pergunta:** qual % da população **urbana** tem água e esgoto, por UF e ano?
- **Grão:** uma linha = **(ano, UF)**. Região anexada pela DTB.
- **Chave primária:** `(ano, sigla_uf)`. **FKs:** SNIS por `(ano, id_municipio)`;
  DTB por `id_municipio` → `sigla_uf`, `nome_uf`, `nome_regiao`.

**Colunas:**

| Coluna | Tipo | Descrição | Unidade |
|---|---|---|---|
| `ano` | INTEGER | ano de referência (2010–2021; D2) | — |
| `sigla_uf` | VARCHAR | UF (DTB) | — |
| `nome_uf` | VARCHAR | nome da UF (DTB) | — |
| `nome_regiao` | VARCHAR | macrorregião (DTB) | — |
| `cobertura_urbana_agua` | DECIMAL | `Σpopulacao_urbana_atendida_agua / nullif(Σpopulacao_urbana,0) × 100` | % |
| `cobertura_urbana_esgoto` | DECIMAL | `Σpopulacao_urbana_atendida_esgoto / nullif(Σpopulacao_urbana_residente_esgoto,0) × 100` | % |
| `municipios_informantes_agua` | INTEGER | municípios com num. e den. de água não nulos **e** fora da exclusão A2 (entram no cálculo) | contagem |
| `municipios_informantes_esgoto` | INTEGER | idem esgoto | contagem |
| `excluidas_a2_agua` | INTEGER | municípios-linha excluídos pela flag A2 de **água** (D5), por grão; `municipios_informantes_agua + excluidas_a2_agua` = municípios com água não nula | contagem |
| `excluidas_a2_esgoto` | INTEGER | idem para **esgoto**; fecha a identidade com `municipios_informantes_esgoto` | contagem |
| `linhas_excluidas_a2` | INTEGER | municípios-linha excluídos pela flag A2 em **água OU esgoto** (D5), por grão | contagem |

- **Denominador:** urbano SNIS (`populacao_urbana`; esgoto usa
  `populacao_urbana_residente_esgoto`).
- **Anos:** 2010–2021 (**2021** é o ano de referência de destaque, D2).
- **Fontes:** SNIS; **IBGE-DTB** (UF/região).
- **Regra D5 (violação A2):** excluir do cálculo as linhas
  `populacao_urbana_atendida_agua > populacao_urbana` (e o par de esgoto), **com
  flag** e **sem clamp**; contar as excluídas por grão em `linhas_excluidas_a2`.
  Impacto nacional ≤ 0,17 pp (Verificação D5).
- **Aceite (confirmado no SELECT, 2026-11-08):** **324 linhas** = 27 UFs × 12
  anos (PK `(ano, sigla_uf)` sem duplicatas; dimensões DTB não nulas). Cada
  cobertura em [0, 100] (medido: água [35,46; 100,0], esgoto [4,99; 97,03]).
  Cobertura urbana de água nacional **2021 = 93,33%** (baseline D5 ≈ 93,4% ✓).
  `municipios_informantes_agua` somado em **2021 = 5.284** — são **5.302** sem a
  D5 **menos 18 exclusões A2 de água** (a DTB cobre 100% dos informantes; o join
  não derruba nenhum). 11 colunas.
- **Exclusões A2 por ano (D5), confirmadas no SELECT** (água / esgoto / água OU
  esgoto):

  | ano | água | esgoto | total (A2) |
  |---|---|---|---|
  | 2010 | 26 | 2 | 28 |
  | 2011 | 35 | 3 | 37 |
  | 2012 | 22 | 5 | 27 |
  | 2013 | 3 | 0 | 3 |
  | 2014 | 3 | 0 | 3 |
  | 2015 | 1 | 2 | 3 |
  | 2016 | 43 | 7 | 49 |
  | 2017 | 7 | 0 | 7 |
  | 2018 | 1 | 0 | 1 |
  | 2019 | 7 | 0 | 7 |
  | 2020 | 6 | 0 | 6 |
  | 2021 | 18 | 7 | 24 |

  Exclusões de água por ano ≤ 43 (máx. 2016), coerente com a conferência C6
  (≤ ~43 em água). Identidade verificada:
  `municipios_informantes_agua + excluidas_a2_agua` = municípios com água não
  nula no grão (idem esgoto).

---

### Mart 2 — `gold.esgoto_coleta_tratamento_ano`

- **Pergunta:** quanto do esgoto é coletado e tratado no Brasil, por ano?
- **Grão:** uma linha = **(ano)**, Brasil.
- **Chave primária:** `(ano)`. **FKs:** SNIS por `(ano, id_municipio)`. **Sem
  dimensão territorial** (único mart 100% SNIS, D1).

**Colunas (13):**

| Coluna | Tipo | Descrição | Unidade |
|---|---|---|---|
| `ano` | INTEGER | 1995–2022 | — |
| `indice_coleta_esgoto` | DECIMAL | `Σvolume_esgoto_coletado / nullif(Σvolume_agua_consumido,0) × 100` (coletado ÷ água consumida — **não** IN046; universo comum den > 0) | % |
| `indice_tratamento_esgoto` | DECIMAL | **IN016**: `Σvolume_esgoto_tratado / nullif(Σvolume_esgoto_coletado,0) × 100` (tratado ÷ **coletado**; universo comum den > 0) | % |
| `indice_coleta_painel` | DECIMAL | mesmo índice de coleta só no **painel de esgoto-coleta** (D24, 1.473 mun.); **NULL fora de 2010–2021** | % |
| `indice_tratamento_painel` | DECIMAL | mesmo índice de tratamento só no **painel de esgoto-tratamento** (D24, 1.440 mun.); **NULL fora de 2010–2021** | % |
| `municipios_informantes_coleta` | INTEGER | universo comum da coleta: coletado e consumido não nulos **e consumido > 0** | contagem |
| `municipios_informantes_tratamento` | INTEGER | universo comum do tratamento: tratado e coletado não nulos **e coletado > 0** | contagem |
| `municipios_painel_coleta` | INTEGER | municípios do painel de coleta por ano (constante **1.473** em 2010–2021; **NULL fora**) | contagem |
| `municipios_painel_tratamento` | INTEGER | municípios do painel de tratamento por ano (constante **1.440** em 2010–2021; **NULL fora**) | contagem |
| `excluidas_den_zero_coleta` | INTEGER | coletado e consumido não nulos mas **consumido = 0** (fora do universo comum) | contagem |
| `excluidas_den_zero_tratamento` | INTEGER | tratado e coletado não nulos mas **coletado = 0** (fora do universo comum) | contagem |
| `municipios_tratado_acima_coletado` | INTEGER | **diagnóstico**: `tratado > coletado` (NÃO excluído — ver ressalva) | contagem |
| `serie_robusta` | BOOLEAN | `municipios_informantes_coleta > 1000` → **true de 2006 em diante** (R3) | — |

- **Denominador:** volume SNIS (água consumida para coleta; esgoto coletado para
  tratamento) — mesmo universo volume/volume, **soma sobre soma**, den > 0.
- **Identidade (D23):** `municipios_informantes_* + excluidas_den_zero_* =
  municípios com os dois volumes não nulos` (por coluna e por ano).
- **Anos:** **1995–2022** (volumes presentes em 2022); **robusto a partir de
  2006** (`volume_esgoto_coletado` só passa de 1.000 informantes em **2006 =
  1.218**, investigacao-silver.md). Nenhum ano é excluído; os frágeis ficam
  marcados por `serie_robusta = false`.
- **Fontes:** SNIS.

**Ressalva de composição e painel (D23/D24):** a série por ano dos índices "de
todos os informantes" **mistura efeito de composição** (os informantes mudam de
ano para ano). A **tendência** deve ser lida pelas colunas de **painel**
(conjunto fixo). Os painéis de esgoto têm **1.473** (coleta) e **1.440**
(tratamento) municípios, contra **4.472** do painel de água (D19) — **não são
representativos do Brasil** (só municípios que informam esgoto em todos os anos
de 2010–2021). Logo, as colunas de painel servem para ler a **tendência**, não o
**nível** nacional, e **não devem ser comparadas em nível** com os índices de
todos os informantes.

**Ressalva `tratado > coletado` (D23):** não é excluído do índice — é esgoto
**importado** para tratamento (município trata mais do que coleta); por isso
`indice_tratamento_esgoto` **pode passar de 100** em anos/recortes frágeis. A
contagem fica exposta em `municipios_tratado_acima_coletado`.

**Anomalias de 1995–2005 (erro de dado preservado sem correção):** nos anos
frágeis um único município domina o numerador da coleta e dispara o índice acima
de 1.500%:

| ano | município | UF | coletado | consumido | razão | % do numerador |
|---|---|---|---|---|---|---|
| 1998 | Fortaleza (2304400) | CE | 47.452.063 | 94.163 | 504× | 88,9% |
| 1999 | Recife (2611606) | PE | 29.071.968 | 30.683 | 948× | 52,7% |

São os **dois valores máximos** de `volume_esgoto_coletado` (erro de escala/
dígito no bruto, não esgoto importado — nenhuma cidade coleta 500–950× o que
consome). **Preservados sem correção** (a silver espelha; o mart não altera
dado) e **isolados por `serie_robusta = false`** (ambos < 2006).

- **Aceite (confirmado no SELECT/MCP, 2026-11-08):** **28 linhas** (1995–2022) ×
  **13 colunas**; PK `(ano)` sem duplicatas; índices "de todos" não nulos (den >
  0). `municipios_informantes_coleta` cresce de **20 (1995)** a **3.051 (2022)**;
  `municipios_informantes_tratamento` de **19 (1995)** a **2.897 (2022)**
  (universo comum den > 0; os ~3.057 "ambos não nulos" de 2022 incluem 160 com
  `coletado = 0`). Índice de coleta recente ~**56% (2021)**; tratamento sobre
  coletado **80,3% (2021)** (nível oficial SNIS ~80% ✓). Painel: coleta
  **60,90 → 55,89** e tratamento **69,37 → 85,18** (2010 → 2021), contagens
  constantes **1.473 / 1.440**.

---

### Mart 3 — `gold.perdas_consumo_uf_ano`

- **Pergunta:** quanto de água se perde na distribuição e quanto cada pessoa
  consome, por UF e ano?
- **Grão:** uma linha = **(ano, UF)**.
- **Chave primária:** `(ano, sigla_uf)`. **FKs:** SNIS `(ano, id_municipio)`;
  DTB `id_municipio` → UF/região.

**Colunas:**

| Coluna | Tipo | Descrição | Unidade |
|---|---|---|---|
| `ano` | INTEGER | 1995–2022 | — |
| `sigla_uf`, `nome_uf`, `nome_regiao` | VARCHAR | dimensão territorial (DTB) | — |
| `indice_perdas_in049` | DECIMAL | fórmula completa do IN049 (abaixo) | % |
| `consumo_per_capita` | DECIMAL | **IN022 (D25):** `Σ(volume_agua_consumido − volume_agua_tratada_exportado) × 1.000.000 / nullif(Σ(pop_med × 365), 0)`, com `pop_med` = média da `populacao_atendida_agua` do ano e do ano anterior | L/hab·dia |
| `municipios_informantes_perdas` | INTEGER | municípios que **entram no cálculo** de perdas: AG006 e AG010 não nulos **e não inconsistentes** (D3; alinha com a identidade do mart 1, ver nota) | contagem |
| `municipios_informantes_consumo` | INTEGER | municípios com volume consumido e pop. atendida não nulos **e pop > 0** | contagem |
| `linhas_inconsistentes_in049` | INTEGER | municípios excluídos pela salvaguarda (D3), por grão = `excluidas_den_nao_positivo + excluidas_consumo_acima` | contagem |
| `excluidas_den_nao_positivo` | INTEGER | componente da salvaguarda (D3): `(AG006+AG018−AG024) ≤ 0` (com AG006 e AG010 não nulos) | contagem |
| `excluidas_consumo_acima` | INTEGER | componente da salvaguarda (D3): denominador > 0 mas `AG010 > (AG006+AG018−AG024)` | contagem |
| `linhas_consumo_liquido_negativo` | INTEGER | **diagnóstico (D25):** `volume_agua_consumido − volume_agua_tratada_exportado < 0`, **NÃO excluído** | contagem |

- **Fórmula D3 (IN049 completo, glossário SNIS 2022):**
  `Σ(AG006 + AG018 − AG010 − AG024) / nullif(Σ(AG006 + AG018 − AG024), 0) × 100`,
  com `AG006 = volume_agua_produzido`, `AG018 = volume_agua_tratada_importado`,
  `AG010 = volume_agua_consumido`, `AG024 = volume_servico_agua`. **AG018 e AG024
  majoritariamente nulos → `coalesce(…, 0)`**; exigir **AG006 e AG010 não nulos**.
- **Salvaguarda D3 (exclusão com flag), em dois componentes:** excluir do cálculo
  as linhas com **`(AG006 + AG018 − AG024) ≤ 0`** (`excluidas_den_nao_positivo`)
  **ou** `AG010 > (AG006 + AG018 − AG024)` com denominador > 0
  (`excluidas_consumo_acima`); a soma dos dois = `linhas_inconsistentes_in049`.
  Impacto ≤ 0,15 pp no nacional, **0 UFs** mudam > 5 pp (Verificação D3 revisada)
  — é **só salvaguarda**, não a regra decisiva. `excluidas_consumo_acima` por ano
  na janela = **0–57** (Verificação D3).
- **Consumo per capita = IN022 (D25):** `Σ(volume_agua_consumido −
  volume_agua_tratada_exportado) × 1.000.000 / nullif(Σ(pop_med × 365), 0)`.
  **`pop_med` = média da `populacao_atendida_agua` do ano e do ano imediatamente
  anterior** (`(pop + coalesce(pop_ano−1, pop)) / 2`; sem ano anterior →
  `pop_med = pop`). **Unidade:** o volume vem em **1.000 m³/ano**, então
  **× 1.000.000** (L) **÷ 365** (dias) = L/hab·dia — comentário explícito no SQL.
  Verificado linha a linha contra a coluna publicada `indice_consumo_agua_per_capita`:
  **99,95%** das linhas com diff < 0,5% (ver D25 em
  [`investigacao-silver.md`](investigacao-silver.md)). A fórmula ingênua `AG010 /
  pop do ano` dava 183 L/hab·dia (≠ IN022); a variante cB dá **151,3** (2021).
- **Denominador:** perdas → volume disponibilizado SNIS; consumo → população
  atendida SNIS (`populacao_atendida_agua` = **total atendida, urbana+rural**,
  D25; **não** IBGE).
- **Nota (`municipios_informantes_perdas`):** conta os municípios que **entram no
  cálculo** (não nulos **e** consistentes), para fechar a identidade
  `municipios_informantes_perdas + linhas_inconsistentes_in049 = municípios com
  AG006 e AG010 não nulos` (padrão do mart 1). Difere da redação literal "AG006 e
  AG010 não nulos" por descontar as inconsistentes — proposital.
- **Anos:** 1995–2022 (robusto ≥ 2001).
- **Fontes:** SNIS; **IBGE-DTB**.
- **Diagnóstico de extremos (D25):** `linhas_consumo_liquido_negativo` conta
  `volume_agua_consumido − volume_agua_tratada_exportado < 0` (**4 linhas** em
  2010–2021, imaterial), **sem exclusão**. **Vilhena/RO 1997** é o único per
  capita absurdo (~46.760 L/hab·dia: `volume_agua_consumido` com erro de escala no
  bruto, ano pré-robusto) — **preservado sem correção, documentado**.
- **Aceite (confirmado no SELECT, 2026-11-08):** **754 linhas** (27 UFs × 28 anos
  = 756, menos **2** pares ausentes em anos iniciais); PK `(ano, sigla_uf)` sem
  duplicatas; dimensões DTB não nulas. `indice_perdas_in049` ∈ **[0; 94,48]**
  (0 fora de [0,100]); índice nacional ponderado 2010–2021 = **37,42%** (nível
  oficial ~40% ✓). `consumo_per_capita` nacional **2021 ≈ 151,3 L/hab·dia** (IN022
  ~152 ✓). Identidade informantes+inconsistentes verificada nos 12 anos;
  componentes somam as inconsistentes. Único extremo: Vilhena/RO 1997.

---

### Mart 4 — `gold.ranking_atendimento_variacao`

- **Pergunta:** quais municípios mais melhoraram ou pioraram no atendimento
  urbano de água entre **dois anos fixos**?
- **Grão:** uma linha = **município** (do painel fixo), com a variação entre os
  dois anos.
- **Chave primária:** `(id_municipio)`. **FKs:** SNIS `(ano, id_municipio)` nos
  dois anos; DTB `id_municipio` → UF/região.

**Anos fixos e painel (D19):** **ano_inicio = 2010, ano_fim = 2021** (nunca
2022). Usa o **painel fixo único** do glossário (seção 3) — **4.472 municípios**
com `populacao_urbana_atendida_agua` e `populacao_urbana` não nulos em **todos os
12 anos de 2010 a 2021** (confirmado no MCP), as 27 UFs. **Mesmo painel do mart
10** (D19: um único painel, não dois). Municípios **fora do painel** não entram
no ranking e são **contados** numa linha de diagnóstico do executor (não viram
linha do mart).

**Colunas:**

| Coluna | Tipo | Descrição | Unidade |
|---|---|---|---|
| `id_municipio` | VARCHAR | município (painel) | — |
| `sigla_uf`, `nome_uf`, `nome_regiao` | VARCHAR | DTB | — |
| `cobertura_2010` | DECIMAL | `populacao_urbana_atendida_agua/nullif(populacao_urbana,0) × 100` em 2010 | % |
| `cobertura_2021` | DECIMAL | idem em 2021 | % |
| `variacao_pp` | DECIMAL | `cobertura_2021 − cobertura_2010` | pontos percentuais |
| `posicao` | INTEGER | **D26:** `row_number() OVER (ORDER BY variacao_pp DESC, populacao_urbana_fim DESC, id_municipio ASC)` — 1..N única, **sem buracos** (posição 1 = maior melhoria) | — |
| `posicao_empate` | INTEGER | **D26:** `rank() OVER (ORDER BY variacao_pp DESC)` — empates **compartilham** a posição (com buracos) | — |
| `variacao_extrema` | BOOLEAN | **diagnóstico:** `abs(variacao_pp) > 80` (12 casos); possível erro de dado ou mudança de prestador/cobertura, **preservado sem correção** | — |

- **Regra D21:** o mart traz **só** o ranking (`posicao`) e a variação em pontos
  percentuais (`variacao_pp`); **sem `quintil_variacao`**.
- **Regra D5:** aplicar a exclusão A2 por município-ano (um município com
  violação em 2010 ou 2021 sai do painel, com flag no diagnóstico). **41
  excluídos** (26 em 2010, 16 em 2021; sobrepostos), todos membros do painel.
- **Regra D26 (empates):** `posicao` = `row_number()` ordenado por `variacao_pp
  DESC, populacao_urbana_fim DESC, id_municipio ASC` (1..N única, sem buracos);
  `posicao_empate` = `rank()` sobre `variacao_pp DESC` (empates compartilham). O
  desempate só por `id_municipio` daria ordem arbitrária nos extremos (vários
  empatados em +100 pp), por isso o critério de população urbana de 2021.
- **Fórmula:** cobertura **por município** em cada ano (não ponderar — é 1
  município por linha); variação = ano_fim − ano_início; window functions
  (roteiro `CTE` + `row_number()`/`rank()`).
- **Aceite (confirmado no SELECT/executor, 2026-11-08):** **4.431 linhas** =
  painel fixo único **4.472** menos **41** excluídos por A2 (identidade D5:
  4.472 = 4.431 + 41 ✓). PK `id_municipio` única (1 linha/município); `posicao`
  1..4.431 sem buracos; `posicao_empate` 1..4.429 (empates compartilham, mín. 1);
  `variacao_pp ∈ [−100, +100]`, mediana 0 (1.371 municípios já a 100% nos dois
  anos); **12** casos de `variacao_extrema`. Dimensões DTB não nulas. **10 colunas.**
- **Diagnóstico de extremos (preservados sem correção, "a investigar"):**
  **3162500/MG** (11,8%→100%, **+88,2 pp**, ~86 mil urb. em 2021 — maior salto em
  município grande); **3301900/RJ** (81,8%→21,3%, **−60,5 pp**, ~241 mil urb. —
  maior piora grande); pioras de **100%→0% na PB** (`2506004`, `2516409`,
  `2500908`). Possível mudança de prestador/cobertura ou erro de dado; **sem
  clamp, sem correção**, sinalizados por `variacao_extrema`.

---

### Mart 5 — `gold.financeiro_uf_ano`

- **Pergunta:** quanto se investe e se gasta por UF e ano (valores **nominais**)?
- **Grão:** uma linha = **(ano, UF)**.
- **Chave primária:** `(ano, sigla_uf)`. **FKs:** SNIS `(ano, id_municipio)`;
  DTB `id_municipio` → UF/região.

**Colunas:**

| Coluna | Tipo | Descrição | Unidade |
|---|---|---|---|
| `ano` | INTEGER | 1995–2022 | — |
| `sigla_uf`, `nome_uf`, `nome_regiao` | VARCHAR | DTB | — |
| `investimento_total` | DECIMAL | `Σinvestimento_total_prestador` (**todos** os municípios — o dinheiro foi gasto) | R$ (nominal) |
| `investimento_total_sem_atipicos` | DECIMAL | **D4/D28:** idem, **excluindo** os municípios com flag `investimento_atipico` | R$ (nominal) |
| `despesa_total_servicos` | DECIMAL | **D27:** `Σdespesa_total_servico` (FN017/DTS) | R$ (nominal) |
| `despesa_exploracao_dex` | DECIMAL | **D27:** `Σdespesa_exploracao` (FN015/DEX, sem indicador por m³) | R$ (nominal) |
| `receita_operacional_direta` | DECIMAL | `Σreceita_operacional_direta` (FN001) | R$ (nominal) |
| `indice_despesa_sobre_receita` | DECIMAL | **D27:** `Σdespesa_total_servico / nullif(Σreceita_operacional_direta,0) × 100` no universo `dts` e `fn001` não nulos (mesmo ano) — **despesa÷receita** (fração da receita consumida pela despesa total; o inverso receita÷despesa seria o IN012, não pedido aqui) | % |
| `tarifa_media` | DECIMAL | **D18/D22:** `Σreceita_operacional_direta / (nullif(Σ(volume_agua_faturado+volume_esgoto_faturado),0) × 1000)` — soma sobre soma (FN001 ÷ (AG011+ES007)) → IN004 | R$/m³ (nominal) |
| `despesa_unitaria` | DECIMAL | **D22/D27:** `Σdespesa_total_servico / (nullif(Σ(volume_agua_faturado+volume_esgoto_faturado),0) × 1000)` — soma sobre soma (**FN017** ÷ (AG011+ES007)) → IN003 | R$/m³ (nominal) |
| `municipios_informantes_investimento` | INTEGER | municípios com investimento não nulo | contagem |
| `municipios_informantes_tarifa` | INTEGER | **D22:** municípios com `fn001` não nulo e `vol_fat > 0` (universo comum) | contagem |
| `municipios_informantes_despesa` | INTEGER | **D22/D27:** municípios com `dts` não nulo e `vol_fat > 0` (universo comum) | contagem |
| `municipios_investimento_atipico` | INTEGER | **D4/D28:** municípios com flag `investimento_atipico`, por grão | contagem |

- **Denominador:** razões só **dentro do mesmo ano e universo SNIS**.
- **Regra D18/D22/D27 (verificada nos dados):** **tarifa média** e **despesa
  unitária** são **colunas deste mart** (não um 11º mart), soma sobre soma. O
  denominador comum é `volume_agua_faturado + volume_esgoto_faturado`
  (AG011+ES007). **Unidade R$/m³:** o volume vem em **1.000 m³/ano**, então a
  conversão **divide por 1.000** (`× 1000` no denominador) — com **comentário
  explícito no SQL**. **D27:** a `despesa_unitaria` (IN003) usa **FN017 =
  `despesa_total_servico` (DTS)**, não `despesa_exploracao` (FN015/DEX, que fica
  como `despesa_exploracao_dex` em R$). **Universo comum** (por índice): numerador
  e denominador não nulos **e denominador > 0** — colunas
  `municipios_informantes_tarifa` e `municipios_informantes_despesa`. Confirmação:
  identidade FN001 fecha 100%; DTS ⊇ DEX em 99,3–99,8% das linhas; a série
  nacional 2010–2021 vai de **R$ 2,18 → 4,12/m³** (tarifa) e **R$ 2,06 → 3,87/m³**
  (despesa unitária DTS) — ver "Verificação de despesa unitária e tarifa média" de
  [`investigacao-silver.md`](investigacao-silver.md) e D27.
- **Regra D4/D28 (investimento atípico):** flag **`investimento_atipico`** quando
  o **investimento per capita do município > R$ 1.000/hab** (limiar **nominal**,
  sem ajuste por inflação). Exige **população IBGE** (janela **2010–2021**); fora
  da janela ou sem população IBGE a flag **não é avaliada** e o município fica nos
  **dois** totais (`investimento_total_sem_atipicos` = `investimento_total` nesses
  grãos). Os atípicos **permanecem** em `investimento_total` (o dinheiro foi
  gasto) e **saem** de `investimento_total_sem_atipicos`. **Mesma regra e mesmo
  nome reusados no mart 8.** A **hipótese de prestador regional é hipótese, não
  fato** (a silver não tem coluna de prestador). **Nota de UF:** **RN** é a UF mais
  afetada (−29% do total se os atípicos fossem excluídos; cita MA/SE/PE).
- **Sensibilidade do limiar (D28, MCP 2026-11-08):**

  | Limiar | Atípicos (2010–2021) | Queda do total de RN |
  |---|---|---|
  | R$ 500 | 394 | −40,7% |
  | R$ 627 (p99,5 real) | 267 | −36,4% |
  | **R$ 1.000 (D4, p99,8)** | **120** | **−29,0%** |

  Os descritivos antigos da D4 (~290, p99,5, RN −36%) são o corte em **p99,5 =
  R$ 627**; a regra fixada é **R$ 1.000** (120 atípicos, RN −29%).
- **Anos:** 1995–2022 (robusto ≥ 2001).
- **Fontes:** SNIS; **IBGE-DTB**; **IBGE-POP** (só para a flag `investimento_atipico`).
- **Regra:** **R$ nominal** — nunca comparar anos sem correção (ressalva da ficha,
  não há coluna constante). Os atípicos **permanecem** no total por UF (D4/D28).
- **Pico de 2019 (D28, preservado sem correção):** 48 atípicos, **45 de RN**
  (investimento total de RN em 2019 = **R$ 1,52 bi**, 5–30× os demais anos), 45
  valores distintos — coerente com prestador regional único (CAERN), mas sem
  coluna de prestador para confirmar; mantido como dado.
- **Aceite (confirmado no SELECT, 2026-11-08):** **754 linhas** (= 27×28 − 2; sem
  informante em **1996-AC** e **1996-PI**). PK `(ano, sigla_uf)` sem duplicatas;
  dimensões DTB não nulas; **16 colunas**. Tarifa nacional **2,18 (2010) → 4,12
  (2021)**; despesa unitária (DTS) **2,06 (2010) → 3,87 (2021)**;
  `Σinvestimento_total` das 27 UFs em 2021 = **R$ 15.297.535.452,19** (total Brasil
  2021); **120** municípios atípicos na janela (RN −29%). Extremos de tarifa/despesa
  fora de [0,2; 20] R$/m³ só em **1995–2000** (nominais baixos no início da série),
  nenhum no período robusto ≥ 2001 — preservados.

> **D18/D22/D27 (fechado, verificado nos dados):** tarifa média (FN001) e despesa
> unitária (**FN017 = DTS**) são **colunas deste mart**, soma sobre soma, em
> **R$/m³** (÷1.000 no volume); **não há 11º mart**. Nominais — deflacionar está
> **fora do escopo**.

---

### Mart 6 — `gold.atendimento_porte_ano`

- **Pergunta:** como variam as coberturas de água e esgoto por **faixa de porte**
  populacional do município?
- **Grão:** uma linha = **(ano, faixa_porte)**.
- **Chave primária:** `(ano, faixa_porte)`. **FKs:** SNIS `(ano, id_municipio)`;
  IBGE-POP `(ano, id_municipio)` → `populacao_total_ibge`.

**Faixas de porte (D16), medidas pela população IBGE de 2021** (fixa por
município, aplicada a todos os anos do mart):

| `faixa_porte` | Limite (hab.) | Nº de municípios (2021, MCP) |
|---|---|---|
| `1_ate_5mil` | < 5.000 | 1.250 |
| `2_5a20mil` | 5.000–19.999 | 2.520 |
| `3_20a50mil` | 20.000–49.999 | 1.120 |
| `4_50a100mil` | 50.000–99.999 | 354 |
| `5_100a500mil` | 100.000–499.999 | 277 |
| `6_acima500mil` | ≥ 500.000 | 49 |
| **total** | | **5.570** |

**Colunas:**

| Coluna | Tipo | Descrição | Unidade |
|---|---|---|---|
| `ano` | INTEGER | 2010–2021 (janela IBGE) | — |
| `faixa_porte` | VARCHAR | uma das 6 faixas (porte fixado em 2021, D16) | — |
| `pop_total_ibge` | BIGINT | Σ`populacao_total_ibge` da faixa inteira no ano | habitantes |
| `municipios_faixa` | INTEGER | nº de municípios da faixa (fixo: 1.250/2.520/1.120/354/277/49) | contagem |
| `pop_informante_agua` | BIGINT | Σ`populacao_total_ibge` **dos informantes de água** (denominador da água e do esgoto, D29) | habitantes |
| `pop_informante_esgoto` | BIGINT | Σ`populacao_total_ibge` dos informantes de esgoto (denominador só do auxiliar) | habitantes |
| `cobertura_agua` | DECIMAL | **IN055** — `Σpopulacao_atendida_agua / nullif(Σpop_total_ibge FILTER (informa água),0) × 100` | % |
| `cobertura_esgoto` | DECIMAL | **IN056** — `Σpopulacao_atendida_esgoto / nullif(Σpop_total_ibge FILTER (informa **ÁGUA**),0) × 100` (denominador = `pop_informante_agua`, **não** `pop_informante_esgoto`; D29) | % |
| `cobertura_esgoto_entre_informantes` | DECIMAL | **auxiliar** — `Σpopulacao_atendida_esgoto / nullif(Σpop_total_ibge FILTER (informa esgoto),0) × 100`; descreve **só quem informa** esgoto, **não comparar faixas por ela** (D29) | % |
| `municipios_informantes_agua` | INTEGER | municípios com atendido água e pop. IBGE não nulos | contagem |
| `municipios_informantes_esgoto` | INTEGER | idem esgoto | contagem |

- **Denominador (D29):** **água e esgoto** dividem pela **população IBGE dos
  informantes de água** (universo comum na água; convenção oficial **IN056** no
  esgoto — o denominador é `pop_informante_agua`). O universo comum vale para a
  água e os demais indicadores; foi **afastado para o esgoto por viés de seleção**
  (branco de esgoto = "sem sistema": 2.531 de 2.532 brancos de 2021 têm colunas
  físicas de esgoto nulas/zero). A **faixa** é da população IBGE 2021 do município.
- **Anos:** 2010–2021. Universo = cadastro `silver.ibge_dtb_municipio` (5.571);
  **1 excluído** sem pop. IBGE 2021 (5101837 Boa Esperança do Norte/MT, D12) →
  **5.570 nas faixas + 1 = 5.571**.
- **Fontes:** SNIS (atendidos); **IBGE-POP** (população total e porte).
- **Mart 6 (total) ≠ mart 1 (urbano):** o mart 6 usa população **total** (IBGE) e
  o mart 1 população **urbana** (SNIS); os nacionais (água **84,2%** aqui vs.
  **93,4%** no mart 1) **não são comparáveis** e o dashboard **não deve cruzá-los**
  — só comparar o **sentido** (ambos crescem com o porte / com a urbanização).
- **Regra:** exige **teste de cobertura de junção** SNIS×IBGE antes do join (já
  rodado em [`pipeline/cobertura.py`](../pipeline/cobertura.py)); numerador
  (atendidos SNIS) e denominador (pop. IBGE dos informantes) → coberturas < 100%
  esperadas.
- **Aceite (confirmado no SELECT/MCP, 2026-11-08):** **6 faixas × 12 anos = 72
  linhas**, PK `(faixa_porte, ano)` sem duplicatas; faixa fixa nos 12 anos
  (1.250/2.520/1.120/354/277/49); **Σ`pop_total_ibge` das faixas em 2021 =
  213.317.639** (= estimativa IBGE Brasil 2021); identidade informantes +
  não-informantes = `municipios_faixa` em todos os grãos.
  **Nacional 2021 (soma sobre soma):** água **84,20%** (= IN055 oficial 84,2%),
  esgoto **55,81%** (= IN056 oficial 55,8%), auxiliar **66,95%**.
- **Perfil por faixa 2021 (confirmado):** **esgoto (IN056) monótono crescente**
  nas 6 faixas (23,60 → 77,15 ✓). **Água (IN055) cresce a partir da faixa 2**
  (66,11 → 94,47); a **faixa 1 (72,20) > faixa 2 (66,11)** é registrada como
  **fato, sem causa atribuída** (não testada). O auxiliar **não** é monótono
  (viés de seleção) — por isso é só descritivo. Água > esgoto em todas as faixas.
  **Exceção única:** 1 município da faixa 5 informa água, não informa atendido de
  esgoto e tem infraestrutura física → missing isolado (D29).

---

### Mart 7 — `gold.populacao_sem_servico_uf_ano`

- **Pergunta:** quantos habitantes, em números absolutos, estão sem esgoto
  coletado e sem água, por UF?
- **Grão:** uma linha = **(ano, UF)**.
- **Chave primária:** `(ano, sigla_uf)`. **FKs:** SNIS `(ano, id_municipio)`;
  IBGE-POP `(ano, id_municipio)`; DTB `id_municipio` → UF/região.

**Colunas:**

| Coluna | Tipo | Descrição | Unidade |
|---|---|---|---|
| `ano` | INTEGER | 2010–2021 | — |
| `sigla_uf`, `nome_uf`, `nome_regiao` | VARCHAR | DTB | — |
| `pop_total_ibge` | BIGINT | `Σ populacao_total_ibge` da UF no ano (residente total, D14) | habitantes |
| `pop_informante_agua` | BIGINT | `Σ populacao_total_ibge` **dos informantes de água** (denominador dos percentuais) | habitantes |
| `pop_sem_agua` | BIGINT | `Σ greatest(populacao_total_ibge − populacao_atendida_agua, 0)` **por município**, só informantes de água | habitantes |
| `pop_sem_informacao_agua` | BIGINT | `Σ populacao_total_ibge` dos municípios **sem informação de água** — o "piso": esses ficam fora de `pop_sem_agua` | habitantes |
| `pop_sem_esgoto` | BIGINT | **IN056/D30** — `Σ greatest(populacao_total_ibge − coalesce(populacao_atendida_esgoto,0), 0)` por município, **entre informantes de ÁGUA** (branco de esgoto = sem rede) | habitantes |
| `pct_sem_agua` | DECIMAL | `100 × pop_sem_agua / nullif(pop_informante_agua,0)` (= 100 − IN055) | % |
| `pct_sem_esgoto` | DECIMAL | `100 × pop_sem_esgoto / nullif(pop_informante_agua,0)` (= 100 − IN056; denominador = `pop_informante_agua`, **não** informantes de esgoto) | % |
| `municipios_informantes_agua` | INTEGER | municípios com pop. IBGE e atendido água não nulos | contagem |
| `municipios_sem_informacao_agua` | INTEGER | municípios com pop. IBGE e atendido água **nulo** | contagem |
| `municipios_informantes_esgoto` | INTEGER | municípios com atendido esgoto não nulo (**transparência**; não é denominador) | contagem |

- **"Sem serviço" não é razão** — é **diferença absoluta** entre população total
  IBGE-POP e atendida SNIS, com `greatest(…, 0)` **por município** (revisões de
  série podem dar atendido > total: 2010–2021, **água 63 grãos / 387.725 hab /
  0,097%**; **esgoto 11 grãos / 90.404 hab** — imaterial, truncado em 0 na origem,
  `pop_sem_* ≥ 0`).
- **Esgoto = sem coleta por rede (D30):** mede atendimento por **rede coletora**;
  quem usa **fossa séptica** conta como "sem esgoto". O rótulo correto é **"sem
  coleta por rede"**, não "sem saneamento".
- **Água — o absoluto é um PISO:** quem **não informa água** não entra em
  `pop_sem_agua`; vai para `pop_sem_informacao_agua` (**3,13 mi hab em 258
  municípios em 2021**), para o leitor ver o tamanho do que não se sabe.
- **Esgoto pela IN056 (D30):** denominador = informantes de **água**; o branco de
  esgoto vale como **"sem rede"** (2.531 de 2.532 brancos de 2021 com colunas
  físicas de esgoto nulas/zero, D29). A **exceção única da faixa 5 do mart 6** (1
  município informa água, não informa atendido de esgoto e tem infraestrutura
  física) é missing isolado — aqui entra como "sem esgoto" (efeito desprezível).
- **Anos:** 2010–2021. Universo = `silver.ibge_dtb_municipio`; **5.570 municípios**
  com pop na janela (5101837 Boa Esperança do Norte/MT, D12, fora; 0 pop nula).
- **Fontes:** **IBGE-POP**; SNIS; **IBGE-DTB**.
- **Aceite (confirmado no SELECT/MCP, 2026-11-08):** **27 × 12 = 324 linhas**, PK
  `(ano, sigla_uf)` sem duplicatas; identidade `municipios_informantes_agua +
  municipios_sem_informacao_agua = municípios da UF no ano`; `Σpop_total_ibge` por
  ano = estimativa IBGE Brasil (2021 = **213.317.639**). **Nacional 2021:** sem
  água **33,29 mi (15,84% ≈ 100 − IN055 84,2)**; sem esgoto **92,88 mi (44,19% =
  100 − IN056 55,81)**. Percentual nacional confere com o oficial; o absoluto
  oficial citado pela imprensa ("≈100 mi") é **não reconciliado** (base
  desconhecida — 44,2% de 213,3 mi ≈ 94 mi), **sem causa atribuída**.
- **Topo 2021 (confirmado):** maior **pct_sem_esgoto** no Norte — **RO 93,9%, AP
  93,2%, PA 91,9%**; maior **pct_sem_agua** — **AP 67,1%, RO 54,0%, PA 51,8%**.
  Maior absoluto de esgoto: **BA, RS, PA, PE, CE**.

---

### Mart 8 — `gold.investimento_per_capita_uf_ano`

- **Pergunta:** quanto se investe por habitante, por UF e ano?
- **Grão:** uma linha = **(ano, UF)**.
- **Chave primária:** `(ano, sigla_uf)`. **FKs:** SNIS `(ano, id_municipio)`;
  IBGE-POP `(ano, id_municipio)`; DTB `id_municipio` → UF/região.

**Colunas:**

| Coluna | Tipo | Descrição | Unidade |
|---|---|---|---|
| `ano` | INTEGER | 2010–2021 | — |
| `sigla_uf`, `nome_uf`, `nome_regiao` | VARCHAR | DTB | — |
| `investimento_per_capita_com_atipicos` | DECIMAL | **D31:** `Σinvestimento_total_prestador / nullif(Σpopulacao_total_ibge,0)` **no universo comum** (municípios com investimento e pop IBGE não nulos — "entre os que declararam investimento") | R$/hab (nominal) |
| `investimento_per_capita_sem_atipicos` | DECIMAL | idem, **excluindo** os municípios com flag `investimento_atipico` (mesmo universo comum, num e den) | R$/hab (nominal) |
| `investimento_total` | DECIMAL | **transparência:** `Σinvestimento_total_prestador` no universo comum (numerador do per capita) — igual ao `investimento_total` do mart 5 por `(ano, sigla_uf)` | R$ (nominal) |
| `investimento_total_sem_atipicos` | DECIMAL | **transparência:** idem, **excluindo** os atípicos — igual ao do mart 5 por `(ano, sigla_uf)` | R$ (nominal) |
| `pop_informante_investimento` | DECIMAL | **transparência:** `Σpopulacao_total_ibge` do universo comum (denominador do per capita) | hab |
| `municipios_informantes` | INTEGER | municípios com investimento e pop. IBGE não nulos (universo comum) | contagem |
| `municipios_investimento_atipico` | INTEGER | municípios com a flag D4/D28, por grão | contagem |
| `valor_nominal` | BOOLEAN | sempre `true` | — |

- **Regra D4/D28 (investimento atípico):** flag `investimento_atipico` quando o
  **investimento per capita do município > R$ 1.000/hab** (limiar **nominal**;
  = p99,8 com pop IBGE). **Mesma regra e mesmo nome do mart 5** (replicada
  exatamente). Os atípicos **permanecem** na coluna `…_com_atipicos` (total fiel
  por UF) e **saem** da coluna `…_sem_atipicos`. **Nota de UF obrigatória:**
  destacar **RN** (−29% do total se os atípicos fossem excluídos; D28); citar
  MA/SE/PE. Limiar como **constante nomeada** no SQL/executor. Hipótese de
  prestador regional é **hipótese, não fato** (sem coluna de prestador na silver).
- **Denominador (D31):** **população total IBGE-POP do universo comum** —
  municípios com investimento **e** pop IBGE não nulos. O per capita é **"entre os
  municípios que declararam investimento"**. **Caveat do branco:** a consulta
  mostra que o nulo de investimento é majoritariamente de município que informou o
  SNIS (tem despesa/receita) e deixou o investimento em branco, mas **não decide**
  se o nulo é "zero investido" ou "não declarado" (não há coluna física que
  resolva; há 423 zeros declarados em 2021 — indício, não prova). **Sensibilidade
  2021:** R$ **75,82/hab** (universo comum) contra R$ **71,71/hab** se todo nulo
  fosse zero (−5,4%) — registrada aqui, **não vira coluna**.
- **Comparação externa (não reconciliada):** gráfico do Senado (ano-base SNIS
  2021) mostra **R$ 82,71/hab**; o mart dá **R$ 75,82/hab** (−8,3%). Registrado
  como **não reconciliado** (fonte é um gráfico, vale só como ordem de grandeza;
  a diferença de base populacional é **hipótese não testada**, sem causa
  atribuída). Fonte: Senado, doc. `ca46fdf4-bc5e-4ec1-a2ac-2951503d84f8`, acesso
  2026-11-08. A conferência com o mart 5 é **consistência interna** (mesma silver,
  trava a regra do atípico contra deriva) — **não** é validação externa.
- **Anos:** 2010–2021.
- **Fontes:** SNIS (investimento); **IBGE-POP**; **IBGE-DTB**.
- **Regra:** **R$ nominal** (R$/hab por ano, não comparável entre anos sem
  correção); teste de cobertura de junção antes do join.
- **Aceite (confirmado no SELECT, 2026-11-08):** **324 linhas** (27 × 12), **12
  colunas**, PK `(ano, sigla_uf)` sem duplicatas; dims DTB não nulas. Universo =
  **5.570 municípios/ano** (5.565 em 2010 e 2011). `municipios_investimento_atipico`
  nacional 2010–2021 = **120** (D28), série por ano **6, 2, 10, 5, 11, 5, 4, 11,
  10, 48, 3, 5**. Per capita nacional **com atípicos** 44,26 (2010) / 72,17 (2019)
  / 75,82 (2021); **sem atípicos** 42,88 / 61,36 / 75,56. **RN 2019:** 443,38 →
  218,91 R$/hab (−50,6%, 45 atípicos) — deixa de ser o outlier extremo. Diferença
  entre as duas colunas é grande **só em RN** (pico 2019). Conferência cruzada por
  `(ano, sigla_uf)` contra o mart 5: **0 divergências** em `investimento_total`,
  `investimento_total_sem_atipicos` e `municipios_investimento_atipico`.

---

### Mart 9 — `gold.atendimento_vs_pib_2021`

- **Pergunta:** como cobertura, perdas e investimento se relacionam com o **PIB
  per capita** do município em **2021**?
- **Grão:** uma linha = **município**, ano fixo = **2021**.
- **Chave primária:** `(id_municipio)`. **FKs:** SNIS, IBGE-PIB, IBGE-POP, todos
  em `(2021, id_municipio)`; DTB `id_municipio` → UF/região.

**Colunas:**

| Coluna | Tipo | Descrição | Unidade |
|---|---|---|---|
| `id_municipio` | VARCHAR | município | — |
| `sigla_uf`, `nome_uf`, `nome_regiao` | VARCHAR | DTB | — |
| `cobertura_urbana_agua` | DECIMAL | `populacao_urbana_atendida_agua/nullif(populacao_urbana,0) × 100` | % |
| `cobertura_urbana_esgoto` | DECIMAL | `populacao_urbana_atendida_esgoto/nullif(populacao_urbana_residente_esgoto,0) × 100` | % |
| `perdas_in049` | DECIMAL | IN049 do município (fórmula do mart 3) | % |
| `investimento_per_capita` | DECIMAL | `investimento_total_prestador / nullif(populacao_total_ibge,0)` | R$/hab (nominal) |
| `pib_per_capita` | DECIMAL | **`pib_municipio × 1000 / nullif(populacao_total_ibge,0)`** (D15: PIB em Mil Reais → **× 1000** converte para reais na gold) | R$/hab (nominal) |
| `investimento_atipico` | BOOLEAN | flag D4/D28 (per capita > R$ 1.000/hab, nominal) | — |

- **Regra D15 (conversão do PIB):** `pib_municipio` está em **Mil Reais** na
  silver (BIGINT). A conversão para reais acontece **só aqui**, com **comentário
  explícito no SQL** (`-- D15: PIB em Mil Reais; × 1000 = reais`). Sanidade: SP
  (3550308) 2021 `pib_municipio` = 828.980.747 Mil Reais ≈ R$ 828,98 bi.
- **Regra D17 (PIB per capita negativo):** se `pib_per_capita < 0`, ele
  **permanece no dado** e **não recebe transformação logarítmica** (log de ≤ 0 é
  indefinido) — nenhum filtro, nenhum clamp. Caso conhecido: Guamaré/RN
  (`2404507`) teve PIB negativo em 2012 (reavaliar em 2021 na carga).
- **Regra D4/D28:** excluir os atípicos **apenas** de rankings per capita (coluna
  `investimento_per_capita`), via a flag `investimento_atipico`; mart 9 mantém a
  flag visível.
- **Anos:** **2021** (único ano com urbano válido + PIB).
- **Fontes:** SNIS; **IBGE-PIB**; **IBGE-POP**.
- **Aceite:** nº de linhas = municípios com SNIS urbano + PIB + população casados
  em 2021 = **5.302** (confirmado no MCP, água urbana). Correlação ≠ causalidade
  (nota do dashboard).

---

### Mart 10 — `gold.avanco_por_renda_painel`

- **Pergunta:** o atendimento avançou mais entre 2010 e 2021 em municípios de
  **maior ou menor renda**?
- **Grão:** uma linha = **(quartil_pib, ano)**, com **ano ∈ {2010, 2021}**, sobre
  um **painel fixo** de municípios.
- **Chave primária:** `(quartil_pib, ano)`. **FKs:** SNIS, IBGE-PIB, IBGE-POP.

**Painel e quartis (D19):** usa o **painel fixo único** do glossário (seção 3) —
**4.472 municípios** não nulos em `populacao_urbana_atendida_agua` e
`populacao_urbana` nos **12 anos** 2010–2021 (confirmado no MCP), as 27 UFs,
**o mesmo do mart 4**. **Quartil de renda = `ntile(4)` NACIONAL**
sobre `pib_per_capita` de **base 2021** (≈ 1.118 municípios por quartil). **Por
UF é inviável** (DF=1, AM=13, RR=14 — sem massa). Municípios **fora do painel**
não entram (contados no diagnóstico do executor).

**Colunas:**

| Coluna | Tipo | Descrição | Unidade |
|---|---|---|---|
| `quartil_pib` | INTEGER | 1 (menor renda) a 4 (maior), `ntile(4)` nacional sobre pib_per_capita 2021 | — |
| `ano` | INTEGER | 2010 ou 2021 | — |
| `cobertura_urbana_agua` | DECIMAL | `Σpopulacao_urbana_atendida_agua/nullif(Σpopulacao_urbana,0) × 100` no quartil-ano | % |
| `municipios_painel` | INTEGER | municípios do painel no quartil | contagem |
| `variacao_pp` | DECIMAL | (coluna/linha derivada 2021 − 2010 por quartil) | pontos percentuais |

- **Denominador:** cobertura → urbano SNIS; quartil → **PIB per capita
  (IBGE-PIB × 1000 / IBGE-POP)**, base 2021.
- **Regra D17:** PIB per capita negativo **cai naturalmente no 1º quartil**
  (ordenação trata o negativo como menor valor); **sem log**, sem filtro.
- **Anos:** **2010 e 2021**, painel fixo.
- **Fontes:** SNIS; **IBGE-PIB**; **IBGE-POP**.
- **Aceite:** **4 quartis × 2 anos = 8 linhas**. `Σmunicipios_painel` por ano =
  **4.472** (painel fixo). Cada quartil ≈ 1.118 municípios (**chute a confirmar**
  a distribuição exata, que depende de empates no `ntile`).

---

## 3. Glossário da gold (definições fechadas)

Uma definição, uma fórmula e uma fonte por termo.

| Termo | Definição | Fórmula / fonte |
|---|---|---|
| **Município informante** | município com **numerador e denominador do indicador não nulos** no grão (ano/UF/faixa). | `count(*) FILTER (WHERE num IS NOT NULL AND den IS NOT NULL)`; fonte SNIS/IBGE conforme o mart. |
| **População de referência** | população **residente total** do município (urbana+rural), ref. 1º/jul (D14). | `populacao_total_ibge` (IBGE-POP). |
| **População urbana** | subconjunto urbano autodeclarado ao SNIS. | `populacao_urbana` (SNIS). Distinta da de referência. |
| **Ano de referência** | 2021 nos marts urbanos (D2); não se usa 2022 neles. | D2 / [`decisoes.md`](decisoes.md). |
| **Painel fixo** (regra D19 + D24) | **Regra (D19):** município com valor nas **colunas-chave** em **todos os 12 anos de 2010 a 2021**. **Cada família de índices aplica a regra às suas próprias colunas-chave (D24).** **Painel urbano de água** (colunas-chave `populacao_urbana_atendida_agua` e `populacao_urbana`) = **4.472 municípios** (Rodada 3.3), as 27 UFs, usado nos **marts 4 e 10**. **Painel de esgoto** (mart 2, D24): **coleta** (`volume_esgoto_coletado`, `volume_agua_consumido` > 0) = **1.473**; **tratamento** (`volume_esgoto_tratado`, `volume_esgoto_coletado` > 0) = **1.440** (painéis distintos). | silver SNIS; regra definida uma vez aqui. |
| **Linha inconsistente (IN049)** | município com `(AG006+AG018−AG024) < AG010`. | excluída com flag (D3), contada por ano. |
| **Investimento atípico** (D4/D28) | município com investimento per capita > **R$ 1.000/hab** (nominal; = p99,8 com pop IBGE). | flag `investimento_atipico` (marts 5 e 8); hipótese de prestador regional é hipótese, não fato. |
| **População sem água** (mart 7) | déficit absoluto por município entre informantes de água: `Σ greatest(populacao_total_ibge − populacao_atendida_agua, 0)`. Quem não informa água fica fora (vai para `pop_sem_informacao_agua` — o absoluto é um piso). | SNIS/IBGE-POP; `pct_sem_agua = 100 − IN055`. |
| **População sem esgoto** (mart 7, **D30/IN056**) | **sem coleta por rede**: `Σ greatest(populacao_total_ibge − coalesce(populacao_atendida_esgoto,0), 0)` entre os **informantes de ÁGUA** (branco de esgoto = sem rede; fossa séptica conta como sem esgoto). Denominador do percentual = `pop_informante_agua`, **não** informantes de esgoto. A convenção antiga (só informantes de esgoto) é **revogada pela D30**. | SNIS/IBGE-POP; `pct_sem_esgoto = 100 − IN056`. |
| **Perda de água** | IN049 = `(AG006+AG018−AG010−AG024)/(AG006+AG018−AG024)×100`. | SNIS (glossário 2022, D3). |
| **Investimento per capita** | `investimento_total_prestador / populacao_total_ibge`. | SNIS/IBGE-POP; R$ nominal (D4/D14). |
| **Tarifa média** (D22) | `Σreceita_operacional_direta / (Σ(volume_agua_faturado+volume_esgoto_faturado) × 1000)`, R$/m³ nominal. | SNIS (FN001 ÷ (AG011+ES007)). |
| **Despesa unitária** (D22/D27) | `Σdespesa_total_servico / (Σ(volume_agua_faturado+volume_esgoto_faturado) × 1000)`, R$/m³ nominal. | SNIS (**FN017 = DTS = `despesa_total_servico`** ÷ (AG011+ES007)) → IN003. `despesa_exploracao` é FN015/DEX. |
| **Universo comum** (D22) | município com numerador e denominador não nulos **e denominador > 0**. | regra de `municipios_informantes` da tarifa/despesa unitária. |
| **PIB per capita** | `pib_municipio × 1000 / populacao_total_ibge` (Mil Reais→reais na gold). | IBGE-PIB/IBGE-POP; nominal (D15). |
| **Valor nominal** | R$ sem deflação; comparável **só no mesmo ano**. | flag `valor_nominal=true`. |

---

## 4. Executor `pipeline/gold.py`

Mesma arquitetura dos executores existentes
([`pipeline/transformacao.py`](../pipeline/transformacao.py),
[`pipeline/transformacao_ibge.py`](../pipeline/transformacao_ibge.py)):
`conectar()` de [`pipeline/db.py`](../pipeline/db.py), transação única,
`ROLLBACK` + `sys.exit(1)` em erro, saída no mesmo formato das etapas atuais.

**Comportamento:**

1. **Lê `sql/gold/*.sql` em ordem numérica** (01…10) — ordenação pelo prefixo
   `NN`, não pela ordem do sistema de arquivos.
2. Abre **uma transação**; nela: `DROP SCHEMA IF EXISTS gold CASCADE` seguido de
   `CREATE SCHEMA gold`. Em **qualquer erro**: `ROLLBACK` + `sys.exit(1)` (nenhum
   schema parcial fica no banco).
3. **Cada arquivo contém apenas um SELECT (D20).** O executor **compõe** o
   `CREATE TABLE gold.<nome> AS <select-do-arquivo>`, onde `<nome>` é o nome do
   mart derivado do nome do arquivo (`NN_nome.sql` → `gold.<nome>`). O arquivo
   **não** traz `CREATE TABLE`, `DROP`, `BEGIN`/`COMMIT` nem múltiplos statements
   — isso garante a regra "uma tabela por arquivo" num único ponto (o executor).
4. **Validação "exatamente uma tabela por arquivo" (D20):** o executor rejeita
   um arquivo que **não seja um único SELECT** (presença de `;` separando
   statements, ou de `create`/`drop`/`insert`) antes de compor o `CREATE TABLE`.
   Depois de criar, confere que a contagem de tabelas em `gold` **incrementou em
   1** e que a tabela esperada existe. Qualquer desvio → `ROLLBACK` +
   `sys.exit(1)`.
5. **Saída** idêntica às etapas atuais: por tabela, uma linha com **nome,
   nº de linhas, nº de colunas** (ex.:
   `gold.atendimento_uf_ano · 324 linhas · 9 colunas`). Ao final, um bloco de
   **diagnóstico** (municípios fora de painel nos marts 4 e 10;
   `municipios_investimento_atipico` D4/D28; `linhas_inconsistentes_in049` D3).
6. Idempotente (schema recriado), sem colunas de auditoria, `data/raw/` nunca
   tocado, silver nunca alterada (conexão de leitura sobre ela).

**Ordem no [`executar.py`](../executar.py):** SNIS bronze → SNIS silver → IBGE
bronze → IBGE silver → **cobertura** → **gold**. A gold entra como **6º passo**,
depois da cobertura (que já roda em
[`pipeline/cobertura.py`](../pipeline/cobertura.py)); exige as silvers do SNIS e
do IBGE prontas.

### 4.1 Teste do executor com `sql/gold/00_teste.sql`

- `sql/gold/00_teste.sql` = `SELECT 1 AS x`.
- **Cinco critérios de aceite do executor:**
  1. cria `gold.teste` com **1 linha, 1 coluna** (`x = 1`);
  2. o schema `gold` é **recriado** (DROP+CREATE) a cada execução (idempotência);
  3. **um erro de SQL** num arquivo dispara `ROLLBACK` + `sys.exit(1)` e **não
     deixa schema parcial** (nenhuma tabela de `gold` após a falha);
  4. a validação "uma tabela por arquivo" (D20) **falha** se um arquivo não for
     um único SELECT (ex.: contém `;` ou `CREATE`/`DROP`), em cópia temporária;
  5. os arquivos são lidos **em ordem numérica** (um arquivo que dependa da ordem
     confirma a sequência).
- **Regra:** **apagar `sql/gold/00_teste.sql`** depois que o executor estiver
  validado — ele não é mart e não pode ir para a produção da gold.

---

## 5. Testes `tests/test_gold.py`

Estilo dos testes da silver
([`tests/test_ibge_silver.py`](../tests/test_ibge_silver.py)): **banco
temporário** via `tmp_path_factory`, **monkeypatch de
`pipeline.db.CAMINHO_BANCO`**, pipeline completo numa fixture de módulo, e os
**casos bloqueantes em cópias** do banco (`shutil.copy`). Expectativas numéricas
**só no teste**.

| Teste | Mart | Liga ao critério de aceite |
|---|---|---|
| `test_m1_linhas_e_cobertura` | 1 | 324 linhas (27×12); cobertura ∈ [0,100]; água nacional 2021 ≈ 93,4% |
| `test_m1_exclusao_a2` | 1 | `linhas_excluidas_a2` > 0 só onde há violação (D5) |
| `test_m2_28_anos` | 2 | 28 linhas (1995–2022) × 13 colunas; PK única; identidade informantes+excluídas=não nulos; painéis constantes (1.473/1.440) e NULL fora de 2010–2021; `serie_robusta` true ≥ 2006; índices ∈ [0,100] exceto `tratado > coletado` (D23) |
| `test_m3_in049_nacional` | 3 | índice nacional 2010–2021 ∈ [35,41]% (D3); inconsistentes 0–57/ano |
| `test_m4_painel_e_rank` | 4 | 4.431 linhas (painel 4.472 − 41 A2); identidade 4.472=4.431+41; `posicao` 1..N única sem buracos; `posicao_empate` empates compartilham (mín. 1); `variacao_pp ∈ [−100,+100]`; 12 `variacao_extrema`; anos 2010/2021 (nunca 2022); sem `quintil_variacao` (D21, D26) |
| `test_m5_linhas_e_total_br` | 5 | 754 linhas (27×28 − 2: sem 1996-AC/1996-PI); PK única; dims DTB não nulas; `Σinvestimento_total` 27 UFs 2021 = R$ 15.297.535.452,19 |
| `test_m5_total_br_por_ano` | 5 | `investimento_total` Brasil por ano 2010–2021 (conferência cruzada mart 8) |
| `test_m5_tarifa_despesa_unitaria` | 5 | tarifa 2,18 (2010)/4,12 (2021); despesa unitária (DTS/FN017) 2,06/3,87; conversão ÷1.000; soma sobre soma; ≥ 0 (D22/D27) |
| `test_m5_identidades_informantes` | 5 | identidades informantes+excluídos=total (tarifa, despesa, índice), valores obrigatórios não nulos |
| `test_m5_investimento_atipico` | 5 | 120 atípicos na janela; RN −29%; `investimento_total_sem_atipicos ≤ investimento_total` |
| `test_m10_mesmo_painel_do_m4` | 10 | painel (4.472) idêntico ao do mart 4 (D19) |
| `test_m6_faixas_2021` | 6 | 72 linhas (6×12); soma das faixas em 2021 = 5.570 |
| `test_m7_absolutos` | 7 | 324 linhas; `habitantes_sem_*` ≥ 0 e ≤ pop. total |
| `test_m8_flag_d4` | 8 | `municipios_investimento_atipico` nacional = 120 (D28); duas colunas diferem em RN |
| `test_m9_2021_pib` | 9 | 5.302 linhas; PIB per capita negativo preservado, sem log (D17) |
| `test_m10_painel_quartis` | 10 | 8 linhas (4×2); `Σmunicipios_painel`/ano = 4.472 |
| `test_executor_uma_tabela_por_arquivo` | — | critério 4 do executor (seção 4.1) |
| `test_executor_rollback_em_erro` | — | critério 3 do executor (cópia temporária) |

---

## 6. Conferências cruzadas (entre marts e com a silver)

Números que o MCP permitiu confirmar marcados **[confirmado]**; os demais são
**[a confirmar no SELECT]**.

1. **Investimento Brasil = Σ UFs (2021):** `Σinvestimento_total` do mart 5 nas 27
   UFs = **R$ 15.297.535.452,19** [confirmado].
2. **População Brasil IBGE 2021:** `Σpopulacao_total_ibge` 2021 (base dos marts
   6–8) = **213.317.639** hab em **5.570** municípios [confirmado].
3. **Painel fixo único (D19) = 4.472** municípios (não nulos nos 12 anos
   2010–2021), usado nos marts 4 e 10 [confirmado].
4. **Faixas de porte 2021 (mart 6)** somam **5.570** municípios
   (1.250/2.520/1.120/354/277/49) [confirmado].
5. **Exclusões D3 (IN049):** `linhas_inconsistentes_in049` por ano na janela =
   **0–57** (Verificação D3) [a confirmar no SELECT com a fórmula completa].
6. **Exclusões D5 (A2):** `linhas_excluidas_a2` por ano 2010–2021 ≤ ~43 em água
   (Rodada 3.6a) [a confirmar no SELECT].
7. **`municipios_informantes` coerente com a silver:** a soma por ano do mart 1
   deve bater com a contagem de informantes urbanos da Rodada 3.2 (ex.: água
   urbana 2021 ≈ **5.302**) [confirmado parcialmente].
8. **Atípicos D4/D28 (marts 5 e 8):** `Σmunicipios_investimento_atipico`
   2010–2021 = **120** (limiar R$ 1.000/hab; RN −29%) [confirmado no SELECT].

**A definir na aula 4 (dashboard):**

- **C9** — soma das coberturas ponderadas por região bate com o agregado Brasil
  (reconciliação região×UF no dashboard).
- **C10** — série de perdas (mart 3) × série financeira (mart 5) consistentes no
  mesmo recorte de anos exibido no painel.

---

## 7. Revisão pela IA (MCP somente leitura) — alvo: **mart 4 (ranking)**

O mart 4 é o alvo da revisão de **grão** porque concentra os riscos: painel
fixo, dois anos, window function e exclusão A2. Roteiro do que perguntar ao MCP
(somente leitura, sem alterar dado):

1. **Grão:** `SELECT id_municipio, count(*) FROM gold.ranking_atendimento_variacao
   GROUP BY 1 HAVING count(*) > 1` — deve voltar **vazio** (uma linha por
   município).
2. **Painel:** o nº de linhas = municípios com `populacao_urbana_atendida_agua` e
   `populacao_urbana` não nulos em **2010 e 2021** (≈4.843) **menos** os
   excluídos por A2. Conferir a diferença.
3. **Ranking:** `posicao` de 1 a N sem buracos nem empates mal resolvidos;
   `variacao_pp = cobertura_2021 − cobertura_2010` para uma amostra.
4. **Sem 2022:** nenhuma linha usa 2022 (D2).
5. **Fora do painel:** municípios presentes só em um dos anos **não** aparecem.

---

## 8. Suposições, pontos "a confirmar" e decisões que dependem de você

**Suposições da spec (sinalizadas, não resolvidas sozinho):**

- Nomes de coluna dos marts (ex.: `cobertura_urbana_agua`) são **propostos**;
  seguir o padrão de [`indicadores.md`](indicadores.md) ao implementar.
- O executor **compõe** o `CREATE TABLE` e o arquivo traz **só o SELECT**
  (D20, seção 4) — decidido.
- Marts 4 e 10 usam o **mesmo painel fixo único (4.472)** (D19, glossário) —
  decidido.
- **Denominador de `tarifa_media`/`despesa_unitaria`**: **fechado por D22**
  (verificado nos dados): `volume_agua_faturado + volume_esgoto_faturado`
  (AG011+ES007), R$/m³ com ÷1.000, valores nominais.

**Itens do dicionário SNIS ainda pendentes (de [`decisoes.md`](decisoes.md) e
[`indicadores.md`](indicadores.md)):**

- **IN049 / "volume disponibilizado":** a spec usa a fórmula completa confirmada
  no glossário 2022 (D3). Se algum código (AG006/AG018/AG010/AG024) divergir ao
  escrever o SQL, **reabrir D3** (não resolver sozinho).
- ~~**Semântica das colunas de população do SNIS**~~ — **RESOLVIDO (D25):**
  `populacao_atendida_agua` é **total atendida (urbana + rural)** — acima da
  `populacao_urbana` (razão mediana 1,026) e ≈ 76% da `populacao_total_ibge`
  (razão mediana 0,757) em 2021. Afeta a leitura dos marts 3, 6 e 7.
- **Investimento e receita** (prestador vs. município vs. estado; direta vs.
  indireta) — semântica fina a confirmar para os marts 5 e 8.
- **Classificação percentual × taxa** dos `indice_*` — quais têm teto 100.

**Decisões que dependem de você:** **nenhuma em aberto** — D18–D22 fecharam
tarifa/despesa unitária (mart 5, denominador e unidade **verificados nos dados**,
D22), painel único, forma do arquivo SQL e o mart 4 sem quintil. Restam apenas os
**itens gerais de dicionário SNIS** acima (semântica de população, investimento/
receita, percentual×taxa), que não bloqueiam a implementação.

**Conflitos com decisões aprovadas:** **nenhum detectado.** A spec aplica D1–D17
como estão. Se, ao escrever o SQL, algum código do glossário do IN049 divergir de
D3, isso é um **conflito a listar** (reabrir D3), não a resolver aqui.

---

## 9. Checklist de entrega da gold (quando for implementar)

- [ ] `sql/gold/01…10_*.sql` — um SELECT por mart, nomes e fórmulas desta spec.
- [ ] `pipeline/gold.py` — executor (seção 4), constantes nomeadas (limiar D4
      R$ 1.000/hab, anos de painel, janela 2010–2021).
- [ ] `tests/test_gold.py` — os testes da seção 5.
- [ ] `executar.py` — gold como 6º passo (após cobertura).
- [ ] `sql/gold/00_teste.sql` **apagado** após validar o executor.
- [ ] comentário D15 (× 1000) nos marts 9 e 10; flag `valor_nominal` no mart 8
      (mart 5 traz a ressalva nominal na ficha, sem coluna constante); nota de RN
      nos marts 5 e 8; flag D4/D28 com o mesmo nome `investimento_atipico`.

---

## 10. O que foi escrito (resumo)

- **Fundamentos e convenções** (seção 1): schema `gold`, `sql/gold/NN_nome.sql`,
  10 regras globais, universos de denominador (D14).
- **10 fichas de mart** (seção 2) com as três perguntas, colunas+tipos+unidades,
  fórmulas exatas, regras D2/D3/D4/D5/D15/D16/D17 **e D18–D22** e critérios de
  aceite.
- **Glossário** (seção 3), **executor + teste** (seção 4), **testes** (seção 5),
  **6+ conferências cruzadas + 2 para a aula 4** (seção 6), **revisão do mart 4
  via MCP** (seção 7), **suposições/pendências/decisões** (seção 8).

### Critérios de aceite que ficaram "chute a confirmar"

| Mart | O que falta confirmar no SELECT |
|---|---|
| 1 | ~~soma de `municipios_informantes_agua` (≈5.302 em 2021)~~ **CONFIRMADO: 5.284 em 2021 (5.302 − 18 A2); 324 linhas; água BR 2021 = 93,33%** |
| 2 | ~~perfil de `municipios_informantes` por ano~~ **CONFIRMADO: 28 linhas × 13 colunas; coleta 20→3.051, tratamento 19→2.897 (universo comum); índice coleta 2021≈56%, tratamento 2021≈80,3%; painéis esgoto 1.473 (coleta)/1.440 (tratamento); `serie_robusta` true ≥ 2006** |
| 3 | ~~nº de linhas e inconsistentes~~ **CONFIRMADO: 754 linhas (756 − 2 pares iniciais); perdas ∈ [0; 94,48]; índice nacional 2010–21 = 37,42%; consumo per capita 2021 = 151,3 L/hab·dia (IN022, D25); `excluidas_consumo_acima` 0–57/ano; único extremo Vilhena/RO 1997** |
| 4 | ~~nº de linhas = painel fixo único (4.472) menos A2~~ **CONFIRMADO: 4.431 linhas × 10 colunas = painel 4.472 − 41 A2 (26 em 2010, 16 em 2021); PK única; posicao 1..4.431 sem buracos; posicao_empate 1..4.429; variacao_pp ∈ [−100,+100]; 12 variacao_extrema; D26** |
| 5 | ~~nº de linhas (≤ 756) nos anos iniciais~~ **CONFIRMADO: 754 linhas × 16 colunas (756 − 2: sem 1996-AC/1996-PI); PK única; tarifa 2,18→4,12; despesa unitária (DTS/FN017, D27) 2,06→3,87; investimento BR 2021 = R$ 15.297.535.452,19; 120 atípicos (D28, RN −29%); extremos de tarifa/despesa só em 1995–2000** |
| 6 | perfil de cobertura por faixa |
| 7 | `habitantes_sem_*` por UF |
| 8 | per capita por UF; `municipios_investimento_atipico` = 120 (D28) |
| 9 | reavaliar PIB per capita negativo em 2021 (Guamaré/RN) |
| 10 | distribuição exata dos quartis (empates no `ntile`) |

### Decisões que dependem de você

**Nenhuma decisão em aberto.** D18–D22 fecharam os pontos antes pendentes
(tarifa/despesa unitária no mart 5 — denominador e unidade **verificados nos
dados**, D22; painel fixo único; arquivo SQL só com SELECT; mart 4 sem quintil).
Restam apenas itens gerais de dicionário SNIS, que não bloqueiam a implementação.

---

## 11. Fatos confirmados no MCP (somente leitura, 2026-11-08)

| Fato | Valor |
|---|---|
| UFs distintas (silver SNIS) | 27 |
| Anos (silver SNIS) | 28 (1995–2022) |
| Mart 1/3/5/7/8 — pares UF×ano com dado urbano 2010–2021 | 324 (27×12) |
| População total IBGE 2021 (Brasil) | 213.317.639 hab, 5.570 municípios |
| Faixas de porte 2021 (mart 6) | 1.250/2.520/1.120/354/277/49 = 5.570 |
| Painel fixo único (12 anos, não nulos; marts 4 e 10) | 4.472 |
| Mart 9 (2021, SNIS urbano + PIB + pop casados) | 5.302 |
| Mart 2 — anos com volumes | 28 (1995–2022) |
| Investimento total Brasil 2021 (mart 5) | R$ 15.297.535.452,19 |
| Mart 5 — linhas / tarifa 2010→2021 / despesa unit. DTS 2010→2021 | 754 / 2,18→4,12 / 2,06→3,87 R$/m³ |
| Mart 5 — municípios atípicos 2010–2021 (R$ 1.000/hab, D28) | 120 (RN −29%; pico 2019 = 48, 45 em RN) |
| Mart 8 — per capita nacional com/sem atípicos 2010/2019/2021 (D31) | com 44,26/72,17/75,82 · sem 42,88/61,36/75,56 R$/hab |
| Mart 8 — RN 2019 (com→sem atípicos) / vs todos os 5.570 em 2021 | 443,38→218,91 R$/hab · 75,82 (comum) vs 71,71 (todos, −5,4%) |

## 12. Consultas MCP usadas (referência)

```sql
-- UFs/anos
SELECT count(DISTINCT sigla_uf), count(DISTINCT ano), min(ano), max(ano)
FROM silver.municipio_agua_esgoto;

-- pares UF×ano com urbano (2010–2021)
SELECT count(*) FROM (SELECT ano, sigla_uf FROM silver.municipio_agua_esgoto
  WHERE ano BETWEEN 2010 AND 2021 AND populacao_urbana IS NOT NULL
    AND populacao_urbana_atendida_agua IS NOT NULL GROUP BY ano, sigla_uf);

-- população e municípios IBGE 2021
SELECT sum(populacao_total_ibge), count(*) FROM silver.ibge_populacao_municipio
WHERE ano = 2021;

-- faixas de porte 2021 (D16)
SELECT CASE WHEN populacao_total_ibge<5000 THEN '1' WHEN populacao_total_ibge<20000 THEN '2'
  WHEN populacao_total_ibge<50000 THEN '3' WHEN populacao_total_ibge<100000 THEN '4'
  WHEN populacao_total_ibge<500000 THEN '5' ELSE '6' END, count(*)
FROM silver.ibge_populacao_municipio WHERE ano=2021 AND populacao_total_ibge IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- painel 12 anos (mart 10)
SELECT count(*) FROM (SELECT id_municipio FROM silver.municipio_agua_esgoto
  WHERE ano BETWEEN 2010 AND 2021 AND populacao_urbana_atendida_agua IS NOT NULL
    AND populacao_urbana IS NOT NULL GROUP BY id_municipio HAVING count(DISTINCT ano)=12);

-- mart 9 (2021, três fontes casadas)
SELECT count(*) FROM silver.municipio_agua_esgoto s
  JOIN silver.ibge_populacao_municipio p ON p.id_municipio=s.id_municipio AND p.ano=s.ano
  JOIN silver.ibge_pib_municipio b ON b.id_municipio=s.id_municipio AND b.ano=s.ano
  WHERE s.ano=2021 AND s.populacao_urbana IS NOT NULL
    AND s.populacao_urbana_atendida_agua IS NOT NULL
    AND p.populacao_total_ibge IS NOT NULL AND b.pib_municipio IS NOT NULL;

-- investimento total Brasil 2021 (mart 5)
SELECT sum(investimento_total_prestador) FROM silver.municipio_agua_esgoto WHERE ano=2021;
```
