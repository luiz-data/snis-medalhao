# Spec do dashboard SNIS (Streamlit) — aula 4

| | |
|---|---|
| **Status** | **aprovada** (2026-11-09) — D34–D39 APROVADAS em [`decisoes.md`](decisoes.md). Fase B em etapas. |
| **Versão** | 0 (proposta) |
| **Data** | 2026-11-09 |
| **Responsável** | Luiz |
| **Camada de origem** | **somente `schema gold`** do `snis.duckdb`, modo **somente leitura** |
| **Depende de** | gold fechada (10 marts, `tests/test_gold.py` verdes) · [`spec-gold.md`](spec-gold.md) · [`indicadores.md`](indicadores.md) · [`decisoes.md`](decisoes.md) (D1–D33) · README §"Limitações conhecidas" |

> Esta spec aplica as decisões **D1–D33** como estão. As decisões novas aparecem
> como **PENDENTES (D34–D39)** e só vão para [`decisoes.md`](decisoes.md) **depois
> da sua aprovação**. Nenhum valor numérico é escrito à mão: os cartões e o resumo
> executivo são travados por teste contra o banco (seção 11).

---

## 0. Preparação (passo 0) — o que foi verificado

**0a. Árvore git:** limpa. `main` sincronizada com `origin/main` (0 commits à
frente) → **o push do Bloco 5 já foi feito**. Única pendência: `design/` não
rastreado (imagens de referência; não é código).

**0c. Imagens `design/referencias/` (só estilo/layout, nunca marca):** inspiração
visual tomada de **dois dashboards ambientais/ESG de terceiros**; aproveitamos
**só estilo e layout**, nunca conteúdo ou marca. As **imagens não são versionadas**
(`design/referencias/` está no `.gitignore`). Inspiração
tomada = **tema escuro**, **faixa superior de cartões de KPI** (valor grande +
rótulo + barra/sparkline), **séries em área/linha**, **tabela com mapa de calor
por célula**, **coluna lateral de resumo executivo**. **Descartado** das
referências (regra do pedido): logotipos, nome de empresa, selos tipo "dados
auditáveis", menu vertical de navegação por página.

**0d. Colunas reais das 10 tabelas gold (via MCP, somente leitura).** Toda coluna
citada nesta spec existe nestas listas; nada fora delas vai para a tela.

| Mart (tabela gold) | Colunas reais |
|---|---|
| 1 `atendimento_uf_ano` | `ano, sigla_uf, nome_uf, nome_regiao, cobertura_urbana_agua, cobertura_urbana_esgoto, municipios_informantes_agua, municipios_informantes_esgoto, excluidas_a2_agua, excluidas_a2_esgoto, linhas_excluidas_a2` |
| 2 `esgoto_coleta_tratamento_ano` | `ano, indice_coleta_esgoto, indice_tratamento_esgoto, indice_coleta_painel, indice_tratamento_painel, municipios_informantes_coleta, municipios_informantes_tratamento, municipios_painel_coleta, municipios_painel_tratamento, excluidas_den_zero_coleta, excluidas_den_zero_tratamento, municipios_tratado_acima_coletado, serie_robusta` |
| 3 `perdas_consumo_uf_ano` | `ano, sigla_uf, nome_uf, nome_regiao, indice_perdas_in049, consumo_per_capita, municipios_informantes_perdas, municipios_informantes_consumo, linhas_inconsistentes_in049, excluidas_den_nao_positivo, excluidas_consumo_acima, linhas_consumo_liquido_negativo` |
| 4 `ranking_atendimento_variacao` | `id_municipio, sigla_uf, nome_uf, nome_regiao, cobertura_2010, cobertura_2021, variacao_pp, posicao, posicao_empate, variacao_extrema` |
| 5 `financeiro_uf_ano` | `ano, sigla_uf, nome_uf, nome_regiao, investimento_total, investimento_total_sem_atipicos, despesa_total_servicos, despesa_exploracao_dex, receita_operacional_direta, indice_despesa_sobre_receita, tarifa_media, despesa_unitaria, municipios_informantes_investimento, municipios_informantes_tarifa, municipios_informantes_despesa, municipios_investimento_atipico` |
| 6 `atendimento_porte_ano` | `faixa_porte, ano, pop_total_ibge, municipios_faixa, pop_informante_agua, pop_informante_esgoto, cobertura_agua, cobertura_esgoto, cobertura_esgoto_entre_informantes, municipios_informantes_agua, municipios_informantes_esgoto` |
| 7 `populacao_sem_servico_uf_ano` | `ano, sigla_uf, nome_uf, nome_regiao, pop_total_ibge, pop_informante_agua, pop_sem_agua, pop_sem_informacao_agua, pop_sem_esgoto, pct_sem_agua, pct_sem_esgoto, municipios_informantes_agua, municipios_sem_informacao_agua, municipios_informantes_esgoto` |
| 8 `investimento_per_capita_uf_ano` | `ano, sigla_uf, nome_uf, nome_regiao, investimento_per_capita_com_atipicos, investimento_per_capita_sem_atipicos, investimento_total, investimento_total_sem_atipicos, pop_informante_investimento, municipios_informantes, municipios_investimento_atipico, valor_nominal` |
| 9 `atendimento_vs_pib_2021` | `id_municipio, sigla_uf, nome_uf, nome_regiao, cobertura_urbana_agua, cobertura_urbana_esgoto, informou_esgoto, cobertura_urbana_agua_acima_100, cobertura_urbana_esgoto_acima_100, perdas_in049, investimento_per_capita, pib_per_capita, investimento_atipico` |
| 10 `avanco_por_renda_painel` | `quartil_pib, ano, cobertura_urbana_agua, municipios_painel, variacao_pp, reducao_relativa_deficit` |

