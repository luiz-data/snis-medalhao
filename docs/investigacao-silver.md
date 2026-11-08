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

---
---

# Rodada 3

Complemento sobre **`silver.municipio_agua_esgoto`** (`snis.duckdb`, MCP
somente leitura). Objetivo: preparar a **spec da gold** (10 marts de
[`indicadores.md`](indicadores.md)) e a **ingestão do IBGE**
([`fontes-ibge.md`](fontes-ibge.md)). **Só fatos, sem decisões.** `TRY_CAST`
não foi necessário (a silver já é tipada). Nomes de coluna conferidos em
`duckdb_columns()`.

### Nota sobre nomes reais de coluna (o que foi usado e por quê)

| Pedido do enunciado | Coluna real usada na silver | Observação |
|---|---|---|
| população atendida de esgoto | `populacao_atendida_esgoto` | a silver **corrigiu** a grafia da bronze (`populacao_atentida_esgoto`) |
| **população total** | **não existe na silver SNIS** | só virá do **IBGE-POP**; onde o item pedia "população total" usei `populacao_urbana` como **proxy de diagnóstico** e sinalizo |
| volume de esgoto coletado / tratado | `volume_esgoto_coletado` / `volume_esgoto_tratado` | — |
| receita operacional total | `receita_operacional` | há também `receita_operacional_direta`; "total" = `receita_operacional` |
| despesa total | `despesa_total_servico` | — |
| investimento total | `investimento_total_prestador` | há `_municipio` e `_estado`; o mart 5/8 usa o do **prestador** |

---

## R3.1 — Colunas 100% nulas por ano (marts 1 e 3; alerta da spec v2.1)

Via `UNPIVOT ... INTO NAME/VALUE` + anti-join (o `UNPIVOT` do DuckDB **descarta
nulos** por padrão, então colunas totalmente nulas num ano simplesmente não
aparecem). **Anos de 2009 a 2021 não têm nenhuma coluna 100% nula.** Resumo:

| Ano | Nº de colunas 100% nulas |
|---|---|
| 1995 | 64 |
| 1996 | 63 |
| 1997 | 66 |
| 1998 | 46 |
| 1999 | 37 |
| 2000 | 35 |
| 2001 | 29 |
| 2002 | 27 |
| 2003–2006 | 22 cada |
| 2007–2008 | 18 cada |
| **2009–2021** | **0** |
| **2022** | **8** |

- Até ~2008 os nulos estruturais são sobretudo **investimento municipal/estadual**,
  **despesa de dívida/fiscal**, **exportação-importação de esgoto** e vários
  **índices** — variáveis que o SNIS só passou a coletar depois.
- **2022 (as 8 colunas 100% nulas):** `populacao_urbana`,
  `populacao_urbana_residente_agua`, `populacao_urbana_atendida_agua`,
  `populacao_urbana_residente_esgoto`, `populacao_urbana_atendida_esgoto`,
  `indice_atendimento_urbano_agua`, `indice_atendimento_agua_esgoto`,
  `indice_atendimento_esgoto_esgoto`.

**Destaque população urbana 2022 + contraste com as variantes `_ibge`:** as
colunas urbanas **autodeclaradas** zeram em 2022, mas as variantes **`_ibge`
continuam preenchidas** — forte indício de que o SNIS substituiu a população
urbana própria pela estimativa IBGE nesse ano:

| Coluna | 2021 (não nulos) | 2022 (não nulos) |
|---|---|---|
| `populacao_urbana` | 5.313 | **0** |
| `populacao_urbana_atendida_agua` | 5.302 | **0** |
| `populacao_urbana_atendida_agua_ibge` | 5.312 | **5.425** |
| `populacao_urbana_residente_esgoto` | 2.787 | **0** |
| `populacao_urbana_residente_esgoto_ibge` | 2.787 | **2.902** |

> Não há `populacao_urbana_ibge` (residente urbana total) — só existem as
> variantes `_ibge` de *atendida água* e *residente esgoto*. Logo, mesmo usando
> `_ibge`, falta em 2022 o **denominador de água** (`populacao_urbana`) do mart 1.

**Colunas 100% nulas em 2022 que são usadas nas fórmulas do
[`indicadores.md`](indicadores.md):**

| Coluna nula em 2022 | Onde é usada |
|---|---|
| `populacao_urbana` | denominador água dos marts **1, 4, 10** |
| `populacao_urbana_atendida_agua` | numerador dos marts **1, 4, 10** |
| `populacao_urbana_atendida_esgoto` | numerador esgoto do mart **1** |
| `populacao_urbana_residente_esgoto` | denominador esgoto do mart **1** |
| os 3 `indice_atendimento_*` | **não** entram nas fórmulas (os marts recalculam `sum/sum`) |

→ **2022 inviabiliza todos os marts urbanos** (1, 4 e 10) com as colunas
autodeclaradas. Volumes, receita, despesa e investimento estão presentes em 2022.

---

## R3.2 — Informantes por ano (municípios com valor não nulo)

`COLUMNS`/`count()` por ano. "População total" não existe → coluna omitida
(ver nota de nomes). `populacao_urbana` ≈ nº de linhas em todo ano (só é nula em
2022).

| Ano | Linhas | pop_at_água | pop_at_esg | pop_urb | vol_água_prod | vol_esg_col | vol_esg_trat | receita_op | desp_total | invest_total |
|---|---|---|---|---|---|---|---|---|---|---|
| 1995 | 54 | 28 | 26 | 54 | 27 | 21 | 26 | 29 | 24 | 0 |
| 1998 | 3.916 | 722 | 312 | 3.916 | 449 | 261 | 195 | 118 | 116 | 119 |
| 2000 | 4.054 | 993 | 411 | 4.054 | 785 | 384 | 329 | 180 | 161 | 111 |
| **2001** | 4.139 | **1.508** | 526 | 4.139 | **1.513** | 518 | 479 | **1.438** | **1.209** | **1.087** |
| 2005 | 4.320 | 3.038 | 934 | 4.320 | 2.987 | 910 | 926 | 2.957 | 2.543 | 2.740 |
| **2006** | 4.516 | 4.479 | **1.219** | 4.516 | 4.405 | **1.218** | **1.177** | 4.400 | 3.777 | 4.248 |
| 2010 | 4.950 | 4.932 | 1.939 | 4.950 | 4.928 | 1.764 | 1.812 | 4.933 | 4.929 | 4.598 |
| 2021 | 5.313 | 5.312 | 2.780 | 5.313 | 5.312 | 2.806 | 2.806 | 5.312 | 5.312 | 4.534 |
| 2022 | 5.425 | 5.425 | 2.900 | **0** | 5.425 | 3.057 | 3.057 | 5.425 | 5.425 | 4.672 |

*(tabela completa 1995–2022 disponível na consulta do Anexo E; acima, os anos de virada)*

**Ano em que cada coluna passa de 1.000 municípios informantes:**

| Coluna | 1º ano > 1.000 |
|---|---|
| `populacao_urbana` | **1998** (3.916) |
| `populacao_atendida_agua` | **2001** (1.508) |
| `volume_agua_produzido` | **2001** (1.513) |
| `receita_operacional` | **2001** (1.438) |
| `despesa_total_servico` | **2001** (1.209) |
| `investimento_total_prestador` | **2001** (1.087) |
| `populacao_atendida_esgoto` | **2006** (1.219) |
| `volume_esgoto_coletado` | **2006** (1.218) |
| `volume_esgoto_tratado` | **2006** (1.177) |

