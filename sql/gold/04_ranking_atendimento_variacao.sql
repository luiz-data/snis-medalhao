-- Mart 4: gold.ranking_atendimento_variacao (spec-gold.md §2, ficha Mart 4)
-- Grão: uma linha por MUNICÍPIO do painel fixo. PK (id_municipio).
-- Pergunta: quais municípios mais melhoraram/pioraram no atendimento urbano de
--   água entre dois anos fixos?
-- Anos fixos (D19/D2): ano_inicio = 2010, ano_fim = 2021 (nunca 2022).
-- Indicador: só ÁGUA urbana. Denominador: população urbana SNIS (D14).
--   cobertura = populacao_urbana_atendida_agua / nullif(populacao_urbana,0) × 100.
-- variacao_pp = cobertura_2021 − cobertura_2010 (pontos percentuais).
-- Painel (D19/D24): painel fixo único = municípios com as colunas-chave
--   (populacao_urbana_atendida_agua E populacao_urbana) não nulas em TODOS os 12
--   anos de 2010 a 2021 = 4.472. As colunas-chave do mart são as do painel urbano
--   de água, logo o painel de 4.472 satisfaz a D24 para este mart. Painel aplicado
--   ANTES do ranking (CTE painel → filtro A2 → window): município fora do painel
--   nunca vira linha e não altera posição.
-- D5: município com violação A2 (atendida urbana > população urbana) em 2010 OU
--   2021 sai do ranking (sem clamp). 41 excluídos; identidade 4.472 = 4.431 + 41.
-- D21: sem quintil_variacao; só posicao e variacao_pp.
-- D26 (empates): posicao = row_number() ORDER BY variacao_pp DESC,
--   populacao_urbana_fim DESC, id_municipio ASC → 1..N única, sem buracos
--   (satisfaz o aceite). posicao_empate = rank() ORDER BY variacao_pp DESC →
--   empates compartilham a posição. Desempate por população urbana de 2021 evita
--   ordem arbitrária nos extremos (há municípios empatados em +100 pp).
-- variacao_extrema: |variacao_pp| > 80 pp (12 casos) — possivelmente erro de dado
--   ou mudança de prestador/cobertura; preservados SEM correção.
-- D20: só este SELECT; o executor compõe o CREATE TABLE.
WITH painel AS (  -- D19: 4.472 municípios não nulos nos 12 anos
  SELECT id_municipio
  FROM silver.municipio_agua_esgoto
  WHERE ano BETWEEN 2010 AND 2021
    AND populacao_urbana_atendida_agua IS NOT NULL
    AND populacao_urbana IS NOT NULL
  GROUP BY id_municipio
  HAVING count(DISTINCT ano) = 12
),
vals AS (  -- valores dos dois anos fixos + flags A2 (D5)
  SELECT
    s.id_municipio,
    max(CASE WHEN s.ano = 2010 THEN s.populacao_urbana_atendida_agua END) AS at10,
    max(CASE WHEN s.ano = 2010 THEN s.populacao_urbana END)               AS urb10,
    max(CASE WHEN s.ano = 2021 THEN s.populacao_urbana_atendida_agua END) AS at21,
    max(CASE WHEN s.ano = 2021 THEN s.populacao_urbana END)               AS urb21,
    bool_or(s.ano = 2010 AND s.populacao_urbana_atendida_agua > s.populacao_urbana) AS a2_inicio,
    bool_or(s.ano = 2021 AND s.populacao_urbana_atendida_agua > s.populacao_urbana) AS a2_fim
  FROM silver.municipio_agua_esgoto s
  JOIN painel p ON p.id_municipio = s.id_municipio
  WHERE s.ano IN (2010, 2021)
  GROUP BY s.id_municipio
),
base AS (  -- painel menos exclusões A2 (D5); cobertura por município (não ponderar)
  SELECT
    v.id_municipio,
    d.sigla_uf,
    d.nome_uf,
    d.nome_regiao,
    100.0 * v.at10 / nullif(v.urb10, 0) AS cobertura_2010,
    100.0 * v.at21 / nullif(v.urb21, 0) AS cobertura_2021,
    100.0 * v.at21 / nullif(v.urb21, 0) - 100.0 * v.at10 / nullif(v.urb10, 0) AS variacao_pp,
    v.urb21 AS populacao_urbana_fim
  FROM vals v
  JOIN silver.ibge_dtb_municipio d ON d.id_municipio = v.id_municipio
  WHERE NOT (v.a2_inicio OR v.a2_fim)
)
SELECT
  id_municipio,
  sigla_uf,
  nome_uf,
  nome_regiao,
  cobertura_2010,
  cobertura_2021,
  variacao_pp,
  -- D26: ranking 1..N único, sem buracos; posição 1 = maior melhoria.
  row_number() OVER (
    ORDER BY variacao_pp DESC, populacao_urbana_fim DESC, id_municipio ASC
  ) AS posicao,
  -- D26: empates compartilham a posição (com buracos).
  rank() OVER (ORDER BY variacao_pp DESC) AS posicao_empate,
  -- diagnóstico: variação improvável (>80 pp), preservada sem correção.
  abs(variacao_pp) > 80 AS variacao_extrema
FROM base
