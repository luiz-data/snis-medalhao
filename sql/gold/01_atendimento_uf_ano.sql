-- Mart 1: gold.atendimento_uf_ano (spec-gold.md §2, ficha Mart 1)
-- Grão: uma linha por (ano, UF). PK (ano, sigla_uf).
-- Pergunta: qual % da população URBANA tem água e esgoto, por UF e ano?
-- Denominador (declarado): população urbana do SNIS
--   água   -> populacao_urbana
--   esgoto -> populacao_urbana_residente_esgoto
-- Índice = Σnum / nullif(Σden,0) × 100 (soma sobre soma; §1.2.1), NUNCA média de índice.
-- UF/região SEMPRE da DTB (§1.2.8), nunca do sigla_uf do SNIS.
-- D2: janela 2010–2021; 2022 excluído (colunas urbanas 100% nulas).
-- D5: linhas com atendida urbana > população urbana são EXCLUÍDAS do cálculo,
--     com flag e contagem por ano (sem clamp). Contadas por água, por esgoto e no total.
-- D20: só este SELECT; o executor compõe o CREATE TABLE.
WITH base AS (
  SELECT
    s.ano,
    d.sigla_uf,
    d.nome_uf,
    d.nome_regiao,
    s.populacao_urbana_atendida_agua    AS num_agua,
    s.populacao_urbana                  AS den_agua,
    s.populacao_urbana_atendida_esgoto  AS num_esgoto,
    s.populacao_urbana_residente_esgoto AS den_esgoto,
    -- flags D5 (violação A2): num e den não nulos e atendida > residente/urbana
    (s.populacao_urbana_atendida_agua IS NOT NULL
       AND s.populacao_urbana IS NOT NULL
       AND s.populacao_urbana_atendida_agua > s.populacao_urbana) AS a2_agua,
    (s.populacao_urbana_atendida_esgoto IS NOT NULL
       AND s.populacao_urbana_residente_esgoto IS NOT NULL
       AND s.populacao_urbana_atendida_esgoto > s.populacao_urbana_residente_esgoto) AS a2_esgoto
  FROM silver.municipio_agua_esgoto s
  JOIN silver.ibge_dtb_municipio d ON d.id_municipio = s.id_municipio
  WHERE s.ano BETWEEN 2010 AND 2021
)
SELECT
  ano,
  sigla_uf,
  nome_uf,
  nome_regiao,
  -- cobertura urbana de água (%), excluindo A2 (D5)
  100.0 * sum(num_agua) FILTER (WHERE num_agua IS NOT NULL AND den_agua IS NOT NULL AND NOT a2_agua)
    / nullif(sum(den_agua) FILTER (WHERE num_agua IS NOT NULL AND den_agua IS NOT NULL AND NOT a2_agua), 0)
    AS cobertura_urbana_agua,
  -- cobertura urbana de esgoto (%), excluindo A2 (D5)
  100.0 * sum(num_esgoto) FILTER (WHERE num_esgoto IS NOT NULL AND den_esgoto IS NOT NULL AND NOT a2_esgoto)
    / nullif(sum(den_esgoto) FILTER (WHERE num_esgoto IS NOT NULL AND den_esgoto IS NOT NULL AND NOT a2_esgoto), 0)
    AS cobertura_urbana_esgoto,
  -- informantes = num e den não nulos E não excluídos por A2 (entram no cálculo)
  count(*) FILTER (WHERE num_agua IS NOT NULL AND den_agua IS NOT NULL AND NOT a2_agua)
    AS municipios_informantes_agua,
  count(*) FILTER (WHERE num_esgoto IS NOT NULL AND den_esgoto IS NOT NULL AND NOT a2_esgoto)
    AS municipios_informantes_esgoto,
  -- exclusões D5 por água e por esgoto (fecham a identidade com os informantes)
  count(*) FILTER (WHERE a2_agua)   AS excluidas_a2_agua,
  count(*) FILTER (WHERE a2_esgoto) AS excluidas_a2_esgoto,
  -- total excluído por A2 em água OU esgoto (D5)
  count(*) FILTER (WHERE a2_agua OR a2_esgoto) AS linhas_excluidas_a2
FROM base
GROUP BY ano, sigla_uf, nome_uf, nome_regiao
