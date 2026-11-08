# Indicadores de saneamento — marts da gold

Spec dos indicadores que a camada **silver** (SNIS + IBGE) permite calcular,
organizada por **mart / pergunta de negócio**. Escrita antes de qualquer código
de gold. Colunas, nulos e cobertura do SNIS foram conferidos via MCP somente
leitura sobre `snis.silver.municipio_agua_esgoto`. Fontes externas estão
catalogadas em [`fontes-ibge.md`](fontes-ibge.md) — **toda citação de fonte
IBGE abaixo usa um ID daquele catálogo**.

## Regras de cálculo (decisões fechadas)

- **Grão da silver SNIS:** uma linha por município e ano; chave
  `(ano, id_municipio)`.
- **Índices agregados** (por ano, UF, região ou Brasil) são sempre
  **recalculados** como `sum(numerador) / sum(denominador)` — ponderação por
  população ou volume. **Nunca** `avg()` de colunas `indice_*`.
- Numerador e denominador devem ser do **mesmo universo** (urbana com urbana,
  água com água). **Declare sempre o denominador**: população total (IBGE-POP)
  ou urbana (SNIS `populacao_urbana`).
- Todo mart por ano traz `municipios_informantes` (municípios com dado não nulo
  naquele ano para o indicador).
- Comparação entre anos usa **painel fixo** (municípios presentes nos dois anos)
  ou declara a mudança de cobertura (**54 municípios em 1995, 5.425 em 2022**).
- **Dimensão territorial = IBGE-DTB** (municípios, UF, região), ligada por
  `id_municipio` / `sigla_uf`. Substitui a seed de UF. Marts por UF citam
  IBGE-DTB como origem de UF e região.
- **Ano de referência 2021** onde 2022 tiver nulos estruturais (ver abaixo).
- Valores em **R$ são nominais**: só comparar dentro do mesmo ano; não somar nem
  comparar anos sem correção.
- **Janela analítica 2010–2021** para tudo que usa o IBGE (limite da série do
  PIB, ver [`fontes-ibge.md`](fontes-ibge.md)).

### Cobertura verificada do SNIS (fatos, não suposições)

| Fato | Valor |
|---|---|
| Linhas / anos | 119.256 / 28 (1995–2022) |
| Municípios distintos / UFs | 5.549 / 27 |
| Informantes de água em 1995 / 2022 | 54 / 5.425 |
| `populacao_atendida_agua` não nula | 99.359 |
| `populacao_urbana` não nula | 113.831 — **0 em 2022** |
| `populacao_urbana_atendida_agua` não nula | 90.727 — **0 em 2022** |
| `populacao_urbana_atendida_esgoto` não nula | 37.858 — **0 em 2022** |
| `populacao_atendida_esgoto` não nula | 42.133 (só 2.900 em 2022) |
| `volume_agua_produzido` / `_consumido` / `_faturado` | 98.303 / 98.444 / 98.590 |
| `volume_esgoto_coletado` / `_tratado` | 41.837 / 41.754 |
| `receita_operacional_direta` | 95.959 |
| `despesa_exploracao` | 96.701 |
| `investimento_total_prestador` | 84.873 |

> **Alerta de 2022:** `populacao_urbana`, `populacao_urbana_atendida_agua` e
> `populacao_urbana_atendida_esgoto` são **100% nulas em 2022**. Todo indicador
> urbano usa **2021 como ano de referência**. Volumes, receita, despesa e
> investimento estão presentes em 2022.

---

## Os 10 marts (perguntas de negócio)

### Mart 1 — `atendimento_uf_ano`

- **Pergunta:** qual % da população urbana tem água e esgoto, por UF e ano?
- **Grão:** ano × UF (+ região via IBGE-DTB).
- **Fórmula (água):** `sum(populacao_urbana_atendida_agua) / sum(populacao_urbana)`.
- **Fórmula (esgoto):**
  `sum(populacao_urbana_atendida_esgoto) / sum(populacao_urbana_residente_esgoto)`.
- **Denominador:** **urbano SNIS** (`populacao_urbana` para água;
  `populacao_urbana_residente_esgoto` para esgoto — denominador oficial a
  confirmar no dicionário SNIS).
- **Ano(s) de referência:** **2021** (urbano 100% nulo em 2022). Janela sugerida
  2010–2021.
- **Fontes:** SNIS; **IBGE-DTB** (UF e região).
- **`municipios_informantes`:** municípios com numerador e denominador não nulos
  no ano, por UF.
- **Ressalvas:** nunca `avg(indice_*)`; ponderar por população urbana; 2022
  inválido para este mart.

### Mart 2 — `esgoto_coleta_tratamento_ano`