→ Série financeira e de água fica robusta **a partir de 2001**; esgoto só
**a partir de 2006**. Antes de 2001 qualquer agregado nacional/UF é frágil.

---

## R3.3 — Painel fixo 2010–2021 (marts 4 e 10)

Chave dos índices urbanos = `populacao_urbana_atendida_agua` **e**
`populacao_urbana` não nulos (numerador e denominador do atendimento urbano de
água). `populacao_urbana` quase nunca é nula (2010–2021), então o painel é
governado pela coluna *atendida*.

| Recorte | Nº de municípios |
|---|---|
| não nulos em **todos os 12 anos** (2010–2021) | **4.472** |
| presentes em **2010 e 2021** (os dois extremos) | 4.843 |
| presentes em **2015 e 2021** | 4.953 |

**Painel 2010–2021 por UF (4.472 municípios, todas as 27 UFs presentes):**

| UF | n | UF | n | UF | n |
|---|---|---|---|---|---|
| MG | 687 | PB | 157 | MS | 72 |
| SP | 516 | PI | 157 | ES | 70 |
| BA | 376 | RN | 155 | PA | 63 |
| RS | 374 | MA | 143 | MT | 54 |
| PR | 374 | TO | 121 | RO | 42 |
| SC | 246 | AL | 82 | AC | 21 |
| GO | 227 | RJ | 79 | AP | 16 |
| PE | 174 | SE | 75 | RR | 14 |
| CE | 163 | | | AM | 13 |
| | | | | DF | 1 |

→ **Quartis (mart 10) no agregado nacional: viável** — 4.472 municípios dão
~1.118 por quartil. **Por UF, inviável** nos pequenos (DF=1, AM=13, RR=14,
AP=16, AC=21, RO=42): `ntile(4)` por UF não tem massa. Quartil de renda deve ser
**nacional**, não por UF.

---

## R3.4 — Valores gigantes (marts 5 e 8)

`investimento_total_prestador` e `despesa_total_servico`. População via
`populacao_urbana` (não há total SNIS); `por_hab` = valor / `populacao_urbana`.

**Top 10 `investimento_total_prestador`** — 9 das 10 linhas são o município
**3550308 (São Paulo capital = SABESP, prestador regional)**:

| id | UF | ano | valor (R$) | pop_urb | R$/hab |
|---|---|---|---|---|---|
| 3550308 | SP | 2016 | 2.625.398.495 | 11.929.962 | 220 |
| 3550308 | SP | 2021 | 2.261.066.786 | 12.284.940 | 184 |
| 3550308 | SP | 2017 | 2.173.013.357 | 11.998.090 | 181 |
| 3550308 | SP | 2022 | 2.137.942.452 | *(nulo)* | — |
| 3550308 | SP | 2015 | 2.085.629.739 | 11.860.245 | 176 |
| **3547809** | **SP** | **2019** | **1.336.908.104** | **718.773** | **1.860** |

→ a linha **3547809 (SP, 2019)** destoa: R$ 1.860/hab, ~10× o resto — típico de
**valor de prestador regional atribuído ao município-sede**, não ao universo
atendido.

**Top 10 `despesa_total_servico`** — dominado por **3304557 (Rio de Janeiro
capital = CEDAE)** e **3550308 (SABESP)**:

| id | UF | ano | valor (R$) | pop_urb | R$/hab |
|---|---|---|---|---|---|
| 3304557 | RJ | 2022 | 7.266.639.142 | *(nulo)* | — |
| 3550308 | SP | 2022 | 7.089.974.466 | *(nulo)* | — |
| 3550308 | SP | 2021 | 6.099.473.275 | 12.284.940 | 497 |
| 3550308 | SP | 2020 | 5.841.352.937 | 12.214.439 | 478 |

**Valores idênticos repetidos em vários municípios** (sinal de prestador
regional duplicado): praticamente **inexistente** acima de R$ 1 mi — só 3 casos
(ano 2012 R$ 5,92 mi em 2 munic.; 2008 R$ 3,96 mi em 3 munic.; 2010 R$ 1,54 mi
em 2 munic.). → A distorção **não** é duplicação do mesmo valor entre
municípios; é **concentração no município-sede** do prestador regional (SABESP,
CEDAE), que recebe todo o valor do prestador. **Casos suspeitos listados, nada
corrigido.**

---

## R3.5 — Preparação para a junção com o IBGE

### a) Integridade de `id_municipio`

| Teste | Resultado |
|---|---|
| fora do padrão `^[0-9]{7}$` | **0** |
| com espaços (`id <> trim(id)`) | **0** |
| pares distintos (UF, 2 primeiros dígitos) | **27** = nº de UFs → cada UF tem **um único** prefixo |

→ `id_municipio` tem sempre 7 dígitos, sem espaços, sem zeros à esquerda
perdidos, e os 2 primeiros dígitos casam com a UF. **Nenhuma divergência.**
Pronto para junção por `id_municipio` (texto, 7 dígitos) com IBGE-DTB/POP/PIB.

### b) Municípios distintos

| Métrica | Valor |
|---|---|
| municípios distintos no total | **5.549** (= esperado) |
| municípios que aparecem em **1 só ano** | **31** |

→ O universo bate com o esperado. Os 31 municípios de ano único não entram em
painel e devem ser tratados na cobertura de junção (podem ser códigos antigos /
fusões — a conferir contra a **versão (ano) da DTB**).

### c) Distribuição por porte — 2021 (**proxy `populacao_urbana`**, ver ressalva)

Não há população total na silver; a faixa oficial do **mart 6 depende de
IBGE-POP (ainda não ingerido)**. Abaixo, diagnóstico sobre `populacao_urbana`:

| Faixa (hab. urbanos) | Nº de municípios |
|---|---|
| até 5 mil | 2.110 |
| 5–20 mil | 1.991 |
| 20–50 mil | 670 |
| 50–100 mil | 250 |
| 100–500 mil | 245 |
| acima de 500 mil | 47 |
| **total** | **5.313** |

> Ressalva: por **população urbana** a maioria é pequena; usando **população
> total IBGE** as faixas sobem (há população rural não contada aqui). Esta tabela
> é só para dimensionar o mart 6 — a faixa final **tem de usar IBGE-POP**.

---

## R3.6 — Pendências da spec v2.1 da silver

### a) Alerta A2 — `populacao_urbana_atendida_agua` > `populacao_urbana`

Comparação **urbana × urbana** (não contra o total). Violações por ano:

| Ano | viola água | viola esgoto* |
|---|---|---|
| 2001 | 488 | 43 |
| 2003 | 1.023 | 92 |
| 2006 | 2.701 | 220 |
| 2009 | 2.156 | 209 |
| **2010** | **26** | 2 |
| 2015 | 1 | 2 |
| 2016 | 43 | 7 |
| 2021 | 18 | 7 |

\* esgoto = `populacao_urbana_atendida_esgoto` > `populacao_urbana_residente_esgoto`.

