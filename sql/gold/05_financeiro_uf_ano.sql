-- Mart 5: gold.financeiro_uf_ano (spec-gold.md §2, ficha Mart 5)
-- Grão: uma linha por (ano, UF). PK (ano, sigla_uf).
-- Pergunta: quanto se investe e se gasta por UF e ano, em R$ NOMINAIS?
--           (comparar só no mesmo ano; deflacionar está fora do escopo.)
--           UF/nome/região SEMPRE da DTB (§1.2.8).
-- D22/D27 (tarifa média e despesa unitária, soma sobre soma, R$/m³):
--   tarifa_media     = Σreceita_operacional_direta (FN001) / (Σvol_fat × 1000)   -> IN004
--   despesa_unitaria = Σdespesa_total_servico       (FN017) / (Σvol_fat × 1000)  -> IN003
--   vol_fat = volume_agua_faturado (AG011) + volume_esgoto_faturado (ES007), em 1.000 m³/ano,
--   então R$/m³ divide por 1.000 (× 1000 no denominador), NUNCA multiplica.
--   D27: FN017 = DTS = `despesa_total_servico` (NÃO `despesa_exploracao`, que é FN015/DEX/IN026);
--   DTS ⊇ DEX. `despesa_exploracao_dex` fica como coluna de DEX em R$ (sem indicador por m³).
--   Universo comum (D22): numerador e denominador não nulos e denominador > 0.
-- D28/D4 (investimento atípico): flag `investimento_atipico` quando investimento per
--   capita > R$ 1.000/hab (limiar NOMINAL, sem ajuste por inflação). Exige população
--   IBGE (janela 2010-2021); fora da janela ou sem pop IBGE a flag NÃO é avaliada
--   (o município fica nos dois totais). Os atípicos PERMANECEM em investimento_total
--   (o dinheiro foi gasto) e SAEM de investimento_total_sem_atipicos. Mesma regra e
--   mesmo nome reusados no mart 8. Hipótese de prestador regional é só hipótese
--   (a silver não tem coluna de prestador).
-- D20: só este SELECT; o executor compõe o CREATE TABLE.
WITH base AS (
  SELECT
    s.ano, d.sigla_uf, d.nome_uf, d.nome_regiao,
    s.investimento_total_prestador AS inv,
    s.despesa_total_servico        AS dts,    -- FN017 (DTS) -> IN003
    s.despesa_exploracao           AS dex,    -- FN015 (DEX)
    s.receita_operacional_direta   AS fn001,  -- FN001
    coalesce(s.volume_agua_faturado, 0) + coalesce(s.volume_esgoto_faturado, 0) AS vol_fat,
    p.populacao_total_ibge AS pop
  FROM silver.municipio_agua_esgoto s
  JOIN silver.ibge_dtb_municipio d ON d.id_municipio = s.id_municipio
  LEFT JOIN silver.ibge_populacao_municipio p
    ON p.id_municipio = s.id_municipio AND p.ano = s.ano
),
m AS (
  SELECT
    *,
    (fn001 IS NOT NULL AND vol_fat > 0)                 AS tem_tarifa,
    (dts   IS NOT NULL AND vol_fat > 0)                 AS tem_despesa,
    (dts   IS NOT NULL AND fn001  IS NOT NULL)          AS tem_indice,
    -- D28/D4: investimento per capita acima de R$ 1.000/hab (nominal), na janela
    (inv IS NOT NULL AND pop IS NOT NULL AND pop > 0
       AND ano BETWEEN 2010 AND 2021 AND inv / pop > 1000.0) AS investimento_atipico
  FROM base
)
SELECT
  ano, sigla_uf, nome_uf, nome_regiao,
  -- valores NOMINAIS em R$/ano (só comparar no mesmo ano)
  sum(inv)                                        AS investimento_total,
  sum(inv) FILTER (WHERE NOT investimento_atipico) AS investimento_total_sem_atipicos,
  sum(dts)                                        AS despesa_total_servicos,
  sum(dex)                                        AS despesa_exploracao_dex,
  sum(fn001)                                      AS receita_operacional_direta,
  -- despesa total ÷ receita × 100 (fração da receita consumida pela despesa), mesmo universo
  100.0 * sum(dts) FILTER (WHERE tem_indice)
    / nullif(sum(fn001) FILTER (WHERE tem_indice), 0)                      AS indice_despesa_sobre_receita,
  -- R$/m³: volume em 1.000 m³/ano -> ÷ 1.000 (× 1000 no denominador)
  sum(fn001) FILTER (WHERE tem_tarifa)
    / (nullif(sum(vol_fat) FILTER (WHERE tem_tarifa), 0) * 1000.0)         AS tarifa_media,
  sum(dts) FILTER (WHERE tem_despesa)
    / (nullif(sum(vol_fat) FILTER (WHERE tem_despesa), 0) * 1000.0)        AS despesa_unitaria,
  -- informantes por índice (universo comum: num e den não nulos e den > 0)
  count(*) FILTER (WHERE inv IS NOT NULL)          AS municipios_informantes_investimento,
  count(*) FILTER (WHERE tem_tarifa)               AS municipios_informantes_tarifa,
  count(*) FILTER (WHERE tem_despesa)              AS municipios_informantes_despesa,
  count(*) FILTER (WHERE investimento_atipico)     AS municipios_investimento_atipico
FROM m
GROUP BY ano, sigla_uf, nome_uf, nome_regiao
