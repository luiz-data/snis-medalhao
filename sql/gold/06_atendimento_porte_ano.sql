-- Mart 6: gold.atendimento_porte_ano (spec-gold.md §2, ficha Mart 6)
-- Grão: uma linha por (faixa_porte, ano). PK (faixa_porte, ano). 6 faixas × 12 anos = 72.
-- Pergunta: como variam as coberturas de água e esgoto por faixa de porte?
--
-- D16: faixa de porte medida SÓ pela populacao_total_ibge de 2021, FIXA para todos
--   os anos. Universo = cadastro silver.ibge_dtb_municipio (5.571); município sem
--   pop. IBGE 2021 fica FORA das faixas (1 excluído: 5101837 Boa Esperança do
--   Norte/MT, D12) -> 5.570 nas faixas + 1 excluído = 5.571.
--
-- D29 (denominador da cobertura):
--   * ÁGUA — universo comum (denominador = pop. IBGE DOS INFORMANTES DE ÁGUA):
--       cobertura_agua = Σpopulacao_atendida_agua
--                        / Σpopulacao_total_ibge FILTER (informa água) × 100   -> IN055
--     Nacional 2021 = 84,20% (= IN055 oficial 84,2%).
--   * ESGOTO — convenção oficial IN056 (denominador = pop. IBGE DOS INFORMANTES
--     DE ÁGUA, NÃO de esgoto; o branco de esgoto = "sem sistema", viés de seleção):
--       cobertura_esgoto = Σpopulacao_atendida_esgoto
--                          / Σpopulacao_total_ibge FILTER (informa ÁGUA) × 100  -> IN056
--     Nacional 2021 = 55,81% (= IN056 oficial 55,8%). O denominador é pop_informante_agua.
--   * AUXILIAR — cobertura_esgoto_entre_informantes (universo comum do esgoto):
--       descreve SÓ quem informa esgoto; NÃO comparar faixas por ela.
--
-- Mart 6 usa população TOTAL (IBGE); mart 1 usa população URBANA (SNIS). Os
-- nacionais (84,2% aqui vs. 93,4% no mart 1, água) NÃO são comparáveis.
-- D20: só este SELECT; o executor compõe o CREATE TABLE.
WITH porte AS (  -- faixa fixada pela pop. IBGE de 2021 (D16); universo = DTB
  SELECT
    d.id_municipio,
    CASE
      WHEN p21.populacao_total_ibge IS NULL         THEN NULL  -- sem pop 2021 -> fora
      WHEN p21.populacao_total_ibge <   5000        THEN '1_ate_5mil'
      WHEN p21.populacao_total_ibge <  20000        THEN '2_5a20mil'
      WHEN p21.populacao_total_ibge <  50000        THEN '3_20a50mil'
      WHEN p21.populacao_total_ibge < 100000        THEN '4_50a100mil'
      WHEN p21.populacao_total_ibge < 500000        THEN '5_100a500mil'
      ELSE '6_acima500mil'
    END AS faixa_porte
  FROM silver.ibge_dtb_municipio d
  LEFT JOIN silver.ibge_populacao_municipio p21
    ON p21.id_municipio = d.id_municipio AND p21.ano = 2021
),
anos AS (SELECT range AS ano FROM range(2010, 2022)),  -- 2010–2021 (janela IBGE)
grade AS (  -- faixa (fixa) × ano; exclui os sem faixa (sem pop 2021)
  SELECT pt.id_municipio, pt.faixa_porte, a.ano
  FROM porte pt CROSS JOIN anos a
  WHERE pt.faixa_porte IS NOT NULL
),
base AS (  -- um registro por (município, ano) com pop. do ano e atendidos SNIS
  SELECT
    g.faixa_porte,
    g.ano,
    pop.populacao_total_ibge AS pop_ibge,
    s.populacao_atendida_agua   AS atendida_agua,
    s.populacao_atendida_esgoto AS atendida_esgoto
  FROM grade g
  LEFT JOIN silver.ibge_populacao_municipio pop
    ON pop.id_municipio = g.id_municipio AND pop.ano = g.ano
  LEFT JOIN silver.municipio_agua_esgoto s
    ON s.id_municipio = g.id_municipio AND s.ano = g.ano
)
SELECT
  faixa_porte,
  ano,
  -- população total IBGE da faixa inteira no ano, e nº de municípios (universo fixo)
  sum(pop_ibge)                                                  AS pop_total_ibge,
  count(*)                                                       AS municipios_faixa,
  -- denominadores (universo comum de cada família de informantes)
  sum(pop_ibge) FILTER (WHERE atendida_agua   IS NOT NULL)       AS pop_informante_agua,
  sum(pop_ibge) FILTER (WHERE atendida_esgoto IS NOT NULL)       AS pop_informante_esgoto,
  -- ÁGUA (IN055): num e den no universo dos informantes de água
  100.0 * sum(atendida_agua)
        / nullif(sum(pop_ibge) FILTER (WHERE atendida_agua IS NOT NULL), 0)
                                                                 AS cobertura_agua,
  -- ESGOTO (IN056): denominador = pop. dos informantes de ÁGUA (D29), NÃO de esgoto
  100.0 * sum(atendida_esgoto)
        / nullif(sum(pop_ibge) FILTER (WHERE atendida_agua IS NOT NULL), 0)
                                                                 AS cobertura_esgoto,
  -- AUXILIAR: universo comum do próprio esgoto (só descreve quem informa esgoto)
  100.0 * sum(atendida_esgoto)
        / nullif(sum(pop_ibge) FILTER (WHERE atendida_esgoto IS NOT NULL), 0)
                                                                 AS cobertura_esgoto_entre_informantes,
  -- informantes por família
  count(*) FILTER (WHERE atendida_agua   IS NOT NULL)            AS municipios_informantes_agua,
  count(*) FILTER (WHERE atendida_esgoto IS NOT NULL)            AS municipios_informantes_esgoto
FROM base
GROUP BY faixa_porte, ano