**Achado decisivo do 0d:** **nenhum mart agregado** (1, 3, 5, 6, 7, 8) expõe uma
linha **"Brasil"** nem o **numerador/denominador** necessário para recompor o
nacional. Só o **mart 2** já é nacional por ano. Logo, os **cartões de KPI
nacionais** e o **resumo executivo** não podem ser montados sem `sum()`/soma‑sobre‑
soma **na tela** — proibido pela regra 7(b). Isso **obriga um mart de apoio
`11_kpis_brasil`** (seção 9), confirmado no MCP:
- somar `pop_sem_esgoto`/`pop_sem_agua` por UF **é cálculo na tela**; e
- `cobertura_esgoto` nacional do mart 6 **não é recomponível** (numerador de
  atendidos não está na tabela), idem água urbana do mart 1 e perdas do mart 3.

**0e. O que a aula 4 pede e a nossa spec (gold) ainda não cobre — em 8 linhas:**
1. Separar **consultas/gráficos** (`painel.py`) de **montagem de página** (`app.py`).
2. **Não calcular na tela** (sem `groupby/sum/mean/merge` em `painel.py`/`app.py`).
3. **Cache** (`st.cache_data`) + botão "Recarregar dados".
4. **Erro tratado** quando falta banco/mart (`st.error` + `st.stop()`).
5. **Tema** por `.streamlit/config.toml` e **formatação própria** de R$/%/número
   (sem depender de `locale`).
6. **Cartões de KPI** e **resumo executivo** por modelo de frase (campos do mart).
7. **Testes unitários** da formatação/montagem em `tmp_path`, sem tocar no banco;
   separados dos testes de qualidade de dados da gold.
8. **Mart de KPIs nacionais (11)** e as conferências **C9/C10** como requisitos de
   tela — **nenhum deles existe hoje** na gold; esta spec os especifica.

---

## 1. Quem lê e o que decide

**Público:** **diretoria/decisores sem tempo** (SNIS, secretarias, imprensa de
dados). Leem em pé, 5 segundos, sem manual.

**A primeira coisa que precisam saber (acima de tudo):** **quantos brasileiros
ainda estão sem água e sem coleta de esgoto por rede, hoje (2021)** — em
**número absoluto** e em **%**.

**Objetivo (5 linhas, sem marketing):**
1. Mostrar, em uma tela, o **estado do saneamento no Brasil em 2021** (água,
   esgoto, déficit absoluto) e sua **evolução** onde a série permite.
2. Dar o número **nacional** correto (soma‑sobre‑soma pré‑agregada), nunca a média
   de médias.
3. Deixar **ver as desigualdades** por UF, região, porte e renda sem afirmar causa.
4. **Rotular cada número** com ano, unidade, fonte e universo de informantes.
5. Ser **auditável pela gold**: todo elemento aponta um mart e colunas reais.

**Ordem de leitura em Z:** canto superior‑esquerdo = **cartões de KPI** (o déficit
primeiro) → topo‑direito = **resumo executivo** (frases‑modelo) → meio‑esquerda =
**evolução** (séries) → meio/baixo = **desigualdade** (porte, UF, renda) →
rodapé = **notas e fontes**.

**Grade de 12 colunas (regras de layout):**
- Faixa de KPIs: 4 cartões de 3 col cada (`4 × 3 = 12`).
- Faixa de conteúdo: **8 col** (gráfico principal) + **4 col** (resumo/nota).
- Gráficos lado a lado: **6 + 6**.
- Tabelas largas (ranking): **12 col**, altura fixa com rolagem interna.
- Gutter de 16px; nada abaixo de 3 colunas de largura; **mobile** empilha em 1
  coluna (cartões viram lista).

---

## 2. Não‑objetivos (o que o painel NÃO faz)

- **Sem previsão / projeção** de séries.
- **Sem causalidade** — só associação; nenhuma frase do tipo "renda causa avanço"
  (Spearman renda×avanço ≈ 0; D33).
- **Sem deflacionar** valores — R$ **nominais**, comparados só dentro do ano (D22).
- **Sem recomendar política** pública.
- **Sem mapa coroplético de municípios** — a gold **não** tem geometria/shape nem
  um mart que a sustente; desigualdade territorial vai por **tabela/ranking/barras
  por UF e região**, não por mapa.
- **Sem indicador urbano em 2022** (população urbana 100% nula; D2).
- **Sem cruzar mart 6 (total) com mart 1 (urbano)** — universos distintos (D29 vs D2).
- **Sem esgoto no recorte de renda** (mart 10 é **água‑only**, D33).

---

## 3. Desenho da tela

**Organização proposta (PENDENTE D35):** **uma página única em faixas** com
**filtro no cabeçalho**, mais **uma aba de detalhe** (ranking, renda, porte). Duas
abas no topo: **"Visão Brasil"** (a página única) e **"Detalhe"**.
Justificativa: a diretoria lê a Visão Brasil em 5 s; quem quer aprofundar abre o
Detalhe. Evita o menu de 10 páginas das referências (ruído para o público‑alvo).

**Filtro — quem reage a quê (ponto 4):**
- **Visão Brasil:** o cabeçalho tem **só `Ano`** + botão **Recarregar dados**.
  O mart 11 é **Brasil × ano**, então **não há filtro de Região na Visão Brasil**.
  Reagem ao **Ano**: os 6 cartões e o resumo (mart 11) e as barras de porte
  (mart 6). **Ignoram o Ano** (recorte fixo, com o ano selecionado só destacado):
  a série de coleta/tratamento (mart 2, 1995–2022) e o avanço por renda (mart 10,
  2010/2021).
