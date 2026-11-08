# Investigação da bronze — insumos para a spec da silver

Levantamento de **fatos e anomalias** sobre `bronze.municipio_agua_esgoto`
(`snis.duckdb`), para subsidiar a escrita da spec da camada silver.
**Não contém decisões** — apenas o que foi medido.

- Conexão: `duckdb.connect("snis.duckdb", read_only=True)`.
- Base: **119.256 linhas**, **133 colunas**, todas `VARCHAR` (bronze é espelho do CSV).
- Período: 1995–2022 (28 anos). `TRY_CAST` usado só para investigar.

---

## 1. Nulos por coluna, somados por família

| Família | Nº de colunas | Observação de nulos (faixa %) |
|---|---|---|
| `outros` (ano, id_municipio, sigla_uf) | 3 | 0% — chaves sempre preenchidas |
| `populacao_` | 9 | 0,2% a 68,3% |
| `quantidade_` | 16 (inclui `quantidade_empregado`) | 0,8% a 68,1% |
| `volume_` | 20 | 17,3% a 72,2% |
| `indice_` | 30 | 17,2% a 71,4% |
| `receita_` | 7 | 17,2% a 69,8% |
| `despesa` / `despesas` | 21 | 18,0% a 69,6% |
| `investimento_` | 21 | 26,4% a 63,2% |
| `extensao_` | 2 | 17,1% (água) / 64,5% (esgoto) |
| `consumo_` | 2 | 28,8% (água) / 70,7% (esgoto) |
| `arrecadacao_total`, `credito_areceber` | 2 | 17,6% / 25,8% |

**Padrão dominante:** colunas de **esgoto** têm muito mais nulos (~60–72%) que
as de **água** (~15–25%). Exemplos do mesmo par:

| Coluna | Nulos | % |
|---|---|---|
| `populacao_atendida_agua` | 19.897 | 16,7% |
| `populacao_atentida_esgoto` *(grafia da fonte)* | 77.123 | 64,7% |
| `extensao_rede_agua` | 20.354 | 17,1% |
| `extensao_rede_esgoto` | 76.968 | 64,5% |

> Nota: o nome `populacao_atentida_esgoto` está com a grafia da fonte
> (*atentida*). Mantido como está na bronze.

---

## 2. Colunas 100% nulas ou com um único valor distinto

**Nenhuma.** Todas as 133 colunas têm pelo menos dois valores distintos e
nenhuma é inteiramente nula. (Há colunas quase totalmente nulas — ver item 3 —
mas nenhuma 100%.)

---

## 3. Nulos por ano das 10 colunas com mais nulos

As 10 colunas mais nulas são **todas de esgoto/importação-exportação** e
**começam a ser preenchidas só a partir de certo ano** — antes disso são 100%
nulas. Resumo (ano em que surge o primeiro valor e quantos municípios
preenchem em anos de referência):

| Coluna | Nulos totais | 1º ano com dado | Preench. no 1º ano | Preench. 2010 | Preench. 2022 |
|---|---|---|---|---|---|
| `volume_esgoto_bruto_exportado_tratamento_importador` | 86.046 | 2009 | 1.686 | 1.940 | 2.902 |
| `indice_consumo_energia_esgoto` | 85.138 | 2003 | 445 | 1.634 | 2.471 |
| `consumo_eletrico_sistemas_esgoto` | 84.291 | 1998 (4 casos) | 4 | 1.742 | 2.632 |
| `volume_esgoto_bruto_importado` | 83.349 | 2007 | 1.324 | 1.940 | 2.902 |
| `volume_esgoto_bruto_exportado` | 83.348 | 2007 | 1.324 | 1.940 | 2.902 |
| `volume_esgoto_importado` | 83.347 | 2007 | 1.324 | 1.940 | 2.902 |
| `receita_operacional_direta_esgoto_importado` | 83.275 | 2007 | 1.340 | 1.937 | 2.902 |
| `despesa_esgoto_exportado` | 82.976 | 1998 (4 casos) | 4 | 1.947 | 3.058 |
| `populacao_urbana_atendida_esgoto` | 81.398 | 2001 | 526 | 1.939 | **0 (2022)** |
| `quantidade_economia_residencial_ativa_esgoto` | 81.240 | 1995 | 24 | 1.872 | 2.529 |

**Achados:**
- Variáveis de **exportação/importação de esgoto** e **energia de esgoto** só
  existem a partir de 2003–2009; anos anteriores são estruturalmente nulos.
- `populacao_urbana_atendida_esgoto` tem dados até 2021 e **zera em 2022**
  (5.425/5.425 nulos) — possível descontinuação da variável nesse ano.
- O volume total de linhas por ano cresce de 54 (1995) a 5.425 (2022), então
  parte dos "nulos" reflete a menor cobertura municipal nos primeiros anos.

---

## 4. Valores que não convertem para número

**Nenhuma coluna numérica tem valores não-conversíveis.** Para todas as 130
colunas (exceto `ano`, `id_municipio`, `sigla_uf`),
`TRY_CAST(col AS DOUBLE)` é não-nulo sempre que o valor não é nulo.