- **Pergunta:** quanto do esgoto é coletado e tratado no Brasil, por ano?
- **Grão:** ano (Brasil).
- **Fórmula (coleta):** `sum(volume_esgoto_coletado) / sum(volume_agua_consumido)`.
- **Fórmula (tratamento):**
  `sum(volume_esgoto_tratado) / sum(volume_esgoto_coletado)`.
- **Denominador:** **volume SNIS** (água consumida para coleta; esgoto coletado
  para tratamento) — mesmo universo volume/volume.
- **Ano(s) de referência:** 1995–2022 (volumes presentes em 2022).
- **Fontes:** SNIS.
- **`municipios_informantes`:** municípios com os volumes não nulos no ano
  (cobertura de esgoto ~41,8k, bem menor que água).
- **Ressalvas:** `CASE WHEN den>0`; muitos municípios sem esgoto; definição
  oficial (esgoto importado/exportado) a confirmar.

### Mart 3 — `perdas_consumo_uf_ano`

- **Pergunta:** quanto de água se perde na distribuição e quanto cada pessoa
  consome, por UF e ano?
- **Grão:** ano × UF (+ região via IBGE-DTB).
- **Fórmula (perdas):**
  `sum(volume_agua_produzido - volume_agua_consumido) / sum(volume_agua_produzido)`.
- **Fórmula (consumo per capita):**
  `sum(volume_agua_consumido)*1000 / (sum(populacao_atendida_agua)*365)` (L/hab·dia).
- **Denominador declarado:** perdas → **volume SNIS** (`volume_agua_produzido`);
  consumo → **população atendida SNIS** (`populacao_atendida_agua`, **não** IBGE).
- **Ano(s) de referência:** 1995–2022.
- **Fontes:** SNIS; **IBGE-DTB** (UF e região).
- **`municipios_informantes`:** municípios com volumes/população não nulos no ano.
- **Ressalvas:** definição oficial de perdas (IN049, "volume disponibilizado" =
  produzido + importado − exportado − serviço) a confirmar; ponderar por volume
  e por população; nunca `avg(indice_*)`.

### Mart 4 — `ranking_atendimento_variacao`

- **Pergunta:** quais municípios mais melhoraram ou pioraram no atendimento entre
  dois anos fixos?
- **Grão:** município (com comparação entre dois anos fixos).
- **Fórmula:** atendimento urbano de água por município
  (`populacao_urbana_atendida_agua / populacao_urbana`) em cada ano; variação =
  ano_fim − ano_início; `rank()`/`ntile()` sobre a variação (window function).
- **Denominador:** **urbano SNIS** (`populacao_urbana`).
- **Ano(s) de referência:** dois anos fixos (ex. **2010 e 2021**; nunca 2022).
- **Fontes:** SNIS; **IBGE-DTB** (UF/região para recorte).
- **`municipios_informantes`:** apenas municípios do **painel fixo** (presentes
  nos dois anos com dado não nulo).
- **Ressalvas:** **painel fixo obrigatório**; declarar os dois anos; `CTE` com
  `lag()`/`rank()`.

### Mart 5 — `financeiro_uf_ano`

- **Pergunta:** quanto se investe e se gasta por UF e ano (valores nominais)?
- **Grão:** ano × UF (+ região via IBGE-DTB).
- **Fórmula:** agregados por UF/ano de `sum(investimento_total_prestador)`,
  `sum(despesa_total_servico)` (**FN017/DTS**) e `sum(despesa_exploracao)`
  (**FN015/DEX**); indicadores derivados como razões do mesmo ano
  (ex. `sum(despesa_total_servico)/sum(receita_operacional_direta)`). **D27:** a
  `despesa_unitaria` (IN003) usa **FN017 = `despesa_total_servico`**, não a DEX;
  tarifa média (IN004) = `receita_operacional_direta` (FN001) ÷ (AG011+ES007),
  em R$/m³ (÷1.000 no volume).
- **Denominador:** quando houver razão, **mesmo ano e mesmo universo SNIS**.
- **Ano(s) de referência:** 1995–2022 (presentes em 2022).
- **Fontes:** SNIS; **IBGE-DTB** (UF e região).
- **`municipios_informantes`:** municípios com valores financeiros não nulos
  (investimento ~84,9k; cobertura menor em 2022: 4.672).
- **Ressalvas:** **R$ nominal** — só comparar dentro do mesmo ano; flag
  `valor_nominal=true`; não comparar anos sem correção.

### Mart 6 — `atendimento_porte_ano`

- **Pergunta:** como variam as coberturas de água e esgoto por faixa de população
  do município?
- **Grão:** ano × faixa de porte populacional.
- **Fórmula:** por faixa, `sum(populacao_atendida_agua) / sum(populacao_total_ibge)`
  e `sum(populacao_atendida_esgoto) / sum(populacao_total_ibge)`.