- **Aba Detalhe:** ganha o filtro de **Região/UF** (marts com UF: **4** ranking,
  **5** financeiro, **9** renda×PIB). A Região **não** aparece na Visão Brasil.

> **Artefato a aprovar:** `design/rascunho.png` (mock estático do layout abaixo).
> Será **produzido após a aprovação desta spec** — não é gerado agora (sem código
> nesta fase). O ASCII abaixo é o contrato do mock.

### Faixa A — cabeçalho + KPIs (12 col · **3 colunas temáticas** × 2 linhas)
```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Saneamento no Brasil — SNIS                        [Ano: 2021 ▼] [↻ Recarregar] │
│  Indicadores urbanos só até 2021 (nunca 2022). Região só na aba Detalhe.         │
├─ ÁGUA ──────────────────┬─ ESGOTO ────────────────┬─ GESTÃO ───────────────────┤
│ Água (IN055) 2021       │ Esgoto (IN056) 2021     │ Perdas (IN049) 2021        │
│  84,20%                 │  55,81%                 │  36,86%  (ver nota)        │
│  mart 11←6 · base pop.  │  mart 11←6 · cobertura  │  mart 11←3                 │
│  total IBGE (inf. água) │  por POPULAÇÃO          │                            │
├─────────────────────────┼─────────────────────────┼────────────────────────────┤
│ Sem água 2021 (piso)    │ Sem esgoto 2021         │ Investimento per capita    │
│  33,3 mi · 15,84%       │  92,9 mi · 44,19%       │  R$ 75,82/hab (nominal)    │
│  mart 11←7 · piso: 258  │  mart 11←7 · por rede;  │  mart 11←8 · entre quem    │
│  mun. sem info fora     │  fossa = sem esgoto     │  declarou investimento     │
└─────────────────────────┴─────────────────────────┴────────────────────────────┘
  coluna ÁGUA (4 col)       coluna ESGOTO (4 col)     coluna GESTÃO (4 col)
```
> **3 colunas temáticas:** **Água** (IN055 em cima, "sem água" embaixo), **Esgoto**
> (IN056 em cima, "sem esgoto" embaixo), **Gestão** (perdas em cima, investimento
> per capita embaixo). Os 4 cartões de cobertura/déficit têm base **informantes de
> água** (pop. total IBGE, D29/D30). A **água urbana** (mart 1, 93,33%) vai para o
> **Detalhe** (E15) — medida distinta do IN055, válida só até 2021.
### Faixa B — evolução (8 col) + resumo executivo (4 col)
```
┌───────────────────────────────────────────┬─────────────────────────────┐
│ Índice de coleta de esgoto                 │ RESUMO EXECUTIVO            │
│ (volume coletado ÷ consumido) — mart 2     │ • Em 2021, 44,19% (92,9mi) │
│ + tratamento (tratado ÷ coletado)          │   sem coleta de esgoto…     │
│   coleta ▁▂▃▄▅   tratamento ▁▃▅▇  %·1995–22│ • Água (IN055) 84,20%       │
│   nota: índice por VOLUME ≠ cartão         │ • Perdas (IN049) 36,86%     │
│   "cobertura de esgoto por rede" (pop.);   │ • Trat. 80,33% / col. 56,02%│
│   56,02% ≠ 55,81% (definições distintas);  │  (4 col, frases‑modelo)     │
│   robusto ≥ 2006                           │                             │
└───────────────────────────────────────────┴─────────────────────────────┘
```
### Faixa C — desigualdade por porte (6 col) + por renda (6 col)
```
┌─────────────────────────────┬─────────────────────────────┐
│ Cobertura por porte 2021     │ Avanço por renda 2010→2021  │
│ água IN055 / esgoto IN056    │ (água‑only, painel 4.472)   │
│ barras agrupadas · 6 faixas  │ barras: cobertura + Δpp     │
│  nota: total IBGE (≠ mart 1) │  nota: só água urbana       │
└─────────────────────────────┴─────────────────────────────┘
```
### Faixa D — rodapé (12 col): fontes, janela, universo de informantes, C9/C10.

### Aba "Detalhe"
```
[ Ranking municípios (mart 4) | Renda × PIB (mart 9) | Financeiro por UF (mart 5) ]
- Ranking: tabela 12 col, heatmap na coluna variacao_pp, filtro UF/região, flag variacao_extrema.
- Renda × PIB: dispersão cobertura×pib_per_capita (mart 9), flag investimento_atipico, nota "associação".
- Financeiro: barras por UF (investimento_total nominal), toggle com/sem atípicos, nota RN.
```

---

## 4. Tabela de rastreabilidade (um elemento por linha)

Nenhum elemento sem mart e colunas verificados no 0d. "A→D" = faixa.