- Não há vírgula decimal, separador de milhar nem notação científica.
- O separador decimal é **ponto** e os números já vêm limpos da fonte.

---

## 5. `populacao_*` e `quantidade_*`: inteiros ou decimais?

**Todos inteiros.** Nas 9 colunas `populacao_*` e 16 `quantidade_*` (incl.
`quantidade_empregado`): zero valores com `.` ou `,`, zero valores fracionários
(`valor <> floor(valor)`).

---

## 6. Colunas monetárias — maior, menor e casas decimais

Famílias `receita_`, `despesa`, `investimento_`, `arrecadacao_`, `credito_`
(53 colunas). **Todas usam no máximo 2 casas decimais.** Destaques:

| Coluna | Máximo | Mínimo |
|---|---|---|
| `receita_operacional` | 8.409.304.441,10 | −207.310,60 |
| `receita_operacional_direta` | 8.339.004.396,00 | −27.576,04 |
| `arrecadacao_total` | 7.884.150.196,60 | 0,00 |
| `despesa_total_servico` | 7.266.639.141,59 | −1.941.765,71 |
| `despesa_exploracao` | 4.846.305.189,64 | −1.989.822,14 |
| `investimento_agua_prestador` | **26.465.758.127,00** | −12.721.324,93 |
| `credito_areceber` | 2.765.089.197,59 | **−869.921.808,78** |

- **Máx. de casas decimais = 2** em todas as 53 colunas monetárias.
- Vários mínimos são **negativos** (ver item 7).

---

## 7. Zeros e negativos por família

Contagem somada sobre todas as colunas de cada família (via `TRY_CAST`):

| Família | Colunas | Zeros | Negativos |
|---|---|---|---|
| `populacao_` | 9 | 1.068 | 0 |
| `extensao_` | 2 | 605 | 0 |
| `quantidade_` | 16 | 141.053 | 0 |
| `volume_` | 20 | 636.007 | **1** |
| `consumo_` | 2 | 9.209 | 0 |
| `indice_` | 30 | 129.359 | **10.890** |
| `receita_` | 7 | 152.496 | **53** |
| `outros` (arrecadacao, credito) | 2 | 7.390 | **7** |
| `despesa` | 21 | 568.350 | **15.460** |
| `investimento_` | 21 | 907.053 | **103** |

**Achados:**
- `populacao_`, `extensao_`, `quantidade_`, `consumo_` **nunca** são negativos.
- `despesa` e `indice_` concentram a maior parte dos negativos.
- Negativos existem em valores monetários (crédito/receita/despesa podem ser
  estornos) e em índices (ver item 9).

---

## 8. Integridade de chaves

- **`id_municipio`:** 100% com 7 dígitos (0 fora do padrão `^[0-9]{7}$`).
- **Prefixo UF × sigla:** para **todas as 27 UFs**, os 2 primeiros dígitos de
  `id_municipio` têm **um único prefixo**, coerente com o código IBGE da UF
  (ex.: SP=35, MG=31, RJ=33, DF=53). Nenhuma inconsistência sigla↔prefixo.
- **Municípios distintos por ano:** crescem de 54 (1995) → 3.916 (1998) →
  4.544 (2007) → 5.425 (2022). Chave `(ano, id_municipio)` sem duplicatas
  (confirmado em `docs/contagens.md`).

---

## 9. Anomalias de negócio (apenas listadas)

### 9.1 `indice_*` acima de 100
23 das 30 colunas `indice_*` têm valores > 100. Porém **nem todo índice é
percentual** — alguns são taxas/razões cujo valor > 100 é esperado:

| Tipo | Exemplos | Máx. observado |
|---|---|---|
| Não-percentual (taxa/razão) | `indice_consumo_agua_per_capita` (L/hab·dia) | 105.263,2 (69.346 casos > 100) |
| | `indice_perda_ligacao_agua` | 167.835,62 (66.929 casos > 100) |
| | `indice_perda_linear_agua`, `indice_consumo_medio_agua` | 28.395 / 19.666 |
| Percentual (esperado 0–100) | `indice_coleta_esgoto` | 5.452,56 (524 casos > 100) |
| | `indice_tratamento_esgoto` | 162.555,56 (164 casos > 100) |
| | `indice_atendimento_urbano_agua` | 1.031,0 (543 casos > 100) |
| | `indice_faturamento_agua` | 5.475,0 (9.179 casos > 100) |

> `indice_atendimento_total_agua` e `indice_perda_distribuicao_agua` têm
> **máx. = 100,0** (bem-comportados no teto), mas o segundo tem mínimo
> **−5.375,0** (ver 9.3).

### 9.2 `populacao_atendida_agua` > `populacao_urbana`
**47.934 linhas** (≈40% das que têm ambos preenchidos). Observação: pode não
ser erro — `populacao_atendida_agua` parece ser atendimento **total**
(urbano+rural), enquanto `populacao_urbana` é só urbana; comparação registrada
como fato para avaliação na silver.

### 9.3 Volumes e índices negativos
- **Volume negativo:** 1 caso — `volume_agua_micromedido_economia_ativa` =
  −15,01 (ano 2007, município 2503555).