→ A2 é **massivo antes de 2010** (centenas a milhares) e **pequeno na janela
2010–2021** (≤ 43/ano em água, ≤ 7 em esgoto). Usando o **denominador urbano
correto**, o excesso quase some — contraste com os 47.934 casos da bronze
(R2.6), que comparavam `populacao_atendida_agua` (total) contra a urbana. A
violação residual (dezenas/ano) ainda precisa de regra (clamp ou exclusão) nos
marts 1/4/10.

### b) Lista final de colunas 100% nulas em 2022 (para o alerta)

Proposta de lista fechada (as 8 de R3.1):

```
populacao_urbana
populacao_urbana_residente_agua
populacao_urbana_atendida_agua
populacao_urbana_residente_esgoto
populacao_urbana_atendida_esgoto
indice_atendimento_urbano_agua
indice_atendimento_agua_esgoto
indice_atendimento_esgoto_esgoto
```

Observação para o alerta: as variantes `_ibge`
(`populacao_urbana_atendida_agua_ibge`, `populacao_urbana_residente_esgoto_ibge`)
**não** entram na lista — elas têm dados em 2022 e são a provável substituta.

### c) Unidades (amostragem, 2021)

Municípios grandes amostrados (3550308 SP, 3304557 RJ, 5300108 DF, 2304400 CE,
4314902 RS):

| Grandeza | Evidência | Confere? |
|---|---|---|
| populações | SP `populacao_urbana` = 12.284.940 hab | ✅ habitantes |
| volumes | SP `volume_agua_consumido` = 729.299,66 (×1.000 m³ = 729 mi m³/ano ≈ 163 L/hab·dia) | ✅ **1.000 m³/ano** |
| monetário | SP `receita_operacional` = 7,25 bi; `despesa_total_servico` = 6,10 bi | ✅ **R$/ano (nominal)** |

**Coluna fora do esperado — `volume_agua_produzido`:** em 2021, SP capital
registra **144,60** (×1.000 m³) com **consumido = 729.299,66** — produzido
<< consumido, **impossível**. RJ capital: produzido 3.259 vs. consumido 468.430.
DF/CE/RS têm produzido > consumido (normais). Quantificação `produzido <
consumido` na janela:

| Ano | com ambos | produzido < consumido | produzido = 0 e consumido > 0 |
|---|---|---|---|
| 2010 | 4.926 | 139 | 109 |
| 2015 | 5.077 | 180 | 104 |
| 2021 | 5.312 | 227 | 123 |
| 2022 | 5.425 | 244 | 115 |

→ 140–244 municípios/ano com `volume_agua_produzido` inconsistente (inclui
grandes prestadores como SABESP/CEDAE que parecem reportar produção por
subsistema). **Impacto direto no mart 3 (perdas)**, cujo denominador é
`volume_agua_produzido`: por município dá perda negativa; por UF, contamina SP e
RJ. Exige regra de exclusão/validação.

---

## R3.7 — Conclusões e recomendações para a spec da gold

*(apenas recomendações; nada implementado)*

**Ano de referência por mart**

| Mart | Ano(s) recomendado(s) | Motivo |
|---|---|---|
| 1 `atendimento_uf_ano` | **2021** (não 2022) | urbano autodeclarado 100% nulo em 2022 |
| 2 `esgoto_coleta_tratamento_ano` | 1995–2022 (robusto ≥ **2006**) | volumes de esgoto só passam de 1.000 munic. em 2006 |
| 3 `perdas_consumo_uf_ano` | 1995–2022 (robusto ≥ **2001**) | depende de `volume_agua_produzido` — **com exclusão** (R3.6c) |
| 4 `ranking_atendimento_variacao` | **2010 e 2021** | painel fixo urbano; 2022 inviável |
| 5 `financeiro_uf_ano` | 1995–2022 (robusto ≥ **2001**) | financeiro robusto a partir de 2001 |
| 6 `atendimento_porte_ano` | 2010–2021 | janela IBGE; porte **exige IBGE-POP** |
| 7 `populacao_sem_servico_uf_ano` | 2010–2021 | exige IBGE-POP |
| 8 `investimento_per_capita_uf_ano` | 2010–2021 | exige IBGE-POP; excluir sedes de prestador regional (R3.4) |
| 9 `atendimento_vs_pib_2021` | **2021** | único ano com urbano + PIB |
| 10 `avanco_por_renda_painel` | **2010 e 2021** | painel + quartil nacional |

**Painel fixo recomendado:** **2010–2021, 4.472 municípios** (não nulos em
`populacao_urbana_atendida_agua` e `populacao_urbana` nos 12 anos), todas as 27
UFs. Quartil de renda (mart 10): **nacional** (viável), **não por UF**.

**Regras de exclusão de valores suspeitos (a decidir na spec):**
1. **`volume_agua_produzido < volume_agua_consumido`** ou `= 0` com consumo > 0:
   excluir do cálculo de perdas (mart 3) — 140–244 munic./ano.
2. **Sedes de prestador regional** (ex.: 3550308 SABESP, 3304557 CEDAE): valor
   financeiro/investimento concentrado; sinalizar em marts 5 e 8, cuidado no
   `por habitante`.
3. **Violação A2 residual** (urbana atendida > urbana), 2010–2021: clamp ou
   exclusão nos marts 1/4/10.
4. **Negativos** em despesa/índice (ver Rodada 1/2): tratar antes de somar.

**Colunas que NÃO podem ser usadas em cada contexto:**
- As **8 colunas urbanas/índices** (R3.6b) em **qualquer mart com ano = 2022**.
- `populacao_urbana` como denominador em 2022 (não há `_ibge` equivalente).
- `volume_agua_produzido` **sem filtro** no mart 3.
- Qualquer coluna de investimento/despesa **para comparação entre anos** sem
  deflator (R$ nominal).

**Riscos para a junção com o IBGE:**
- **31 municípios** de ano único e possíveis **códigos antigos/fusões**: casar
  contra a **versão (ano) da DTB** e registrar não casados.
- **População total ausente na silver**: marts 6, 7, 8, 9, 10 **bloqueados** até
  a ingestão de **IBGE-POP**; porte (mart 6) idem.
- **Janela do PIB (2010–2021)**: marts 9 e 10 limitados a esse intervalo.
- Chave `id_municipio` está **limpa** (7 dígitos, prefixo UF coerente) — baixo
  risco técnico de junção; o risco é de **cobertura temporal/territorial**, não
  de formato.

---

## Anexo E — Consultas da Rodada 3