| # | Elemento (faixa) | Pergunta que responde | Mart | Colunas | Filtro | Forma | Armadilha dos dados | Rótulo/nota obrigatórios |
|---|---|---|---|---|---|---|---|---|
| E1 | Cartão "Sem esgoto (rede)" (A) | Quantos sem coleta por rede? | **11** (apoio) | `pop_sem_esgoto_br, pct_sem_esgoto_br` | Ano | KPI + sparkline | IN056; fossa = sem rede; abs. oficial ≈100 mi não reconciliado | "sem **coleta por rede** · IN056 · 2021 · SNIS+IBGE" |
| E2 | Cartão "Sem água" (A) | Quantos sem água? | **11** | `pop_sem_agua_br, pct_sem_agua_br` | Ano | KPI + sparkline | é um **piso** (não‑informantes fora: 3,13 mi) | "piso · exclui 258 mun. sem informação · 2021" |
| E3 | Cartão "Água (IN055)" (A) | % com água (total)? | **11** | `cobertura_agua_in055_br` | Ano | KPI | base pop. **total IBGE** dos informantes de água; **não** é urbano | "IN055 · base pop. **total** IBGE (informantes de água) · 2021" |
| E4 | Cartão "Esgoto (IN056)" (A) | % com esgoto por rede (população)? | **11** | `cobertura_esgoto_in056_br` | Ano | KPI | **cobertura por POPULAÇÃO** (IN056) ≠ índice de coleta por volume (E5); 55,81 ≠ 56,02 | "IN056 · cobertura por **população** · base total IBGE · 2021" |
| E5 | Índice de coleta/tratamento (B) | O esgoto avança (por volume)? | **2** (via `ler_esgoto_robusto`) | `ano, indice_coleta_esgoto, indice_tratamento_esgoto, serie_robusta` | — (**janela robusta 2006–2022**; ignora o Ano) | Linha | **índice por VOLUME** (coletado÷consumido) ≠ cobertura por população (E4); 1995–2005 omitido (não robusto; 1998/1999 coleta >100%) | "Índice de coleta de esgoto (volume coletado ÷ consumido) · % · SNIS · 2006–2022 · **≠ cobertura por rede (pop.)**"; nota do período omitido; teste `test_ler_esgoto_robusto_exclui_acima_100` |
| E6 | Resumo executivo (B) | Síntese em 3 frases | **11** | campos da seção 6 | Ano | Texto‑modelo | nenhum número à mão; sem causa | fonte+ano embutidos |
| E7 | Barras por porte (C) | Cobertura cresce com porte? | **6** | `faixa_porte, cobertura_agua, cobertura_esgoto` | Ano | Barras agrupadas | **base total IBGE** (≠ mart 1); faixa1>faixa2 água (fato) | "IN055/IN056 · total IBGE · não cruzar com urbano"; **legenda em texto "Água"/"Esgoto"** (cor nunca é o único significado, 7k); nota/legenda **≥ 12 px** |
| E8 | Barras por renda (C) | Avanço por quartil | **10** | `quartil_pib, ano, cobertura_urbana_agua, variacao_pp` | — (2010/2021) | Barras + Δpp | **água‑only**; painel 4.472 (8,4% pop fora) | "só **água urbana** · painel · 2010→2021" |
| E9 | Tabela ranking (Detalhe) | Quem mais melhorou/piorou? | **4** | `id_municipio, nome_uf, cobertura_2010, cobertura_2021, variacao_pp, posicao, variacao_extrema` | UF/região | Tabela + heatmap | A2 excluído; 12 extremos; não antes de 2010 | "painel 4.472 · variação extrema sinalizada" |
| E10 | Dispersão renda×cobertura (Detalhe) | Relação com PIB? | **9** | `pib_per_capita, cobertura_urbana_agua, investimento_atipico, informou_esgoto` | UF/região | Dispersão | **associação, não causa**; esgoto só informantes | "2021 · associação · esgoto entre informantes" |
| E11 | Barras financeiro UF (Detalhe) | Quanto se investe/UF? | **5** | `nome_uf, investimento_total, investimento_total_sem_atipicos, municipios_investimento_atipico` | Ano/UF | Barras + toggle | R$ **nominal**; atípicos visíveis; nota RN | "R$ nominal · comparar só no ano · RN afetada" |
| E12 | Nota de informantes (B) | Quão representativo? | **2** | `municipios_informantes_coleta` | — | Texto | leitura muda com informantes | número de informantes exibido · teste `test_nota_informantes` |
| E13 | Reconciliação C9/C10 (D) | Região soma = Brasil? | 1/3/5 + 11 | ver seção 8 | Ano | Nota/teste | — | rodapé + `test_c9_cobertura_ponderada_regiao`, `test_c9_regiao_soma_brasil`, `test_c10_anos_consistentes` |
| E15 | Cartão "Água urbana" (**Detalhe**) | % urbano com água? | **11** (`cobertura_urbana_agua_br`) / mart 1 | Ano(≤2021) | KPI | urbano SNIS ≠ IN055; só ≤2021; **não comparar com IN055** | "cobertura **urbana** · SNIS · ≤2021 · não comparável ao IN055" |
| E16 | Cartão "Investimento per capita" (A) | Quanto se investe por habitante? | **11** (`investimento_per_capita_br`) | Ano | KPI | R$ **nominal**; universo comum (entre quem declarou investimento, D31) | "R$/hab · **nominal** · entre quem declarou investimento · 2021" |
| E14 | Cartão/nota "Perdas (IN049)" (B/Detalhe) | Quanto de água se perde? | **11** (`perdas_in049_br`) | Ano | KPI | per‑year ≠ pooled; não reconciliado | **Nota fixa:** "Cálculo próprio pela fórmula do SNIS; pode diferir de valores divulgados (diferença não reconciliada)." (sem número publicado) |

---

## 5. Cartões de KPI

Valor **esperado hoje** lido do banco por MCP (2026-11-09). Cada um é travado por
teste em `tests/test_gold.py` (coluna "trava"). Marts agregados **não** têm linha
Brasil → o número vem do **mart 11** (seção 9); **mart 2** serve direto.