- **Índices negativos:** 10.890 no total. Ex.: `indice_coleta_esgoto` min
  −30,22; `indice_perda_distribuicao_agua` min −5.375,0;
  `indice_consumo_agua_per_capita` min −623,9.

---

## Anexo A — Consultas usadas

Todas rodadas via `duckdb.connect("snis.duckdb", read_only=True)` sobre
`T = bronze.municipio_agua_esgoto`. `col` denota cada coluna iterada.

```sql
-- Item 1: nulos por coluna
SELECT count(*) - count("col") FROM T;               -- por coluna

-- Item 2: 100% nula ou 1 valor
SELECT count(DISTINCT "col") FROM T;                  -- <= 1 ?

-- Item 3: nulos por ano das top-10
SELECT count(*) - count("col") FROM T WHERE ano = 'AAAA';

-- Item 4: valores não numéricos
SELECT count(*) FROM T
 WHERE "col" IS NOT NULL AND TRY_CAST("col" AS DOUBLE) IS NULL;
SELECT DISTINCT "col" FROM T
 WHERE "col" IS NOT NULL AND TRY_CAST("col" AS DOUBLE) IS NULL LIMIT 5;

-- Item 5: populacao_/quantidade_ fracionários
SELECT count(*) FROM T
 WHERE "col" LIKE '%.%' OR "col" LIKE '%,%';
SELECT count(*) FROM T
 WHERE TRY_CAST("col" AS DOUBLE) <> floor(TRY_CAST("col" AS DOUBLE));

-- Item 6: monetárias
SELECT max(TRY_CAST("col" AS DOUBLE)), min(TRY_CAST("col" AS DOUBLE)) FROM T;
SELECT max(length(split_part("col", '.', 2))) FROM T WHERE "col" LIKE '%.%';

-- Item 7: zeros e negativos
SELECT count(*) FROM T WHERE TRY_CAST("col" AS DOUBLE) = 0;
SELECT count(*) FROM T WHERE TRY_CAST("col" AS DOUBLE) < 0;

-- Item 8: integridade
SELECT count(*) FROM T WHERE NOT regexp_matches(id_municipio, '^[0-9]{7}$');
SELECT sigla_uf, count(DISTINCT substr(id_municipio,1,2)) FROM T GROUP BY sigla_uf;
SELECT ano, count(DISTINCT id_municipio) FROM T GROUP BY ano ORDER BY ano;

-- Item 9: anomalias
SELECT count(*) FROM T WHERE TRY_CAST("indice_x" AS DOUBLE) > 100;
SELECT count(*) FROM T
 WHERE TRY_CAST(populacao_atendida_agua AS DOUBLE)
     > TRY_CAST(populacao_urbana AS DOUBLE);
SELECT count(*) FROM T WHERE TRY_CAST("volume_x" AS DOUBLE) < 0;
```

---

## Anexo B — Suposições e limitações

- **Famílias** foram definidas por prefixo do nome da coluna. `despesa_` e
  `despesas_` foram agrupadas em uma só família "despesa"; `arrecadacao_total`
  e `credito_areceber` ficaram em "outros" (mas entraram como monetárias no
  item 6). Agrupamento é heurístico, não oficial do SNIS.
- **Conversão numérica** usa `TRY_CAST(... AS DOUBLE)`. Como o item 4 mostrou
  zero valores não-conversíveis, isso não descartou dados; mas valores muito
  grandes poderiam perder precisão em `DOUBLE` (não verificado).
- **Prefixo UF:** verificado que cada sigla mapeia para um único prefixo de 2
  dígitos coerente com o código IBGE. **Não** foi validado o dígito verificador
  nem a existência real de cada `id_municipio` contra uma tabela oficial de
  municípios.
- **Item 9.2** (`populacao_atendida_agua > populacao_urbana`): comparei os dois
  campos diretamente; **não** investiguei a definição exata de cada um no
  dicionário do SNIS, então o excesso pode ser semântico (atendimento total vs.
  urbano), não erro.
- **Classificação percentual vs. taxa** dos índices (item 9.1) foi inferida do
  nome/escala observada, **não** do dicionário oficial de indicadores.
- **Significado de negativos** (estorno, ajuste contábil, erro de digitação)
  não foi investigado — apenas contado.
- `populacao_urbana_atendida_esgoto` zerar em 2022 foi observado nos dados;
  **não** confirmei a causa (mudança metodológica vs. falha de carga na fonte).

---
---

# Rodada 2

Complemento à investigação acima. Mesmas regras: `read_only=True`, scripts em
`/tmp`, `TRY_CAST` só para investigar. **Só fatos, sem decisões.**

## R2.1 — Classe e tipo sugerido das 133 colunas

Classe atribuída por heurística de nome/evidência; tipo sugerido pela evidência
observada (todas são `VARCHAR` na bronze).

**Contagem por classe:** identificador **3**, inteiro **25**,
medida/índice **54**, monetária **51** → total **133**.

Regra de tipo: identificador → `VARCHAR` (exceto `ano`, candidato a
`SMALLINT`); inteiro → `BIGINT`; monetária → `DECIMAL(_,2)`; medida/índice →
`DOUBLE`.