```sql
-- R3.1 colunas 100% nulas por ano (UNPIVOT descarta nulos -> anti-join)
WITH years AS (SELECT DISTINCT ano FROM silver.municipio_agua_esgoto),
cols AS (SELECT column_name AS name FROM duckdb_columns()
         WHERE schema_name='silver' AND table_name='municipio_agua_esgoto'
           AND column_name NOT IN ('ano','id_municipio','sigla_uf')),
present AS (SELECT ano,name FROM (UNPIVOT silver.municipio_agua_esgoto
             ON COLUMNS(* EXCLUDE (ano,id_municipio,sigla_uf))
             INTO NAME name VALUE value) GROUP BY ano,name)
SELECT y.ano, count(*), string_agg(c.name, ', ')
FROM years y CROSS JOIN cols c
LEFT JOIN present p ON p.ano=y.ano AND p.name=c.name
WHERE p.name IS NULL GROUP BY y.ano ORDER BY y.ano;

-- R3.2 informantes por ano
SELECT ano, count(*), count(populacao_atendida_agua), count(populacao_atendida_esgoto),
  count(populacao_urbana), count(volume_agua_produzido), count(volume_esgoto_coletado),
  count(volume_esgoto_tratado), count(receita_operacional), count(despesa_total_servico),
  count(investimento_total_prestador)
FROM silver.municipio_agua_esgoto GROUP BY ano ORDER BY ano;

-- R3.3 painel fixo (chave: urbana atendida agua + urbana)
WITH base AS (SELECT id_municipio, sigla_uf, ano FROM silver.municipio_agua_esgoto
  WHERE populacao_urbana_atendida_agua IS NOT NULL AND populacao_urbana IS NOT NULL)
SELECT count(*) FROM (SELECT id_municipio FROM base WHERE ano BETWEEN 2010 AND 2021
  GROUP BY id_municipio HAVING count(DISTINCT ano)=12);   -- idem 2010&2021, 2015&2021, por UF

-- R3.4 valores gigantes + repetição entre municípios
SELECT id_municipio, sigla_uf, ano, investimento_total_prestador, populacao_urbana
FROM silver.municipio_agua_esgoto ORDER BY investimento_total_prestador DESC NULLS LAST LIMIT 10;
SELECT ano, investimento_total_prestador, count(DISTINCT id_municipio)
FROM silver.municipio_agua_esgoto WHERE investimento_total_prestador>1000000
GROUP BY ALL HAVING count(DISTINCT id_municipio)>1 ORDER BY 2 DESC;

-- R3.5 integridade da chave e municipios distintos
SELECT count(*) FROM silver.municipio_agua_esgoto WHERE NOT regexp_matches(id_municipio,'^[0-9]{7}$');
SELECT count(DISTINCT id_municipio) FROM silver.municipio_agua_esgoto;
SELECT count(*) FROM (SELECT id_municipio FROM silver.municipio_agua_esgoto
  GROUP BY id_municipio HAVING count(DISTINCT ano)=1);
-- porte 2021 (proxy populacao_urbana)
SELECT CASE WHEN populacao_urbana<5000 THEN '1' WHEN populacao_urbana<20000 THEN '2'
  WHEN populacao_urbana<50000 THEN '3' WHEN populacao_urbana<100000 THEN '4'
  WHEN populacao_urbana<500000 THEN '5' ELSE '6' END, count(*)
FROM silver.municipio_agua_esgoto WHERE ano=2021 AND populacao_urbana IS NOT NULL GROUP BY 1;

-- R3.6a alerta A2 (urbana x urbana)
SELECT ano, count(*) FILTER (WHERE populacao_urbana_atendida_agua > populacao_urbana)
FROM silver.municipio_agua_esgoto GROUP BY ano ORDER BY ano;

-- R3.6c unidades: amostra + produzido<consumido
SELECT ano, count(*) FILTER (WHERE volume_agua_produzido < volume_agua_consumido)
FROM silver.municipio_agua_esgoto WHERE ano BETWEEN 2010 AND 2022 GROUP BY ano ORDER BY ano;
```

## Anexo F — Suposições e limitações da Rodada 3

- **"População total"** não existe na silver SNIS; onde o enunciado a pediu
  (itens 2 e 5c) usei `populacao_urbana` como **proxy de diagnóstico**, sempre
  sinalizado. O valor oficial virá de **IBGE-POP** (não ingerido).
- **Classificação de coluna por mart** segue [`indicadores.md`](indicadores.md);
  "investimento total" = `investimento_total_prestador` (não `_municipio`/`_estado`).
- **Painel R3.3** usa `populacao_urbana_atendida_agua` + `populacao_urbana` como
  chave; outros marts (financeiro, volumes) teriam painel diferente.
- **Casos suspeitos (R3.4, R3.6c)** foram apenas **listados/contados**; não
  investiguei o dicionário do SNIS nem confirmei a causa (subsistema, prestador
  regional, erro de carga). Nada foi corrigido.
- A substituição `_ibge` em 2022 (R3.1) é **inferência** a partir dos dados; a
  causa metodológica não foi confirmada em documentação do SNIS.
- Não validei dígito verificador nem existência real de cada `id_municipio`
  contra tabela oficial — isso é o **teste de cobertura de junção** a fazer na
  ingestão do IBGE.

---
---

# Verificação das decisões (Rodada 3)

Teste das 6 decisões recomendadas em R3.7, com SQL, resultado e veredito
(**CONFIRMA**, **CONFIRMA COM AJUSTE** ou **NÃO CONFIRMA**). MCP somente leitura.
Colunas conferidas em `duckdb_columns()`; `TRY_CAST` não foi necessário.

---

## D1 — População total ausente (marts 6–10 bloqueados até IBGE-POP)

Conferência: nenhuma coluna de PIB, população total IBGE ou região existe na
silver (busca por `%pib%`, `%total_ibge%`, `%regiao%` → **0 resultados**); as 13
colunas SNIS das fórmulas existem todas.

Mapeamento fórmula → colunas (de [`indicadores.md`](indicadores.md)):

| Mart | Colunas SNIS (existem na silver) | Falta (externo) | Depende de |
|---|---|---|---|
| 1 `atendimento_uf_ano` | pop_urbana, pop_urbana_atendida_agua/esgoto, pop_urbana_residente_esgoto | UF/região | **IBGE-DTB** |
| 2 `esgoto_coleta_tratamento_ano` | volume_esgoto_coletado/tratado, volume_agua_consumido | — | **nenhum (100% SNIS)** |
| 3 `perdas_consumo_uf_ano` | volume_agua_produzido/consumido, populacao_atendida_agua | UF/região | **IBGE-DTB** |
| 4 `ranking_atendimento_variacao` | pop_urbana_atendida_agua, pop_urbana | UF/região | **IBGE-DTB** |
| 5 `financeiro_uf_ano` | investimento_total_prestador, despesa_exploracao, receita_operacional_direta | UF/região | **IBGE-DTB** |
| 6 `atendimento_porte_ano` | populacao_atendida_agua/esgoto | **populacao_total_ibge** (numerador porte + denominador) | **IBGE-POP** |
| 7 `populacao_sem_servico_uf_ano` | populacao_atendida_agua/esgoto | **populacao_total_ibge** | **IBGE-POP + IBGE-DTB** |
| 8 `investimento_per_capita_uf_ano` | investimento_total_prestador | **populacao_total_ibge** | **IBGE-POP + IBGE-DTB** |
| 9 `atendimento_vs_pib_2021` | urbanas, volumes, investimento | **pib_municipio + populacao_total_ibge** | **IBGE-PIB + IBGE-POP** |
| 10 `avanco_por_renda_painel` | pop_urbana_atendida_agua, pop_urbana | **pib_municipio + populacao_total_ibge** | **IBGE-PIB + IBGE-POP** |