- **Denominador declarado:** **população total IBGE-POP**. A **faixa de porte**
  também é definida pela população IBGE-POP do município no ano.
- **Ano(s) de referência:** 2010–2021 (janela IBGE).
- **Fontes:** SNIS (atendidos); **IBGE-POP** (população total e porte).
- **`municipios_informantes`:** municípios com atendimento SNIS não nulo e
  população IBGE casada, por faixa.
- **Ressalvas:** exige **teste de cobertura de junção** SNIS×IBGE antes do join;
  numerador e denominador de universos distintos (atendidos SNIS vs. população
  total IBGE) — coberturas abaixo de 100% são esperadas.

### Mart 7 — `populacao_sem_servico_uf_ano`

- **Pergunta:** quantos habitantes, em números absolutos, estão sem esgoto
  coletado e sem água, por UF?
- **Grão:** ano × UF (+ região via IBGE-DTB).
- **Fórmula (absolutos):**
  `sum(populacao_total_ibge - populacao_atendida_agua)` (sem água) e
  `sum(populacao_total_ibge - populacao_atendida_esgoto)` (sem esgoto),
  com `greatest(..., 0)` por município.
- **Denominador declarado:** não é razão — é **diferença absoluta** entre
  **população total IBGE-POP** e população atendida SNIS.
- **Ano(s) de referência:** 2010–2021 (janela IBGE).
- **Fontes:** **IBGE-POP** (população total); SNIS (atendidos); **IBGE-DTB**
  (UF e região).
- **`municipios_informantes`:** municípios com população IBGE e atendimento SNIS
  não nulos no ano.
- **Ressalvas:** tratar atendido > total (revisões de série) com `greatest(.,0)`;
  teste de cobertura de junção antes do join.

### Mart 8 — `investimento_per_capita_uf_ano`

- **Pergunta:** quanto se investe por habitante, por UF e ano?
- **Grão:** ano × UF (+ região via IBGE-DTB).
- **Fórmula:** `sum(investimento_total_prestador) / sum(populacao_total_ibge)`.
- **Denominador declarado:** **população total IBGE-POP**.
- **Ano(s) de referência:** 2010–2021 (janela IBGE).
- **Fontes:** SNIS (investimento); **IBGE-POP** (população); **IBGE-DTB** (UF e
  região).
- **`municipios_informantes`:** municípios com investimento SNIS não nulo e
  população IBGE casada.
- **Ressalvas:** **R$ nominal** (R$/hab por ano, não comparável entre anos sem
  correção); ponderar por população; teste de cobertura de junção.

### Mart 9 — `atendimento_vs_pib_2021`

- **Pergunta:** como cobertura, perdas e investimento se relacionam com o PIB per
  capita do município em 2021?
- **Grão:** município, ano = **2021**.
- **Fórmula:** por município em 2021 — cobertura urbana de água/esgoto (ver
  Mart 1), perdas (ver Mart 3), investimento per capita (ver Mart 8); eixo de
  renda = `pib_municipio / populacao_total_ibge` (PIB per capita).
- **Denominador declarado:** coberturas → **urbano SNIS**; investimento per
  capita e PIB per capita → **população total IBGE-POP**.
- **Ano(s) de referência:** **2021** (urbano válido; último ano do PIB).
- **Fontes:** SNIS; **IBGE-PIB** (PIB); **IBGE-POP** (população).
- **`municipios_informantes`:** municípios com SNIS, PIB e população não nulos
  em 2021 e casados nas três fontes.
- **Ressalvas:** PIB **nominal** (um único ano, comparação válida); correlação ≠
  causalidade; teste de cobertura de junção nas três fontes. **PIB per capita
  negativo (D17):** há município com PIB negativo real do SIDRA (Guamaré/RN, 2012;
  em 2021 reavaliar na carga). Se o PIB per capita de 2021 for negativo, ele
  **permanece no dado**, **cai no menor quartil** e **não recebe transformação
  logarítmica** (log de valor ≤ 0 é indefinido) — nenhum filtro ou clamp.

### Mart 10 — `avanco_por_renda_painel`

- **Pergunta:** o atendimento avançou mais entre 2010 e 2021 em municípios de
  maior ou menor renda?
- **Grão:** quartil de PIB per capita × (dois anos: 2010 e 2021), em **painel
  fixo** de municípios.
- **Fórmula:** quartis de `pib_municipio/populacao_total_ibge` (base 2021) via
  `ntile(4)` (window function); por quartil,
  `sum(populacao_urbana_atendida_agua)/sum(populacao_urbana)` em 2010 e 2021 e a
  variação.
- **Denominador declarado:** cobertura → **urbano SNIS** (`populacao_urbana`);
  quartil → **PIB per capita (IBGE-PIB / IBGE-POP)**.