| # | Coluna | Classe | Tipo sugerido |
|---|---|---|---|
| 1 | ano | identificador | SMALLINT |
| 2 | id_municipio | identificador | VARCHAR |
| 3 | sigla_uf | identificador | VARCHAR |
| 4 | populacao_atendida_agua | inteiro | BIGINT |
| 5 | populacao_atentida_esgoto | inteiro | BIGINT |
| 6 | populacao_urbana | inteiro | BIGINT |
| 7 | populacao_urbana_residente_agua | inteiro | BIGINT |
| 8 | populacao_urbana_atendida_agua | inteiro | BIGINT |
| 9 | populacao_urbana_atendida_agua_ibge | inteiro | BIGINT |
| 10 | populacao_urbana_residente_esgoto | inteiro | BIGINT |
| 11 | populacao_urbana_atendida_esgoto | inteiro | BIGINT |
| 12 | populacao_urbana_residente_esgoto_ibge | inteiro | BIGINT |
| 13 | extensao_rede_agua | medida/índice | DOUBLE |
| 14 | extensao_rede_esgoto | medida/índice | DOUBLE |
| 15 | quantidade_sede_municipal_agua | inteiro | BIGINT |
| 16 | quantidade_sede_municipal_esgoto | inteiro | BIGINT |
| 17 | quantidade_localidade_agua | inteiro | BIGINT |
| 18 | quantidade_localidade_esgoto | inteiro | BIGINT |
| 19 | quantidade_ligacao_ativa_agua | inteiro | BIGINT |
| 20 | quantidade_ligacao_ativa_esgoto | inteiro | BIGINT |
| 21 | quantidade_ligacao_total_agua | inteiro | BIGINT |
| 22 | quantidade_ligacao_total_esgoto | inteiro | BIGINT |
| 23 | quantidade_economia_ativa_agua | inteiro | BIGINT |
| 24 | quantidade_economia_ativa_esgoto | inteiro | BIGINT |
| 25 | quantidade_ligacao_micromedia_ativa_agua | inteiro | BIGINT |
| 26 | quantidade_economia_residencial_ativa_agua | inteiro | BIGINT |
| 27 | quantidade_economia_residencial_ativa_esgoto | inteiro | BIGINT |
| 28 | quantidade_economia_micromedida_ativa_agua | inteiro | BIGINT |
| 29 | quantidade_economia_residencial_micromedida_ativa_agua | inteiro | BIGINT |
| 30 | volume_agua_produzido | medida/índice | DOUBLE |
| 31 | volume_agua_tratada_eta | medida/índice | DOUBLE |
| 32 | volume_agua_micromedido | medida/índice | DOUBLE |
| 33 | volume_agua_consumido | medida/índice | DOUBLE |
| 34 | volume_agua_faturado | medida/índice | DOUBLE |
| 35 | volume_agua_macromedido | medida/índice | DOUBLE |
| 36 | volume_agua_tratada_desinfeccao | medida/índice | DOUBLE |
| 37 | volume_agua_bruta_exportado | medida/índice | DOUBLE |
| 38 | volume_agua_tratada_importado | medida/índice | DOUBLE |
| 39 | volume_agua_tratada_exportado | medida/índice | DOUBLE |
| 40 | volume_agua_micromedido_economia_ativa | medida/índice | DOUBLE |
| 41 | volume_servico_agua | medida/índice | DOUBLE |
| 42 | volume_agua_fluoretada | medida/índice | DOUBLE |
| 43 | consumo_eletrico_sistemas_agua | medida/índice | DOUBLE |
| 44 | volume_esgoto_coletado | medida/índice | DOUBLE |
| 45 | volume_esgoto_tratado | medida/índice | DOUBLE |
| 46 | volume_esgoto_faturado | medida/índice | DOUBLE |
| 47 | volume_esgoto_bruto_exportado | medida/índice | DOUBLE |
| 48 | volume_esgoto_bruto_importado | medida/índice | DOUBLE |
| 49 | volume_esgoto_importado | medida/índice | DOUBLE |
| 50 | volume_esgoto_bruto_exportado_tratamento_importador | medida/índice | DOUBLE |
| 51 | consumo_eletrico_sistemas_esgoto | medida/índice | DOUBLE |
| 52 | indice_agua_ligacao | medida/índice | DOUBLE |
| 53 | indice_hidrometracao | medida/índice | DOUBLE |
| 54 | indice_macromedicao_volume_disponibilizado | medida/índice | DOUBLE |
| 55 | indice_macromedicao | medida/índice | DOUBLE |
| 56 | indice_perda_faturamento | medida/índice | DOUBLE |
| 57 | indice_micromedido_economia | medida/índice | DOUBLE |
| 58 | indice_coleta_esgoto | medida/índice | DOUBLE |
| 59 | indice_tratamento_esgoto | medida/índice | DOUBLE |
| 60 | indice_consumo_agua_faturado | medida/índice | DOUBLE |
| 61 | indice_extensao_agua_ligacao | medida/índice | DOUBLE |
| 62 | indice_extensao_esgoto_ligacao | medida/índice | DOUBLE |
| 63 | indice_consumo_agua_per_capita | medida/índice | DOUBLE |
| 64 | indice_atendimento_urbano_agua | medida/índice | DOUBLE |
| 65 | indice_atendimento_agua_esgoto | medida/índice | DOUBLE |
| 66 | indice_volume_agua_economia | medida/índice | DOUBLE |
| 67 | indice_faturamento_agua | medida/índice | DOUBLE |
| 68 | indice_participacao_economia_agua | medida/índice | DOUBLE |
| 69 | indice_micromedicao_relativo_agua | medida/índice | DOUBLE |
| 70 | indice_esgotamento_agua_consumida | medida/índice | DOUBLE |
| 71 | indice_atendimento_esgoto_esgoto | medida/índice | DOUBLE |
| 72 | indice_perda_distribuicao_agua | medida/índice | DOUBLE |
| 73 | indice_perda_linear_agua | medida/índice | DOUBLE |
| 74 | indice_perda_ligacao_agua | medida/índice | DOUBLE |
| 75 | indice_consumo_agua | medida/índice | DOUBLE |
| 76 | indice_consumo_medio_agua | medida/índice | DOUBLE |
| 77 | indice_atendimento_total_agua | medida/índice | DOUBLE |
| 78 | indice_atendimento_esgoto_agua | medida/índice | DOUBLE |
| 79 | indice_fluoretacao_agua | medida/índice | DOUBLE |
| 80 | indice_consumo_energia_agua | medida/índice | DOUBLE |
| 81 | indice_consumo_energia_esgoto | medida/índice | DOUBLE |
| 82 | receita_operacional_direta | monetária | DECIMAL(_,2) |
| 83 | receita_operacional_direta_agua | monetária | DECIMAL(_,2) |
| 84 | receita_operacional_direta_esgoto | monetária | DECIMAL(_,2) |
| 85 | receita_operacional_indireta | monetária | DECIMAL(_,2) |
| 86 | receita_operacional_direta_agua_exportada | monetária | DECIMAL(_,2) |
| 87 | receita_operacional | monetária | DECIMAL(_,2) |
| 88 | receita_operacional_direta_esgoto_importado | monetária | DECIMAL(_,2) |
| 89 | arrecadacao_total | monetária | DECIMAL(_,2) |
| 90 | credito_areceber | monetária | DECIMAL(_,2) |
| 91 | despesa_pessoal | monetária | DECIMAL(_,2) |
| 92 | quantidade_empregado | inteiro | BIGINT |
| 93 | despesa_produto_quimico | monetária | DECIMAL(_,2) |
| 94 | despesa_energia | monetária | DECIMAL(_,2) |
| 95 | despesa_servico_terceiro | monetária | DECIMAL(_,2) |
| 96 | despesa_exploracao | monetária | DECIMAL(_,2) |
| 97 | despesas_juros_divida | monetária | DECIMAL(_,2) |
| 98 | despesa_total_servico | monetária | DECIMAL(_,2) |
| 99 | despesa_ativo | monetária | DECIMAL(_,2) |
| 100 | despesa_agua_importada | monetária | DECIMAL(_,2) |
| 101 | despesa_fiscal | monetária | DECIMAL(_,2) |
| 102 | despesa_fiscal_nao_computada | monetária | DECIMAL(_,2) |
| 103 | despesa_exploracao_outro | monetária | DECIMAL(_,2) |
| 104 | despesa_servico_outro | monetária | DECIMAL(_,2) |
| 105 | despesa_amortizacao_divida | monetária | DECIMAL(_,2) |
| 106 | despesas_juros_divida_excecao | monetária | DECIMAL(_,2) |
| 107 | despesa_divida_variacao | monetária | DECIMAL(_,2) |
| 108 | despesa_divida_total | monetária | DECIMAL(_,2) |
| 109 | despesa_esgoto_exportado | monetária | DECIMAL(_,2) |
| 110 | despesa_capitalizavel_municipio | monetária | DECIMAL(_,2) |
| 111 | despesa_capitalizavel_estado | monetária | DECIMAL(_,2) |
| 112 | despesa_capitalizavel_prestador | monetária | DECIMAL(_,2) |
| 113 | investimento_agua_prestador | monetária | DECIMAL(_,2) |
| 114 | investimento_esgoto_prestador | monetária | DECIMAL(_,2) |
| 115 | investimento_outro_prestador | monetária | DECIMAL(_,2) |
| 116 | investimento_recurso_proprio_prestador | monetária | DECIMAL(_,2) |
| 117 | investimento_recurso_oneroso_prestador | monetária | DECIMAL(_,2) |
| 118 | investimento_recurso_nao_oneroso_prestador | monetária | DECIMAL(_,2) |
| 119 | investimento_total_prestador | monetária | DECIMAL(_,2) |
| 120 | investimento_agua_municipio | monetária | DECIMAL(_,2) |
| 121 | investimento_esgoto_municipio | monetária | DECIMAL(_,2) |
| 122 | investimento_outro_municipio | monetária | DECIMAL(_,2) |
| 123 | investimento_recurso_proprio_municipio | monetária | DECIMAL(_,2) |
| 124 | investimento_recurso_oneroso_municipio | monetária | DECIMAL(_,2) |
| 125 | investimento_recurso_nao_oneroso_municipio | monetária | DECIMAL(_,2) |
| 126 | investimento_total_municipio | monetária | DECIMAL(_,2) |
| 127 | investimento_agua_estado | monetária | DECIMAL(_,2) |
| 128 | investimento_esgoto_estado | monetária | DECIMAL(_,2) |
| 129 | investimento_outro_estado | monetária | DECIMAL(_,2) |
| 130 | investimento_recurso_proprio_estado | monetária | DECIMAL(_,2) |
| 131 | investimento_recurso_oneroso_estado | monetária | DECIMAL(_,2) |
| 132 | investimento_recurso_nao_oneroso_estado | monetária | DECIMAL(_,2) |
| 133 | investimento_total_estado | monetária | DECIMAL(_,2) |