```sql
SELECT column_name FROM duckdb_columns()
WHERE schema_name='silver' AND table_name='municipio_agua_esgoto'
  AND (lower(column_name) LIKE '%pib%' OR lower(column_name) LIKE '%total_ibge%'
       OR lower(column_name) LIKE '%regiao%');   -- 0 linhas
```

**Veredito: CONFIRMA.** Marts **6, 7, 8, 9, 10** não calculam sem **IBGE-POP**
(e 9/10 também sem **IBGE-PIB**). Marts **1, 3, 4, 5, 7, 8** precisam de
**IBGE-DTB** para UF/região. Só o **mart 2 é 100% SNIS**. Marts 1–5 produzem a
parte SNIS sem IBGE-POP (mas sem recorte de região até a DTB entrar).

---

## D2 — Ano 2021 e colunas `_ibge`

Não existe `populacao_urbana_ibge` (residente urbana total); as variantes `_ibge`
são de *atendida água* e *residente esgoto*. Comparação da atendida urbana de
água com sua `_ibge`, 2019–2022:

| Ano | munic. c/ ambas | dif. mediana % | dif. p95 % | nº dif. > 10% |
|---|---|---|---|---|
| 2019 | 5.177 | 38,36 | 80,05 | 4.631 |
| 2020 | 5.337 | 38,44 | 80,72 | 4.765 |
| 2021 | 5.302 | 38,38 | 79,96 | 4.719 |
| 2022 | **0** | — | — | 0 |

Informantes em 2021 (completude):

| Mart | Coluna | Informantes 2021 |
|---|---|---|
| 1 | populacao_urbana | 5.313 |
| 1 | populacao_urbana_atendida_agua | 5.302 |
| 1 | populacao_urbana_residente_esgoto | 2.787 |
| 1 | populacao_urbana_atendida_esgoto | 2.779 |
| 3 | volume_agua_produzido / consumido | 5.312 / 5.312 |
| 3/7 | populacao_atendida_agua | 5.312 |
| 7 | populacao_atendida_esgoto | 2.780 |

**Veredito: CONFIRMA COM AJUSTE.** 2021 tem população urbana de **água completa**
(~5.300) — ótimo ano de referência; esgoto urbano é estruturalmente menor
(~2.780, nem toda cidade tem esgoto). **Ajuste:** a coluna `_ibge` **não** serve
como "verificação de sensibilidade" trocável — difere da autodeclarada em
**~38% na mediana** e **>10% em ~89% dos municípios**; é uma **medida distinta**
(base IBGE), não um recálculo da mesma grandeza. Em 2022 a autodeclarada é nula,
então nem há par. Tratar `_ibge` como **série alternativa rotulada**, nunca
como aproximação da coluna oficial.

---

## D3 — `volume_agua_produzido` e regra do mart 3 (perdas)

Diagnóstico 2010–2021 (IN049 ≈ `(produzido − consumido)/produzido`):

| Ano | c/ ambos | produzido < consumido | produzido nulo/0 e consumo>0 | IN049 calculável (prod>0) | IN049 fora de 0–100 |
|---|---|---|---|---|---|
| 2010 | 4.926 | 139 | 109 | 4.819 | 30 |
| 2015 | 5.077 | 180 | 104 | 4.942 | 76 |
| 2020 | 5.337 | 225 | 125 | 5.167 | 100 |
| 2021 | 5.312 | 227 | 123 | 5.168 | 104 |

Índice nacional ponderado `sum(prod−cons)/sum(prod)`:

| Ano | perda SEM exclusão | perda COM exclusão (prod ≥ cons e prod>0) |
|---|---|---|
| 2010 | 29,72% | **41,13%** |
| 2015 | 30,04% | **38,82%** |
| 2018 | 19,90% | **36,68%** |
| 2021 | 22,65% | **37,24%** |

**Veredito: CONFIRMA.** A regra muda o resultado **de forma relevante**: sem
exclusão a perda nacional cai para 20–30% (puxada por linhas com produzido
<< consumido, p.ex. SABESP 2021 produzido=144 vs. consumido=729.299); com
exclusão fica em **37–41%**, condizente com o nível nacional conhecido (~38–40%).
Excluir as linhas `produzido < consumido` (≈139–227/ano) **e** `produzido nulo/0
com consumo>0` (≈100–125/ano) é necessário. Relatar a contagem excluída por ano.

### D3 revisado — fórmula completa do IN049 (glossário SNIS 2022)

`IN049 = (AG006 + AG018 − AG010 − AG024) / (AG006 + AG018 − AG024) × 100`.
Colunas reais na silver (via `duckdb_columns()`):

| Código | Grandeza | Coluna na silver |
|---|---|---|
| AG006 | volume produzido | `volume_agua_produzido` |
| AG018 | volume (tratada) importado | `volume_agua_tratada_importado` |
| AG010 | volume consumido | `volume_agua_consumido` |
| AG024 | volume de serviço | `volume_servico_agua` |

AG018 e AG024 são majoritariamente nulos → tratados como **0** (`coalesce`);
exijo AG006 e AG010 não nulos. "Inconsistente" = `(AG006+AG018−AG024) < AG010`.

| Ano | linhas válidas | (a) inconsistentes | (c) den. nulo/0/neg | (b) índice TODAS | (b) índice SEM inconsist. |
|---|---|---|---|---|---|
| 2010 | 4.926 | 30 | 0 | 39,25 | 39,30 |
| 2011 | 4.930 | 7 | 0 | 39,06 | 39,07 |
| 2012 | 5.061 | 19 | 3 | 37,42 | 37,43 |
| 2013 | 5.030 | 34 | 14 | 38,09 | 38,19 |
| 2014 | 5.105 | 57 | 5 | 37,08 | 37,23 |
| 2015 | 5.077 | 57 | 31 | 36,88 | 37,02 |
| 2016 | 5.161 | 38 | 31 | 38,24 | 38,36 |
| 2017 | 5.116 | 1 | 37 | 38,55 | 38,55 |
| 2018 | 5.135 | 1 | 30 | 35,53 | 35,54 |
| 2019 | 5.177 | 1 | 23 | 35,97 | 35,98 |
| 2020 | 5.337 | 0 | 45 | 36,42 | 36,42 |
| 2021 | 5.312 | 2 | 21 | 36,86 | 36,86 |

**(d) UFs que mudam mais de 5 pp com a exclusão: nenhuma** (0 de 324 pares
UF-ano; maior diferença observada = **1,67 pp**).

**Comparação com o teste anterior (só `produzido`):**

| | Simplificada `(prod−cons)/prod` | IN049 completo |
|---|---|---|
| Índice nacional (todas) | **22–30%** | **35–39%** (nível oficial ~40%) |
| Inconsistentes/ano | 139–227 | **0–57** |
| Efeito da exclusão | **+10 a +17 pp** | **≤ 0,15 pp** |