| Cartão | Valor hoje (2021) | Unidade | Mart entrega | Trava (teste) |
|---|---|---|---|---|
| **Sem esgoto (rede)** | **92.879.110** (44,19%) | hab · % | **11** (`pop_sem_esgoto_br`, `pct_sem_esgoto_br`) | `test_m11_sem_esgoto_2021` = Σ mart 7 |
| **Sem água** (piso) | **33.285.121** (15,84%) | hab · % | **11** (`pop_sem_agua_br`, `pct_sem_agua_br`) | `test_m11_sem_agua_2021` = Σ mart 7 |
| **Água (IN055)** (cartão A) | **84,20%** | % | **11** (`cobertura_agua_in055_br`) | `test_m11_valores_2021` = 84,20% (mart 6) |
| **Esgoto (IN056)** (cartão A) | **55,81%** | % | **11** (`cobertura_esgoto_in056_br`) | `test_m11_valores_2021` = 55,81% (mart 6) |
| **Água urbana** (Detalhe, E15) | **93,33%** | % | **11** (`cobertura_urbana_agua_br`) | `test_m11_cross_2021_marts_origem` ∈ [93,2; 93,5] (D5) |
| **Tratamento de esgoto** | **80,33%** | % | **2** direto (`indice_tratamento_esgoto`) | `test_m2_tratamento_2021` ≈ 80,3% |
| **Coleta de esgoto** | **56,02%** | % | **2** direto (`indice_coleta_esgoto`) | `test_m2_coleta_2021` ≈ 56% |
| **Perdas de água (IN049)** | **36,86%** (2021; o 37,42% é o **pooled 2010–2021**, não um ano) | % | **11** (`perdas_in049_br`) | `test_m11_perdas_por_ano_nao_e_pooled` = 36,86% |
| **Consumo per capita** | **151,3** | L/hab·dia | **11** (`consumo_per_capita_br`) | `test_m11_consumo_2021` ≈ 151 (IN022) |
| **Investimento total** | **R$ 15.297.535.452,19** | R$ nominal | **11** (`investimento_total_br`) = Σ mart 5 | `test_m11_investimento_2021` = mart 5 |
| **Investimento per capita** | **R$ 75,82/hab** | R$/hab nominal | **11** (`investimento_per_capita_br`) | `test_m11_inv_pc_2021` = 75,82 (mart 8/D31) |

> Mínimo pedido (água, esgoto IN056, sem esgoto por rede) ✓ coberto. Os **6
> cartões** em tela (Faixa A, 2 linhas × 3) são **Sem esgoto, Sem água, Esgoto
> (IN056)** (linha 1) e **Água (IN055), Perdas (IN049), Investimento per capita**
> (linha 2) — todos com base/denominador rotulado. A **água urbana** (mart 1) vai
> para o **Detalhe** (E15), por ser medida distinta do IN055 e só válida até 2021.
> Consumo per capita, tratamento e coleta ficam em nota/Detalhe.

**Por que o mart 11 (e não cálculo na tela):** `cobertura_esgoto` nacional do
mart 6 não é recomponível sem o numerador de atendidos (não exposto); perdas e
água urbana exigem soma‑sobre‑soma de colunas que não estão nas tabelas por UF; e
somar `pop_sem_*` por UF seria `sum()` **na tela** (proibido, 7b). Medido no MCP:
proxy de perdas ponderado por município dá **38,84%** ≠ **36,86%** (soma/soma por
volume, 2021) — prova de que o número correto **tem que vir pré‑agregado**.

**Perdas — nota de não reconciliação (obrigatória no cartão):** o IN049 nacional
calculado pela fórmula D3 é **36,86% em 2021**. As exclusões (a)+(c) são
**imateriais**: 23 municípios em 2021 mudam o índice em **+0,0002 pp**
(36,8610% → 36,8612%). **Valor publicado não confirmado:** as fontes oficiais do
SNIS divergem para o ano‑base 2021 (MDR cita **39,3%**; Min. das Cidades /
Diagnóstico Temático de Gestão Técnica cita **40,3%**; os **40,1%** são de
**2020**) e não foi localizada a tabela primária com ano‑base inequívoco → **o
painel não cita número publicado**, só registra que o valor da gold difere das
divulgações oficiais. O **37,42%** é o **agregado 2010–2021 (pooled)**, não o
valor de um ano — nunca rotular como "oficial". Redação do cartão em E14 (seção 4).

---

## 6. Resumo executivo (frases‑modelo)

**Proibido** texto à mão com números e **proibida** explicação causal. Cada frase
é um **template** com campos preenchidos por colunas do **mart 11** (ou mart 2).

| Template | Campos (mart 11, salvo nota) | Exemplo renderizado (2021) |
|---|---|---|
| "Em {ano}, {pct_sem_esgoto}% da população ({pop_sem_esgoto} hab) estava **sem coleta de esgoto por rede**." | `ano, pct_sem_esgoto_br, pop_sem_esgoto_br` | "Em 2021, 44,19% (92,9 mi) sem coleta de esgoto por rede." |
| "{pct_sem_agua}% ({pop_sem_agua} hab) sem água — número **mínimo**, fora {mun_sem_info} municípios sem informação." | `pct_sem_agua_br, pop_sem_agua_br, municipios_sem_info_agua_br` | "15,84% (33,3 mi) sem água — mínimo…" |
| "A cobertura de água (**IN055**) era {agua_in055}% em {ano}." | `cobertura_agua_in055_br, ano` | "84,20% em 2021." |
| "O volume de esgoto **coletado** equivalia a {coleta}% do volume de **água consumida** e {tratamento}% do coletado era **tratado**." | `indice_coleta_esgoto_br, indice_tratamento_esgoto_br` | "coletado equivalia a 56,02% … e 80,33% … tratado." |
| "As **perdas** de água na distribuição somavam {perdas}% (IN049)." | `perdas_in049_br` | "36,86% (IN049)." |