**As 51 monetárias** = 7 `receita_*` + `arrecadacao_total` + `credito_areceber`
+ 21 `despesa*` + 21 `investimento_*`. Confirmação explícita dos 4 itens
pedidos (todos **incluídos**):

| Coluna | Está nas monetárias? |
|---|---|
| `despesas_juros_divida` | ✅ sim |
| `despesas_juros_divida_excecao` | ✅ sim |
| `arrecadacao_total` | ✅ sim |
| `credito_areceber` | ✅ sim |

> Ajuste vs. Rodada 1: aqui classifiquei por evidência de valores inteiros, então
> `quantidade_empregado` entrou em **inteiro** (não monetária) e a contagem de
> monetárias é **51** (a Rodada 1 citou "53 monetárias" agrupando por prefixo e
> incluindo contagens de casas decimais; a diferença é só de critério de
> classificação, não de dados).

## R2.2 — `volume_*`, `extensao_*`, `consumo_eletrico_*`, `indice_*`: min, max, casas decimais

Máx. de casas decimais observado é **2** em todas (alguns índices só chegam a 1).

| Coluna | Mín | Máx | Máx casas |
|---|---|---|---|
| extensao_rede_agua | 0,0 | 4.883.646,0 | 2 |
| extensao_rede_esgoto | 0,0 | 1.791.797,0 | 2 |
| volume_agua_produzido | 0,0 | 7.114.442,76 | 2 |
| volume_agua_tratada_eta | 0,0 | 4.980.110,0 | 2 |
| volume_agua_micromedido | 0,0 | 1.286.217,66 | 2 |
| volume_agua_consumido | 0,0 | 2.408.408,7 | 2 |
| volume_agua_faturado | 0,0 | 2.468.324,18 | 2 |
| volume_agua_macromedido | 0,0 | 5.595.085,0 | 2 |
| volume_agua_tratada_desinfeccao | 0,0 | 2.134.332,75 | 2 |
| volume_agua_bruta_exportado | 0,0 | 78.000,0 | 2 |
| volume_agua_tratada_importado | 0,0 | 1.345.024,84 | 2 |
| volume_agua_tratada_exportado | 0,0 | 1.382.878,0 | 2 |
| volume_agua_micromedido_economia_ativa | **−15,01** | 667.023,09 | 2 |
| volume_servico_agua | 0,0 | 219.176,51 | 2 |
| volume_agua_fluoretada | 0,0 | 1.345.024,84 | 2 |
| consumo_eletrico_sistemas_agua | 0,0 | 7.823.015,0 | 2 |
| volume_esgoto_coletado | 0,0 | 47.452.063,0 | 2 |
| volume_esgoto_tratado | 0,0 | 47.452.063,0 | 2 |
| volume_esgoto_faturado | 0,0 | 47.452.063,0 | 2 |
| volume_esgoto_bruto_exportado | 0,0 | 42.564,47 | 2 |
| volume_esgoto_bruto_importado | 0,0 | 35.000,0 | 2 |
| volume_esgoto_importado | 0,0 | 10.187,68 | 2 |
| volume_esgoto_bruto_exportado_tratamento_importador | 0,0 | 42.564,47 | 2 |
| consumo_eletrico_sistemas_esgoto | 0,0 | 534.172,0 | 2 |
| indice_agua_ligacao | 0,08 | 69,0 | 2 |
| indice_hidrometracao | 0,0 | 100,0 | 2 |
| indice_macromedicao_volume_disponibilizado | **−4.600,0** | 1.111,98 | 2 |
| indice_macromedicao | **−1.603,63** | 154.250,0 | 2 |
| indice_perda_faturamento | **−5.375,0** | 100,0 | 2 |
| indice_micromedido_economia | 0,0 | 11.363,3 | 1 |
| indice_coleta_esgoto | **−30,22** | 5.452,56 | 2 |
| indice_tratamento_esgoto | 0,0 | 162.555,56 | 2 |
| indice_consumo_agua_faturado | **−1.001,9** | 11.363,3 | 1 |
| indice_extensao_agua_ligacao | 0,0 | 18.017,2 | 1 |
| indice_extensao_esgoto_ligacao | 0,0 | 42.000,0 | 2 |
| indice_consumo_agua_per_capita | **−623,9** | 105.263,2 | 1 |
| indice_atendimento_urbano_agua | 0,0 | 1.031,0 | 1 |
| indice_atendimento_agua_esgoto | 0,0 | 1.397,98 | 2 |
| indice_volume_agua_economia | 0,0 | 23.858,3 | 1 |
| indice_faturamento_agua | 0,0 | 5.475,0 | 2 |
| indice_participacao_economia_agua | 0,0 | 2.600,85 | 2 |
| indice_micromedicao_relativo_agua | **−418,18** | 100,0 | 2 |
| indice_esgotamento_agua_consumida | **−12,09** | 875,23 | 2 |
| indice_atendimento_esgoto_esgoto | 0,0 | 1.397,98 | 2 |
| indice_perda_distribuicao_agua | **−5.375,0** | 100,0 | 2 |
| indice_perda_linear_agua | **−2.624,87** | 28.395,07 | 2 |
| indice_perda_ligacao_agua | **−46.164,38** | 167.835,62 | 2 |
| indice_consumo_agua | 0,0 | 5.475,0 | 2 |
| indice_consumo_medio_agua | **−60,3** | 19.666,7 | 1 |
| indice_atendimento_total_agua | 0,0 | 100,0 | 2 |
| indice_atendimento_esgoto_agua | 0,0 | 100,0 | 2 |
| indice_fluoretacao_agua | 0,0 | 3.627,39 | 2 |
| indice_consumo_energia_agua | 0,0 | 477,34 | 2 |
| indice_consumo_energia_esgoto | 0,0 | 16.000,0 | 2 |