**Veredito: CONFIRMA COM AJUSTE (corrige o D3 original).** A fórmula completa
muda o diagnóstico: o que parecia "produzido << consumido" eram, em boa parte,
**prestadores que importam água tratada** (AG018) — o denominador
`produzido + importado − serviço` os acomoda. Com o IN049 correto o índice
nacional já fica em **~36–39% com todas as linhas**, e a **exclusão passa a ser
imaterial** (≤ 0,15 pp no nacional, 0 UFs acima de 5 pp). **Ajuste:** manter a
exclusão das inconsistentes **apenas como salvaguarda, com flag e contagem por
ano** (0–57 linhas), **não** como a regra decisiva do D3 original — a regra antiga
`produzido < consumido` seria **excessiva** (excluiria importadores legítimos).
Mart 3 deve usar a **fórmula completa do IN049**, não a simplificada.

---

## D4 — Sedes de prestador regional

R3.4: a distorção é **concentração no município-sede**, não duplicação (só 3
valores idênticos repetidos acima de R$ 1 mi). Testes de critério de flag:

- **10× a mediana per capita da UF-ano:** flaga **3.862** munic.-ano / 1.549
  municípios / 25 UFs → **frouxo demais** (a distribuição é muito assimétrica;
  mediana ≈ R$ 15/hab).
- Distribuição nacional de investimento per capita (2010–2021): mediana
  **R$ 15**, p95 **R$ 232**, p99 **R$ 745**, **p99,5 R$ 1.217**, máx R$ 29.369.
- **Critério proposto (reproduzível): per capita > R$ 1.000/hab** (≈ p99,5
  nacional) → **~290 munic.-ano**. Impacto no total de investimento por UF
  (quanto sairia se excluído):

| UF | nº flag | % do total da UF |
|---|---|---|
| **RN** | 74 | **35,89%** |
| MA | 5 | 10,81% |
| SE | 6 | 8,14% |
| PE | 19 | 7,52% |
| SP | 40 | 4,54% |
| MG | 52 | 2,58% |
| demais 11 UFs | ≤ 24 | < 3,7% |

```sql
WITH b AS (SELECT ano,sigla_uf,id_municipio, investimento_total_prestador inv,
  investimento_total_prestador/nullif(populacao_urbana,0) pc
  FROM silver.municipio_agua_esgoto
  WHERE ano BETWEEN 2010 AND 2021 AND investimento_total_prestador>0 AND populacao_urbana>0)
SELECT sigla_uf, count(*) FILTER (WHERE pc>1000) n,
  round(sum(inv) FILTER (WHERE pc>1000)*100.0/sum(inv),2) pct
FROM b GROUP BY sigla_uf ORDER BY pct DESC;
```

**Veredito: CONFIRMA COM AJUSTE.** Manter nos totais por UF é correto —
excluir destruiria **RN (−36%)** e distorceria MA/SE/PE. **Ajuste ao critério:**
o limiar não é "mesmo valor repetido em N municípios" (quase não ocorre) nem
"10× a mediana" (frouxo); adotar **per capita > R$ 1.000/hab (≈ p99,5 nacional)**
como flag `prestador_regional_provavel`, usada só para **excluir dos rankings
municipais per capita** (marts 8 e 9). Observação: a sede SABESP atribuída à
capital de SP (R$ 184/hab) **não** é flagada por per capita — correto, pois não
distorce ranking per capita; o problema per capita aparece quando a sede é um
município pequeno. RN merece nota específica na spec.

---

## D5 — Violação A2 residual (exclusão com flag vs clamp)

Índice nacional de cobertura urbana de água `sum(atendida)/sum(urbana)`,
2010–2021:

| Ano | nº viola | dif. média (hab) | dif. máx (hab) | baseline | exclusão | clamp |
|---|---|---|---|---|---|---|
| 2010 | 26 | 2.113 | 7.758 | 92,16 | 92,10 | 92,13 |
| 2011 | 35 | 6.134 | 111.181 | 93,15 | 92,98 | 93,02 |
| 2016 | 43 | 1.363 | 30.065 | 92,97 | 92,91 | 92,94 |
| 2021 | 18 | 6.275 | 31.100 | 93,45 | 93,33 | 93,38 |

Linhas afetadas por UF (2010–2021): só **TO** passa de 1% (**1,96%**); PA 0,89%,
SE 0,78%, RJ 0,76%, MG 0,58%; todas as demais < 1%.

**Veredito: CONFIRMA COM AJUSTE.** A exclusão com flag funciona e é defensável.
**Ajuste de expectativa:** o impacto é **negligível** — exclusão e clamp diferem
do baseline em **≤ 0,17 pp** no nacional, e só **TO** ultrapassa 1% das linhas.
Como exclusão ≈ clamp aqui, a decisão é de baixo risco; recomendo manter a
**exclusão com flag** (mais transparente: o dado inválido não entra), mas clamp
seria igualmente aceitável. O que importa é **registrar a flag**, não o método.

---

## D6 — Versão da DTB e 31 municípios de ano único

A silver **não tem coluna de nome** de município (nome → **a confirmar na
ingestão da DTB**). Os 31 municípios de ano único, por ano de aparição:

| Ano único | nº | Comportamento provável |
|---|---|---|
| 1999 | 1 | 2210953(PI) — meio da série (reporte esporádico) |
| 2006–2016 | 11 | meio da série (esporádicos ou código alterado) |
| 2020 | 7 | 2102754(MA),2103125(MA),2201919/2203859/2205953(PI),5101852(MT),5214903(GO) |
| 2021 | 1 | 2908101(BA) |
| **2022 (último ano)** | **12** | 1302108(AM),2105963/2107902(MA),2200954/2205458/2210391(PI),2308351(CE),2700805(AL),2900108(BA),4304853(RS),5102694(MT),5219456(GO) — **prováveis novos informantes / emancipações** |

- **Só no último ano (2022): 12** → entram agora no SNIS; provável
  emancipação recente ou primeiro reporte — **a confirmar na ingestão da DTB**.
- **Só no primeiro ano (1995): 0.**
- **No meio da série: 19** → reporte esporádico ou código que mudou/fundiu —
  **a confirmar na ingestão da DTB**.
- **Formato:** todos os `id_municipio` têm 7 dígitos (R3.5a: 0 fora do padrão);
  **nenhum id fora do padrão**.

**Veredito: CONFIRMA.** Usar a **DTB mais recente (2025)** e listar divergências
no teste de cobertura, sem correção manual, é adequado: os 31 são majoritariamente
entrantes de 2022 e esporádicos de meio de série, e **nenhum tem formato
inválido**, então a conciliação é de **cobertura** (existência/vigência na DTB),
não de formato. Nome, emancipação vs. fusão e vigência de cada código ficam
**a confirmar na ingestão da DTB**.

---

## Quadro-resumo das 6 decisões