**Frases‑modelo preenchidas com 2021 (o que `painel.frases_resumo` devolve):**
1. "Em 2021, 44,19% da população (92,9 mi) estava sem coleta de esgoto por rede."
2. "15,84% (33,3 mi) sem água — número mínimo, fora 258 municípios sem informação."
3. "A cobertura de água (IN055) era 84,20% em 2021."
4. "O volume de esgoto coletado equivalia a 56,02% do volume de água consumido e 80,33% do coletado era tratado."
5. "As perdas de água na distribuição somavam 36,86% (IN049)."

**Confirmação (regras 7j/perdas):** nenhuma frase **compara** o 36,86% com um valor
publicado, nenhuma cita número oficial, e **nenhuma afirma causa** (sem "porque",
"devido", "por isso"). A não reconciliação das perdas fica **só** na nota do cartão
E14, não no resumo. A frase de água usa **IN055** (base total IBGE), não a urbana.

Regras: números formatados pela seção 10 (R$/%/milhão). Cada frase embute **ano e
fonte**. Nenhuma frase liga renda a avanço (D33) nem atribui causa a nenhuma
diferença por porte/UF.

---

## 7. Regras de dado (numeradas e testáveis)

| # | Regra | Como se verifica (critério de aceite) |
|---|---|---|
| **a** | `painel.py` lê **só** `schema gold`, conexão **somente leitura** (`ler()`). | `grep` não acha `silver.`/`bronze.` em `painel.py`/`app.py`; conexão aberta `read_only=True`; teste `test_conexao_read_only`. |
| **b** | **Sem cálculo na tela:** proibidos `groupby`, `sum`, `mean`, `merge`, `.agg(` em `painel.py`/`app.py`. | teste `test_sem_operacoes_proibidas` faz `grep` dessas tokens no código e falha se achar. Toda agregação vem da gold/mart 11. |
| **c** | Indicadores **urbanos** (marts 1, 4, 9, 10) com seletor de ano **travado em 2021** + nota. | o seletor desses elementos não oferece 2022; `test_ano_urbano_apenas_2021`. |
| **d** | Esgoto **urbano** rotulado "entre os municípios que informam esgoto urbano", **nunca** ao lado do IN056 sem aviso (D29, D32). | revisão de rótulo (checklist §12) + `test_rotulo_esgoto_urbano` sobre as strings de rótulo. |
| **e** | Valores monetários **nominais**, comparar só **dentro do ano**, com rótulo "R$ nominal". | `test_rotulo_nominal`; seletor financeiro não permite comparar dois anos em um gráfico. |
| **f** | `investimento_atipico`/atípicos **visíveis e sinalizados**, nunca removidos em silêncio. | toggle exibe os dois valores; `municipios_investimento_atipico` sempre mostrado; `test_atipico_visivel`. |
| **g** | Marts **6 (total)** e **1 (urbano)** **nunca** cruzados no mesmo gráfico/eixo. | nenhum elemento mistura colunas dos dois; checklist §12 + `test_nao_cruza_m1_m6`. |
| **h** | Todo gráfico com **título, unidade, fonte e ano**. | `test_todo_grafico_tem_rotulo` valida o dicionário de specs de gráfico (seção 10). |
| **i** | **Número de informantes** exibido onde afeta a leitura (marts 1, 2, 6, 7). | nota de informantes presente; `test_nota_informantes`. |
| **j** | **Nenhum texto causal** onde a spec marcou hipótese (D33 renda; porte faixa1>faixa2; absoluto ≈100 mi). | `test_sem_texto_causal` faz `grep` de termos proibidos ("porque", "causa", "devido a") nas strings de narrativa. |
| **k** | Contraste legível no **tema escuro**; cor/ícone **nunca** como único portador de significado (rótulo textual sempre — ex.: legenda do porte com texto "Água"/"Esgoto"); **nota/legenda ≥ 12 px**. | `tema.contraste()` (11 pares passam) + `labelFontSize/titleFontSize ≥ 12` nas figuras + legenda de texto no mart 6. |
| **l** | Painel do **mart 10** sempre rotulado "municípios que informaram **água urbana nos 12 anos**", **só água**. | `test_rotulo_mart10`; o elemento E8 carrega o rótulo fixo. |

---

## 8. Conferências C9 e C10 (requisitos do dashboard)

**C9 — Região soma = Brasil (reconciliação região×UF).** Definição da
[`spec-gold.md`](spec-gold.md) §6: *"soma das coberturas **ponderadas por região**
bate com o agregado Brasil"*. Verificada nas **duas** formas:
- **(i) Cobertura ponderada por região (a forma da spec-gold):** a cobertura
  urbana de água **ponderada** (soma/soma dos numeradores e denominadores das 5
  regiões) = agregado Brasil do mart 11.
  `WITH r AS (SELECT d.nome_regiao, sum(populacao_urbana_atendida_agua) num,
  sum(populacao_urbana) den FROM silver.municipio_agua_esgoto s JOIN
  silver.ibge_dtb_municipio d USING(id_municipio) WHERE ano=2021 AND <A2 excluída>
  GROUP BY 1) SELECT sum(num)/sum(den)` = `kpis_brasil.cobertura_urbana_agua_br` =
  **93,33%** (5 regiões). Teste `test_c9_cobertura_ponderada_regiao`.