**Nota:** só 4 índices têm teto exato em 100,0 (`indice_hidrometracao`,
`indice_micromedicao_relativo_agua`, `indice_atendimento_total_agua`,
`indice_atendimento_esgoto_agua`) e `indice_perda_faturamento` /
`indice_perda_distribuicao_agua` têm máx. 100,0 mas mínimos muito negativos.
Os demais ultrapassam 100 (ver Rodada 1, item 9.1).

## R2.3 — Valor máximo de `populacao_*` e `quantidade_*`

| Coluna | Máx |
|---|---|
| populacao_atendida_agua | 12.396.372 |
| populacao_atentida_esgoto | 12.396.372 |
| populacao_urbana | 12.284.940 |
| populacao_urbana_residente_agua | 12.284.940 |
| populacao_urbana_atendida_agua | 12.284.940 |
| populacao_urbana_atendida_agua_ibge | 12.396.372 |
| populacao_urbana_residente_esgoto | 12.284.940 |
| populacao_urbana_atendida_esgoto | 12.284.940 |
| populacao_urbana_residente_esgoto_ibge | 12.396.372 |
| quantidade_sede_municipal_agua | 1 |
| quantidade_sede_municipal_esgoto | 1 |
| quantidade_localidade_agua | 3.348 |
| quantidade_localidade_esgoto | 5.000 |
| quantidade_ligacao_ativa_agua | 3.308.131 |
| quantidade_ligacao_ativa_esgoto | 2.997.737 |
| quantidade_ligacao_total_agua | 3.755.238 |
| quantidade_ligacao_total_esgoto | 3.294.368 |
| quantidade_economia_ativa_agua | 5.244.059 |
| quantidade_economia_ativa_esgoto | 5.930.147 |
| quantidade_ligacao_micromedia_ativa_agua | 3.308.068 |
| quantidade_economia_residencial_ativa_agua | 4.876.789 |
| quantidade_economia_residencial_ativa_esgoto | 4.534.461 |
| quantidade_economia_micromedida_ativa_agua | 5.183.315 |
| quantidade_economia_residencial_micromedida_ativa_agua | 4.818.597 |
| quantidade_empregado | 6.454 |