| # | Decisão | Veredito | Ajuste proposto |
|---|---|---|---|
| D1 | Marts 6–10 bloqueados até IBGE-POP | **CONFIRMA** | Explicitar: 6–10 exigem IBGE-POP (9/10 também IBGE-PIB); 1,3,4,5,7,8 exigem IBGE-DTB; só mart 2 é 100% SNIS |
| D2 | 2021 nos marts urbanos; `_ibge` como sensibilidade | **CONFIRMA COM AJUSTE** | `_ibge` é medida distinta (dif. mediana 38%), não recálculo; usar como série rotulada, não como aproximação |
| D3 | Perdas IN049 excluindo produzido<consumido | **CONFIRMA COM AJUSTE** (ver "D3 revisado") | Usar a fórmula completa do IN049 (AG006+AG018−AG010−AG024)/(AG006+AG018−AG024); com ela o nacional já é ~36–39% e a exclusão vira só salvaguarda (≤0,15 pp, 0 UFs >5 pp). A regra simplificada `produzido<consumido` excluía importadores legítimos |
| D4 | Sedes regionais: manter no total, flag, excluir per capita | **CONFIRMA COM AJUSTE** | Flag objetiva = per capita > R$ 1.000/hab (≈ p99,5); nota especial para RN (−36% se excluído do total) |
| D5 | A2 residual: exclusão com flag (não clamp) | **CONFIRMA COM AJUSTE** | Impacto negligível (≤0,17 pp; só TO>1%); exclusão ok, clamp equivalente — o essencial é a flag |
| D6 | DTB 2025; listar divergências dos 31 de ano único | **CONFIRMA** | 12 são entrantes de 2022, 19 de meio de série, 0 fora de formato; nome/vigência a confirmar na ingestão |

## Texto pronto para `docs/decisoes.md` (não criar o arquivo; só o texto)

```
- D1 (2026-11-08): Marts 6–10 ficam bloqueados ate ingerir IBGE-POP (e 9,10 tambem IBGE-PIB); marts 1,3,4,5,7,8 dependem de IBGE-DTB para UF/regiao; mart 2 e 100% SNIS. Motivo: a silver nao tem populacao total, PIB nem regiao (0 colunas).
- D2 (2026-11-08): Ano de referencia dos marts urbanos (1,4,9,10) e 2021; as colunas _ibge sao serie alternativa rotulada, nao verificacao de sensibilidade. Motivo: 2021 tem agua urbana completa (~5.300 informantes) e as _ibge diferem ~38% na mediana da autodeclarada.
- D3 (2026-11-08): Mart 3 (perdas) usa IN049 e exclui linhas com produzido<consumido e produzido nulo/0 com consumo positivo, reportando a contagem por ano. Motivo: a exclusao corrige a perda nacional de ~23% para ~37% (nivel oficial ~40%).
- D4 (2026-11-08): Sedes de prestador regional permanecem nos totais por UF, com flag prestador_regional_provavel (per capita > R$ 1.000/hab, ~p99,5 nacional), e sao excluidas apenas dos rankings municipais per capita (marts 8 e 9); RN tem nota propria. Motivo: concentram valor no municipio-sede; excluir do total distorceria RN (-36%).
- D5 (2026-11-08): Violacao A2 (urbana atendida agua > urbana) e excluida do calculo de cobertura com flag, em vez de clamp. Motivo: impacto nacional negligivel (<=0,17 pp; so TO >1% das linhas); exclusao e mais transparente.
- D6 (2026-11-08): Usar a DTB mais recente (2025) e conciliar os 31 municipios de ano unico no teste de cobertura, sem correcao manual. Motivo: 12 sao entrantes de 2022, 19 esporadicos de meio de serie, 0 com id fora do padrao de 7 digitos.
```

## Anexo G — Consultas da Verificação

```sql
-- D2 dif % autodeclarada vs _ibge (2019-2022)
SELECT ano, median(abs(populacao_urbana_atendida_agua-populacao_urbana_atendida_agua_ibge)*100.0
  /nullif(populacao_urbana_atendida_agua_ibge,0)) dif_mediana
FROM silver.municipio_agua_esgoto WHERE ano BETWEEN 2019 AND 2022 GROUP BY ano;

-- D3 perda nacional com/sem exclusao
SELECT ano, sum(volume_agua_produzido-volume_agua_consumido)*100.0/sum(volume_agua_produzido) sem_excl,
  sum(CASE WHEN volume_agua_produzido>=volume_agua_consumido AND volume_agua_produzido>0
        THEN volume_agua_produzido-volume_agua_consumido END)*100.0
  /sum(CASE WHEN volume_agua_produzido>=volume_agua_consumido AND volume_agua_produzido>0
        THEN volume_agua_produzido END) com_excl
FROM silver.municipio_agua_esgoto WHERE ano BETWEEN 2010 AND 2021 GROUP BY ano ORDER BY ano;

-- D5 baseline/exclusao/clamp (atd = alias; 'at' e palavra reservada)
WITH b AS (SELECT ano, populacao_urbana_atendida_agua atd, populacao_urbana urb
  FROM silver.municipio_agua_esgoto WHERE ano BETWEEN 2010 AND 2021 AND populacao_urbana>0)
SELECT ano, sum(atd)*100.0/sum(urb) baseline,
  sum(atd) FILTER (WHERE atd<=urb)*100.0/sum(urb) FILTER (WHERE atd<=urb) exclusao,
  sum(least(atd,urb))*100.0/sum(urb) clamp
FROM b GROUP BY ano ORDER BY ano;

-- D6 municipios de ano unico
WITH u AS (SELECT id_municipio, min(sigla_uf) uf, min(ano) ano
  FROM silver.municipio_agua_esgoto GROUP BY id_municipio HAVING count(DISTINCT ano)=1)
SELECT ano, count(*), string_agg(id_municipio||'('||uf||')', ', ') FROM u GROUP BY ano ORDER BY ano;
```

## Anexo H — Suposições da Verificação

- **D1:** mapeamento fórmula→coluna segue [`indicadores.md`](indicadores.md);
  `populacao_total_ibge`, `pib_municipio` e `regiao` são nomes previstos em
  [`fontes-ibge.md`](fontes-ibge.md), ainda inexistentes na silver.
- **D2:** comparei a atendida urbana de água (não há `populacao_urbana_ibge`);
  "sensibilidade" foi interpretada como troca de coluna na mesma fórmula.
- **D3:** IN049 aproximado por `(produzido−consumido)/produzido`; "volume
  disponibilizado" oficial (produzido + importado − exportado − serviço)
  **a confirmar** no glossário — pode alterar as contagens.
- **D4:** critério per capita usa `populacao_urbana` como denominador (não há
  total SNIS); o limiar R$ 1.000/hab é calibrado pela p99,5 **nacional**
  observada, não por norma do SNIS. "Prestador regional" não foi confirmado no
  cadastro de prestadores.
- **D5:** exclusão/clamp calculados só para o índice nacional e participação de
  linhas por UF; não recalculei cada índice de UF individualmente.
- **D6:** classificação emancipação/fusão é **inferência** pelo ano de aparição;
  nome e vigência de cada código **a confirmar na ingestão da DTB** (sem internet).

---
---

# Verificação de despesa unitária e tarifa média (mart 5)

Teste, com MCP somente leitura, das definições de `despesa_unitaria` (IN003) e
`tarifa_media` (IN004) do mart 5. Glossário SNIS 2022: IN003 lista AG011, ES007,
FN017; IN004 lista AG011, ES007, FN002, FN003, FN007, FN038 (FN001 = FN002 +
FN003 + FN007 + FN038). O glossário **não** traz a fórmula em texto. Hipóteses:
**IN003 = FN017 / (AG011 + ES007)** e **IN004 = FN001 / (AG011 + ES007)**, em
**R$/m³**.

## V1 — Mapeamento código SNIS → coluna da silver

Via `duckdb_columns()` (schema `silver`, tabela `municipio_agua_esgoto`):