- **(ii) Absolutos agregáveis:** a soma das regiões dos **absolutos** (déficit do
  mart 7; investimento do mart 5) = agregado Brasil.
  `SELECT sum(pop_sem_esgoto) FROM gold.populacao_sem_servico_uf_ano WHERE ano=2021`
  = `pop_sem_esgoto_br` = **92.879.110**; investimento = **R$ 15.297.535.452,19**.
  Teste `test_c9_regiao_soma_brasil`.
- **Aceite:** percentual ponderado = agregado (≤ 0,01 pp); absolutos diferença **0**.
- **Onde aparece:** testes `test_c9_cobertura_ponderada_regiao` e
  `test_c9_regiao_soma_brasil` **e** nota de rodapé (Faixa D) "Brasil = Σ regiões ✓".

**C10 — perdas (mart 3) × financeiro (mart 5) consistentes no recorte exibido.**
- **Definição:** no conjunto de anos exibido, as séries de perdas e financeira
  cobrem os **mesmos anos** e o **mesmo universo declarado** (sem ano com um lado
  vazio e outro cheio que induza leitura falsa).
- **Consulta de verificação:** contagem de anos com `indice_perdas_in049` não nulo
  (mart 3) e com `investimento_total` não nulo (mart 5) no range do seletor — devem
  coincidir, ou a diferença é anotada.
- **Aceite:** anos exibidos têm os dois lados presentes; faltas sinalizadas.
- **Onde aparece:** **nota de rodapé** (Faixa D) com a janela efetiva; teste
  `test_c10_anos_consistentes`.

---

## 9. Marts de apoio (o que falta na gold) — só especificação

### Mart 11 — `gold.kpis_brasil` (PENDENTE D34)
- **Por que:** alimentar cartões (seção 5) e resumo executivo (seção 6) **sem
  cálculo na tela** (regra 7b). Nenhum mart atual expõe linha Brasil nem os
  numeradores para recompor o nacional.
- **Grão:** **(ano)** — Brasil. Linha por ano dentro da janela de cada indicador.
- **Roteiro (padrão aula 3):** grão (ano, Brasil) → chute (valores de hoje já
  medidos no MCP, seção 5) → **SELECT validado** (soma‑sobre‑soma a partir da
  **silver**, mesmas fórmulas dos marts) → arquivo `sql/gold/11_kpis_brasil.sql` +
  teste em `test_gold.py`, em **fases A/B próprias** (A: spec/aprovação; B: código).
- **Colunas (15, soma‑sobre‑soma nacional; R$ nominal pela regra 7e — `valor_nominal`
  foi removido por ser metadado constante):**
  `ano, cobertura_urbana_agua_br, cobertura_agua_in055_br, cobertura_esgoto_in056_br,
  indice_coleta_esgoto_br, indice_tratamento_esgoto_br, perdas_in049_br,
  consumo_per_capita_br, pop_sem_agua_br, pop_sem_esgoto_br, pct_sem_agua_br,
  pct_sem_esgoto_br, municipios_sem_info_agua_br, investimento_total_br,
  investimento_per_capita_br`. PK `ano`; janela 2010–2021.
- **Valores 2021 travados (SELECT validado por MCP):** água urbana 93,33%;
  IN055 84,20%; IN056 55,81%; coleta 56,02%; tratamento 80,33%; **perdas 36,86%
  (ano; pooled 2010–2021 = 37,42%)**; consumo 151,3 L/hab·dia; sem água 33.285.121
  (15,84%); sem esgoto 92.879.110 (44,19%); 258 municípios sem informação;
  investimento R$ 15.297.535.452,19; inv. per capita R$ 75,82/hab.
- **Status:** **IMPLEMENTADO** — `sql/gold/11_kpis_brasil.sql` (só SELECT, D20),
  executor já o monta, testes `test_m11_*` em `tests/test_gold.py` verdes.
- **Testes previstos:** igualdade com as somas dos marts 5/7 (C9), coincidência de
  IN055/IN056 com mart 6, perdas/consumo com mart 3, coleta/tratamento com mart 2.
- **Regra:** indicadores urbanos só 2010–2021; os demais na sua janela; nunca 2022
  no urbano.

> **Nenhum outro mart de apoio é necessário** para o escopo desta spec. Mapa
> coroplético exigiria uma fonte de geometria (fora do projeto) → fica em
> não‑objetivos, não em mart de apoio.

---

## 10. Arquitetura

```
app.py                      # monta a página (layout, filtros, cache, erros). SEM cálculo.
painel.py                   # consultas (SELECT na gold) + specs de gráfico. SEM cálculo.
formato.py                  # formatação R$/%/número sem locale.
.streamlit/config.toml      # tema escuro verde‑azulado (PENDENTE D37).
tests/test_dashboard.py     # testes unitários da tela (tmp_path, sem banco real).
```

- **`painel.py`:** uma função por consulta (`ler_kpis_brasil(ano)`,
  `ler_serie_esgoto()`, `ler_porte(ano)`, …), cada uma rodando **um SELECT** na
  gold e devolvendo o DataFrame **já agregado pela gold**; e uma função por gráfico
  devolvendo a spec (título, unidade, fonte, ano). **Proibido** `groupby/sum/mean/
  merge` aqui (7b).
- **`app.py`:** lê filtros do cabeçalho, chama `painel.py`, dispõe nas faixas da
  seção 3, renderiza cartões/gráficos/notas. Nenhuma conta.
- **`formato.py`:** `brl(x)` → "R$ 1.234,56"; `pct(x, casas=2)` → "44,19%";
  `milhao(x)` → "92,9 mi"; `inteiro(x)` → "15.297.535.452". **Sem `locale`** —
  separador por substituição de string (ponto milhar, vírgula decimal).