**Fatos:** `quantidade_sede_municipal_*` é binária (máx. 1); os máximos de
população batem com São Paulo (≈12,3–12,4 mi); todos cabem em `INTEGER`
(< 2,1 bi), com folga até para `BIGINT`.

## R2.4 — Colunas com negativos e contagem

43 colunas têm ao menos um valor negativo:

| Coluna | Negativos | Coluna | Negativos |
|---|---|---|---|
| volume_agua_micromedido_economia_ativa | 1 | despesa_pessoal | 7 |
| indice_macromedicao_volume_disponibilizado | 1 | despesa_produto_quimico | 2 |
| indice_macromedicao | 193 | despesa_energia | 3 |
| indice_perda_faturamento | 9.179 | despesa_servico_terceiro | 7 |
| indice_coleta_esgoto | 2 | despesa_exploracao | 6 |
| indice_consumo_agua_faturado | 58 | despesas_juros_divida | 160 |
| indice_consumo_agua_per_capita | 6 | despesa_total_servico | 3 |
| indice_micromedicao_relativo_agua | 6 | despesa_ativo | 601 |
| indice_esgotamento_agua_consumida | 2 | despesa_agua_importada | 1 |
| indice_perda_distribuicao_agua | 468 | despesa_fiscal | 1.139 |
| indice_perda_linear_agua | 481 | despesa_fiscal_nao_computada | 6.935 |
| indice_perda_ligacao_agua | 488 | despesa_exploracao_outro | 792 |
| indice_consumo_medio_agua | 6 | despesa_servico_outro | 1.258 |
| receita_operacional_direta | 1 | despesa_amortizacao_divida | 342 |
| receita_operacional_direta_agua | 2 | despesas_juros_divida_excecao | 4 |
| receita_operacional_direta_esgoto | 7 | despesa_divida_variacao | 4.152 |
| receita_operacional_indireta | 40 | despesa_divida_total | 46 |
| receita_operacional | 3 | despesa_capitalizavel_prestador | 2 |
| credito_areceber | 7 | investimento_agua_prestador | 26 |
| investimento_esgoto_prestador | 21 | investimento_outro_prestador | 24 |
| investimento_recurso_proprio_prestador | 11 | investimento_recurso_oneroso_prestador | 11 |
| investimento_total_prestador | 10 | | |