- **Ano(s) de referência:** **2010 e 2021**, painel fixo.
- **Fontes:** SNIS; **IBGE-PIB**; **IBGE-POP**.
- **`municipios_informantes`:** apenas municípios do **painel fixo** presentes
  em 2010 e 2021 nas três fontes.
- **Ressalvas:** **painel fixo obrigatório**; declarar a mudança de cobertura;
  `ntile` sobre renda; nunca `avg(indice_*)`. **PIB per capita negativo (D17):**
  permanece no dado e **cai no menor quartil** do `ntile(4)` (a ordenação trata o
  negativo como o menor valor, naturalmente no 1º quartil); **não aplicar
  transformação logarítmica** ao PIB per capita (log indefinido para ≤ 0).

---

## Resumo em tabela

| Mart | Grão | Fontes | Ano(s) | Pondera por |
|---|---|---|---|---|
| 1 `atendimento_uf_ano` | ano × UF | SNIS, IBGE-DTB | 2021 | pop. urbana |
| 2 `esgoto_coleta_tratamento_ano` | ano (BR) | SNIS | 1995–2022 | volume |
| 3 `perdas_consumo_uf_ano` | ano × UF | SNIS, IBGE-DTB | 1995–2022 | volume/pop. atendida |
| 4 `ranking_atendimento_variacao` | município (2 anos) | SNIS, IBGE-DTB | 2 anos fixos | pop. urbana (painel) |
| 5 `financeiro_uf_ano` | ano × UF | SNIS, IBGE-DTB | 1995–2022 | — (nominal) |
| 6 `atendimento_porte_ano` | ano × porte | SNIS, IBGE-POP | 2010–2021 | pop. total IBGE |
| 7 `populacao_sem_servico_uf_ano` | ano × UF | IBGE-POP, SNIS, IBGE-DTB | 2010–2021 | absolutos |
| 8 `investimento_per_capita_uf_ano` | ano × UF | SNIS, IBGE-POP, IBGE-DTB | 2010–2021 | pop. total IBGE (nominal) |
| 9 `atendimento_vs_pib_2021` | município | SNIS, IBGE-PIB, IBGE-POP | 2021 | — (nominal) |
| 10 `avanco_por_renda_painel` | quartil × 2 anos | SNIS, IBGE-PIB, IBGE-POP | 2010 e 2021 | pop. urbana (painel) |

---

## O que NÃO dá para calcular (e por quê)

- **Qualquer indicador urbano em 2022:** `populacao_urbana` e as atendidas
  urbanas são **100% nulas em 2022**. Usar 2021.
- **Séries financeiras comparáveis entre anos sem correção:** valores em R$ são
  **nominais** e não há deflator na silver. Comparação inter-anual exige
  correção externa.
- **Atendimento total de água/esgoto apenas com SNIS:** sem a população total
  residente; só é possível com **IBGE-POP** (marts 6–8).

---

## Ressalvas de catálogo e "a confirmar"

- **Definições oficiais do SNIS** (IN005/IN006/IN022/IN023/IN049 etc.,
  denominador de tarifa, composição de "volume disponibilizado", conversão de
  unidade do per capita) — **a confirmar** no dicionário do SNIS.
- **Semântica fina das colunas** de investimento (prestador vs. município vs.
  estado) e de receita (direta vs. indireta) — **a confirmar**.
- **Cobertura de junção SNIS×IBGE** será medida antes de qualquer join
  (convenção do catálogo [`fontes-ibge.md`](fontes-ibge.md)).

---

## Itens "a revisar" (conflitos com a versão anterior deste arquivo)

A versão anterior organizava o arquivo em **10 fichas de indicador** e sugeria
**5 marts de gold**. A reorganização em 10 marts preserva o conteúdo, mas os
pontos abaixo mudaram e ficam marcados **a revisar**:

- **Atendimento total de água (antiga ficha #2):** antes "Dá, mas… falta
  denominador". **A revisar:** agora é possível via **IBGE-POP** (marts 6–8); a
  pilha "Dá, mas…" deixa de valer.
- **Dimensão de UF por seed:** a versão anterior citava "seed/tabela de
  referência das 27 UFs ligada por `sigla_uf`". **A revisar:** substituída por
  **IBGE-DTB** (UF e região por `id_municipio`).
- **Tarifa média / despesa unitária (antigas fichas #8 e #9):** não entraram
  como mart próprio na lista de 10. **A revisar:** mantidas como indicadores
  derivados possíveis dentro de `financeiro_uf_ano` (mart 5); confirmar se devem
  virar mart separado.
- **Consumo per capita com denominador:** a antiga ficha #7 usava
  `populacao_atendida_agua`; o mart 3 mantém esse denominador **SNIS**
  explicitamente (não IBGE). **A revisar** apenas para alinhar a redação.