- **Cache:** cada `ler_*` com `@st.cache_data`; botão **"↻ Recarregar dados"**
  chama `st.cache_data.clear()`.
- **Erro:** no `app.py`, antes de desenhar, verificar banco e **os 11 marts**; se
  faltar → `st.error("Banco ou mart ausente: <nome>. Rode o pipeline.")` +
  `st.stop()`.
- **Tema:** `.streamlit/config.toml` com `base="dark"` e paleta (D37); sem CSS de
  marca/logo.
- **Como rodar:** `uv run streamlit run app.py`.
- **Relatório HTML (OPCIONAL — PENDENTE D39):** export estático do resumo+KPIs.
  **Marcado como opcional**, fora do caminho crítico; só se você aprovar.

---

## 11. Testes

**Unitários da tela (`tests/test_dashboard.py`) — dado inventado em `tmp_path`,
sem tocar no `snis.duckdb`:**
- `formato.py`: `brl`, `pct`, `milhao`, `inteiro` com casos fixos (sem
  `pytest.approx` em dinheiro — igualdade de string formatada).
- montagem: `painel.py` chamado contra um **DuckDB temporário** com schema `gold`
  mínimo (fixture) → cada `ler_*` devolve as colunas esperadas.
- regras 7a/7b/7g/7h/7j/7l: os `grep`/asserts da seção 7.
- **sem teste sem assert, sem `skip`/`xfail`, sem `pytest.approx` em R$.**
- **Meta de cobertura da aula:** `formato.py` e `painel.py` **100%** de linhas;
  `app.py` coberto pelo smoke test de montagem (meta ≥ a da aula 4).

**Separado — qualidade de dados da gold (`tests/test_gold.py`, banco real):** os
testes do mart 11 e C9/C10 (seções 5, 8, 9) usam o **dado real** e ficam **neste**
arquivo, não em `test_dashboard.py`.

**Só verificável manualmente na interface (roteiro):**
1. Contraste do tema escuro legível (7k) — abrir, conferir texto/fundo.
2. Mobile empilha em 1 coluna sem rolagem horizontal.
3. Botão "Recarregar dados" limpa o cache (mudar o banco e ver atualizar).
4. `st.stop()` dispara ao renomear/remover um mart.
5. Rótulos d/e/l presentes em cada gráfico; cor nunca é o único significado.

---

## 12. Critérios de aceite (checklist) e riscos

**Checklist:**
- [ ] `app.py` roda com `uv run streamlit run app.py` e trata banco/mart ausente.
- [ ] 4 cartões da Faixa A com valores da seção 5, travados por teste.
- [ ] Resumo executivo 100% por template (seção 6); zero número à mão.
- [ ] Nenhuma operação proibida em `painel.py`/`app.py` (7b, por `grep`).
- [ ] Marts urbanos só 2021 (7c); mart 10 rotulado água‑only (7l).
- [ ] Esgoto urbano nunca ao lado do IN056 sem aviso (7d).
- [ ] R$ nominal rotulado; atípicos visíveis (7e, 7f).
- [ ] Mart 6 nunca cruzado com mart 1 (7g).
- [ ] Todo gráfico com título/unidade/fonte/ano (7h); informantes exibidos (7i).
- [ ] Tema escuro com contraste; significado nunca só por cor (7k).
- [ ] C9 e C10 com teste verde e nota de rodapé (seção 8).
- [ ] `mart 11` especificado e, após aprovação, implementado+testado.
- [ ] `design/rascunho.png` aprovado antes do código de tela.

**Riscos e mitigação:**
| Risco | Mitigação |
|---|---|
| Alguém some colunas na tela p/ "fazer o nacional" | mart 11 pronto + teste `test_sem_operacoes_proibidas`. |
| Leitor compara urbano (mart 1) com total (mart 6) | regra 7g + nota fixa; gráficos separados. |
| Esgoto urbano lido como IN056 | rótulo "entre informantes" (7d) + cartões usam IN056. |
| R$ comparado entre anos | seletor financeiro de ano único + rótulo nominal (7e). |
| Absoluto "sem esgoto" lido como oficial ≈100 mi | nota de não reconciliação (D30) no rodapé. |
| Cor como único significado (dark) | rótulo textual sempre (7k). |
| Mart 11 divergir dos marts | C9/C10 e igualdades por teste (seções 5, 8). |

---

## 13. Conflitos com decisões registradas (D1–D33)

**Nenhum conflito que exija violar uma decisão.** Pontos de atenção resolvidos a
favor da decisão registrada:
- As referências visuais sugerem **mapa** e **menu multipágina**; **seguimos a
  gold**: sem mapa (não há geometria; não‑objetivo) e página única (público de 5 s).
- A aula sugere séries longas; **marts urbanos travados em 2021** (D2) e **sem R$
  inter‑anual** (D22) prevalecem sobre "mostrar a série inteira".
- Esgoto por renda (mart 10) **não existe** — D33 (água‑only) prevalece.

---

## 14. Decisões novas (APROVADAS em 2026-11-09 — registradas em decisoes.md)

- **D34** — criar `gold.kpis_brasil` (mart 11) para KPIs/resumo nacionais. **(a) criar.**
- **D35** — página única em faixas + aba "Detalhe". **(a).**
- **D36** — seletor de ano: urbano travado em 2021, não urbano com intervalo. **(a).**
- **D37** — tema escuro verde‑azulado via `config.toml`, sem marca. **(a).**
- **D38** — biblioteca de gráficos = **Altair**. **(a).**
- **D39** — relatório HTML estático **fora do escopo** da aula 4. **(a).**