| Código SNIS | Grandeza | Coluna na silver | Existe? |
|---|---|---|---|
| AG011 | volume de água **faturado** | `volume_agua_faturado` | ✅ |
| ES007 | volume de esgoto **faturado** | `volume_esgoto_faturado` | ✅ |
| FN002 | receita operacional direta de água | `receita_operacional_direta_agua` | ✅ |
| FN003 | receita operacional direta de esgoto | `receita_operacional_direta_esgoto` | ✅ |
| FN007 | receita op. direta de água exportada | `receita_operacional_direta_agua_exportada` | ✅ |
| FN038 | receita op. direta de esgoto importado | `receita_operacional_direta_esgoto_importado` | ✅ |
| FN001 | receita operacional direta (total) | `receita_operacional_direta` | ✅ |
| FN017 | despesas de exploração (DEX) | `despesa_exploracao` | ✅ |

- **Todas as 8 informações existem** como coluna. **FN001 não precisa ser
  composto** — já existe como `receita_operacional_direta`; mesmo assim a
  identidade `FN001 = FN002+FN003+FN007+FN038` foi testada (V2a).
- **Indicadores publicados IN003 e IN004 NÃO existem como coluna** na silver: a
  busca por `indice_*` retorna 30 colunas, **nenhuma** de tarifa ou de despesa
  por m³ (as mais próximas — `indice_faturamento_agua`,
  `indice_consumo_agua_faturado`, `indice_perda_faturamento` — são outros
  indicadores). **Logo não há coluna publicada para comparação linha a linha**;
  a confirmação se apoia na **identidade de FN001** e na **sanidade da série
  nacional** (V2b/V3) contra os valores conhecidos do SNIS.

## V2a — Identidade FN001 = FN002 + FN003 + FN007 + FN038 (2010–2021)

```sql
SELECT ano,
  count(*) FILTER (WHERE <5 componentes não nulos>) AS linhas_completas,
  count(*) FILTER (WHERE <completas> AND
    abs(receita_operacional_direta
      - (receita_operacional_direta_agua+receita_operacional_direta_esgoto
         +receita_operacional_direta_agua_exportada
         +receita_operacional_direta_esgoto_importado)) <= 0.01) AS batem
FROM silver.municipio_agua_esgoto WHERE ano BETWEEN 2010 AND 2021 GROUP BY ano;
```

**Resultado: `batem = linhas_completas` em todos os 12 anos** (2010: 1.930/1.930;
2012: 2.219/2.219; 2021: 2.787/2.787; etc.). A coluna `receita_operacional_direta`
**é** FN001 (identidade exata, 0 divergências). Confirma o numerador da tarifa.

## V2b/V3 — Conversão de unidade e sanidade da série nacional

**Correção de unidade importante:** o volume faturado está em **1.000 m³/ano**
(confirmado na Rodada 3.6c: SP `volume_agua_consumido` = 729.299,66 ×1.000 m³ ≈
163 L/hab·dia). Logo, para obter **R$/m³**:

> **R$/m³ = Σreceita (R$) / ( Σvolume (1.000 m³) × 1.000 )**

(ou seja, **dividir** por 1.000 o quociente receita/volume — **não multiplicar**,
como sugeria a redação da hipótese; multiplicar daria mediana ≈ R$ 4,6 **milhões**
/m³, absurda). Série nacional ponderada (soma/soma, com `vol>0`):

| Ano | nº informantes | `tarifa_media_br` (R$/m³) | `despesa_unitaria_br` (R$/m³) |
|---|---|---|---|
| 2010 | 4.824 | 2,18 | 1,51 |
| 2013 | 4.894 | 2,64 | 1,82 |
| 2016 | 4.938 | 3,38 | 2,36 |
| 2019 | 5.033 | 3,87 | 2,60 |
| **2021** | **5.129** | **4,12** | **2,83** |

```sql
SELECT ano,
  sum(receita_operacional_direta) FILTER (WHERE vol_fat>0)
    / (sum(vol_fat) FILTER (WHERE receita_operacional_direta IS NOT NULL) * 1000.0) AS tarifa_media_br,
  sum(despesa_exploracao) FILTER (WHERE vol_fat>0)
    / (sum(vol_fat) FILTER (WHERE despesa_exploracao IS NOT NULL) * 1000.0) AS despesa_unitaria_br
FROM (SELECT *, coalesce(volume_agua_faturado,0)+coalesce(volume_esgoto_faturado,0) AS vol_fat
      FROM silver.municipio_agua_esgoto WHERE ano BETWEEN 2010 AND 2021)
GROUP BY ano ORDER BY ano;
```

A série é **monotônica, crescente e na faixa conhecida do SNIS** (tarifa média
nacional ~R$ 2–4/m³ na década; DEX unitária menor que a tarifa em todos os anos).
Distribuição municipal 2021 (R$/m³): tarifa mediana **4,64**, p95 **9,73**;
despesa mediana **3,87**, p95 **10,03** (5.129 municípios com `vol>0`). **Sanidade
confirmada** — nenhuma variação (ex.: retirar exportação do denominador, ou usar
FN002+FN003 no numerador) foi necessária, pois as hipóteses já produzem valores
corretos e a identidade FN001 fecha.

## V4 — Universo comum por UF (2021)

Municípios com numerador **e** denominador não nulos e **denominador > 0** (mesmo
denominador `AG011+ES007` para as duas colunas → `n_tarifa = n_despesa`):

| UF | n | UF | n | UF | n |
|---|---|---|---|---|---|
| MG | 793 | PB | 186 | ES | 78 |
| SP | 633 | CE | 181 | SE | 75 |
| RS | 470 | PE | 178 | RO | 47 |
| BA | 402 | PI | 172 | AM | 40 |
| PR | 398 | RN | 159 | AC | 22 |
| SC | 289 | MA | 144 | AP | 16 |
| GO | 238 | TO | 135 | RR | 14 |
| | | MT | 111 | DF | 1 |
| | | AL | 93 | | |
| | | PA | 88 | | |
| | | RJ | 88 | | |
| | | MS | 78 | | |

**27 UFs presentes** (DF com 1 município — prestador único). Total ≈ 5.129
municípios. O **universo comum** (num. e den. não nulos, den. > 0) é a regra de
`municipios_informantes` do mart 5 para essas colunas.

## V5 — Conclusão

- **Numeradores:** `tarifa_media` ← `receita_operacional_direta` (FN001);
  `despesa_unitaria` ← `despesa_exploracao` (FN017).
- **Denominador comum:** `volume_agua_faturado + volume_esgoto_faturado`
  (AG011 + ES007), com `nullif(…, 0)` e exigindo den. > 0.
- **Unidade:** **R$/m³ = Σnum / (Σ(vol_fat) × 1.000)** — valores **nominais**
  (comparar só no mesmo ano; deflacionar está fora do escopo).
- **Agregação:** soma sobre soma (nunca `avg` de razão), herdada da regra global.
- **Ressalva:** os indicadores publicados IN003/IN004 **não** estão materializados
  como coluna; a confirmação vem da **identidade FN001 (100%)** e da **sanidade da
  série nacional** (faixa conhecida do SNIS), não de um match linha a linha com
  coluna publicada. → **Base para a D22.**