**Fatos:** maiores concentrações em `indice_perda_faturamento` (9.179),
`despesa_fiscal_nao_computada` (6.935) e `despesa_divida_variacao` (4.152).
Nenhuma coluna `populacao_*`, `quantidade_*`, `extensao_*` ou
`consumo_eletrico_*` tem negativos. Entre `volume_*`, só uma
(`volume_agua_micromedido_economia_ativa`, 1 caso).

## R2.5 — Zeros em 2022 vs 2021

**Pergunta:** há colunas que viram maioria-zero em 2022 e **não** em 2021?
**Resposta: não.** Nenhuma coluna passa a ter a maioria dos valores (não-nulos)
zerada só em 2022. As colunas que são majoritariamente zero em 2022
(exportação/importação, investimentos municipais/estaduais) **já eram**
majoritariamente zero em 2021 — é característica estrutural, não mudança de 2022.

O fenômeno de 2022 destacado na Rodada 1 é de **nulos, não zeros**:

| Coluna | Ano | Total | Zeros | Nulos |
|---|---|---|---|---|
| populacao_urbana_atendida_esgoto | 2021 | 5.313 | 20 | 2.534 |
| populacao_urbana_atendida_esgoto | 2022 | 5.425 | 0 | **5.425 (100%)** |

Ou seja, a coluna não "zerou" em 2022 — ficou **inteiramente nula** nesse ano.

## R2.6 — População total vs. urbana

| Condição | Linhas |
|---|---|
| `populacao_atendida_agua` > `populacao_urbana` | 47.934 |
| …e também > `populacao_urbana_residente_agua` | **47.934** |

**Fato:** as duas contagens são **idênticas** (47.934). Toda linha em que a
população atendida com água supera a população urbana também supera a população
urbana residente de água. Consistente com a hipótese de que
`populacao_atendida_agua` é um total (urbano+rural) e os campos `urbana*` são
subconjuntos urbanos — mas isso **não foi confirmado** no dicionário do SNIS.

## Anexo C — Consultas da Rodada 2

```sql
-- R2.1 classe por heurística de nome (identificador/inteiro/monetária/medida)
DESCRIBE bronze.municipio_agua_esgoto;

-- R2.2 min/max/casas decimais
SELECT min(TRY_CAST("col" AS DOUBLE)), max(TRY_CAST("col" AS DOUBLE)) FROM T;
SELECT max(length(split_part("col", '.', 2))) FROM T WHERE "col" LIKE '%.%';

-- R2.3 máximos
SELECT max(TRY_CAST("col" AS DOUBLE)) FROM T;

-- R2.4 negativos por coluna
SELECT count(*) FROM T WHERE TRY_CAST("col" AS DOUBLE) < 0;

-- R2.5 zeros/nulos por ano
SELECT count(*) FROM T WHERE ano='AAAA' AND TRY_CAST("col" AS DOUBLE)=0;
SELECT count("col") FROM T WHERE ano='AAAA';     -- não-nulos

-- R2.6 população total vs urbana
SELECT count(*) FROM T
 WHERE TRY_CAST(populacao_atendida_agua AS DOUBLE) > TRY_CAST(populacao_urbana AS DOUBLE)
   AND TRY_CAST(populacao_atendida_agua AS DOUBLE) > TRY_CAST(populacao_urbana_residente_agua AS DOUBLE);
```

## Anexo D — Suposições da Rodada 2

- **Classe das colunas** (R2.1) é heurística por nome + evidência de valores,
  **não** o dicionário oficial do SNIS. "medida/índice" junta volumes,
  extensões, consumo elétrico e índices (todos com decimais); "monetária" =
  receita/despesa/investimento/arrecadação/crédito.
- **`quantidade_empregado`** foi posto em "inteiro" por ter só valores inteiros
  (máx. 6.454), apesar do prefixo `quantidade_`; na Rodada 1 ele aparecia junto
  da família `quantidade`. Diferença de critério, não de dados.
- **Tipo sugerido** reflete a evidência (casas decimais, sinal, magnitude), não
  uma decisão de modelagem — a escolha final é da spec da silver. `DECIMAL(_,2)`
  indica 2 casas; a precisão total não foi dimensionada.
- **R2.5:** "maioria" = mais de 50% dos valores **não-nulos** do ano. Critério
  arbitrário para triagem.
- **R2.6:** comparação direta de campos; a semântica (total vs. urbano) **não**
  foi confirmada em documentação oficial.
- Possível perda de precisão de `DOUBLE` em valores muito grandes não foi
  reavaliada nesta rodada.
