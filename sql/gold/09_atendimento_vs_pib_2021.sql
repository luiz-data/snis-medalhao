-- Mart 9: gold.atendimento_vs_pib_2021 (spec-gold.md §2, ficha Mart 9)
-- Grão: uma linha por MUNICÍPIO, ano fixo = 2021. PK (id_municipio).
-- Pergunta: como a cobertura URBANA de água/esgoto, as perdas e o investimento
--           se relacionam com o PIB per capita do município em 2021?
-- UF/nome/região SEMPRE da DTB (§1.2.8), nunca do sigla_uf do SNIS.
-- Universo (declarado, aceite da ficha): SNIS com água urbana informada em 2021
--   (populacao_urbana > 0 E populacao_urbana_atendida_agua não nula) casado com
--   PIB 2021 e população IBGE 2021 = 5.302 municípios (JOINs internos; cada
--   informante de água urbana tem PIB e pop IBGE). Os 268 municípios com pop+PIB
--   mas sem água urbana informada ficam de fora (3.304.102 hab; ver ficha).
-- Denominadores (declarados): água -> populacao_urbana; esgoto -> populacao_urbana_residente_esgoto.
-- D2: ano de referência 2021 (único com urbano válido + PIB).
-- D15 (conversão do PIB): pib_municipio está em MIL REAIS (BIGINT) na silver;
--   a conversão para reais acontece SÓ AQUI: × 1000 = reais. Sanidade: SP (3550308)
--   2021 pib_municipio = 828.980.747 Mil Reais ≈ R$ 828,98 bi.
-- D17 (PIB per capita negativo): permanece no dado, sem clamp, sem filtro, sem log.
--   Em 2021 há 0 negativos (Guamaré/RN voltou a positivo); a regra fica registrada.
-- D28/D4 (investimento atípico): MESMO predicado do mart 5/8 — investimento per
--   capita > R$ 1.000/hab (limiar NOMINAL). Mantido VISÍVEL (sem clamp, sem exclusão,
--   sem flag nova de PIB): só a flag investimento_atipico herdada.
-- D32 (cobertura > 100%): mantém o valor ORIGINAL do município (sem clamp) e
--   sinaliza em coluna booleana. Difere da D5 do mart 1 (que EXCLUI do agregado)
--   porque aqui o grão é o município (não há soma de onde excluir). 2021: 18 água, 7 esgoto.
-- Esgoto "entre informantes": cobertura_urbana_esgoto é NULL para quem não informa
--   (não zero); informou_esgoto marca os 2.771 informantes de esgoto urbano.
-- D20: só este SELECT; o executor compõe o CREATE TABLE.
WITH base AS (
  SELECT
    s.id_municipio,
    d.sigla_uf,
    d.nome_uf,
    d.nome_regiao,
    s.populacao_urbana_atendida_agua    AS num_agua,
    s.populacao_urbana                  AS den_agua,
    s.populacao_urbana_atendida_esgoto  AS num_esgoto,
    s.populacao_urbana_residente_esgoto AS den_esgoto,
    s.indice_perda_distribuicao_agua    AS perdas_in049,   -- IN049 do município
    s.investimento_total_prestador      AS inv,
    po.populacao_total_ibge             AS pop,
    pib.pib_municipio                   AS pib_mil_reais
  FROM silver.municipio_agua_esgoto s
  JOIN silver.ibge_dtb_municipio d        ON d.id_municipio   = s.id_municipio
  JOIN silver.ibge_populacao_municipio po ON po.id_municipio  = s.id_municipio AND po.ano  = 2021
  JOIN silver.ibge_pib_municipio pib      ON pib.id_municipio = s.id_municipio AND pib.ano = 2021
  WHERE s.ano = 2021
    AND s.populacao_urbana > 0
    AND s.populacao_urbana_atendida_agua IS NOT NULL
)
SELECT
  id_municipio,
  sigla_uf,
  nome_uf,
  nome_regiao,
  -- cobertura urbana de água (%), valor ORIGINAL (D32: sem clamp)
  100.0 * num_agua / nullif(den_agua, 0) AS cobertura_urbana_agua,
  -- cobertura urbana de esgoto (%), valor ORIGINAL; NULL para quem não informa esgoto
  CASE WHEN num_esgoto IS NOT NULL AND den_esgoto IS NOT NULL
       THEN 100.0 * num_esgoto / nullif(den_esgoto, 0) END AS cobertura_urbana_esgoto,
  -- informou água e esgoto urbanos (esgoto nulo = não informou, não zero)
  (num_esgoto IS NOT NULL AND den_esgoto IS NOT NULL) AS informou_esgoto,
  -- D32: sinalização de cobertura > 100% (valor preservado acima)
  (num_agua   IS NOT NULL AND den_agua   IS NOT NULL AND num_agua   > den_agua)   AS cobertura_urbana_agua_acima_100,
  (num_esgoto IS NOT NULL AND den_esgoto IS NOT NULL AND num_esgoto > den_esgoto) AS cobertura_urbana_esgoto_acima_100,
  -- perdas na distribuição (IN049, %), do município
  perdas_in049,
  -- investimento per capita (R$/hab, NOMINAL 2021) sobre a população IBGE
  inv / nullif(pop, 0) AS investimento_per_capita,
  -- D15: PIB em Mil Reais; × 1000 = reais. PIB per capita em R$/hab NOMINAL 2021.
  pib_mil_reais * 1000.0 / nullif(pop, 0) AS pib_per_capita,
  -- D28/D4: mesmo predicado do mart 5/8 (investimento per capita > R$ 1.000/hab, nominal)
  (inv IS NOT NULL AND pop IS NOT NULL AND pop > 0 AND inv / pop > 1000.0) AS investimento_atipico
FROM base
