-- Mart 3: gold.perdas_consumo_uf_ano (spec-gold.md §2, ficha Mart 3)
-- Grão: uma linha por (ano, UF). PK (ano, sigla_uf).
-- Pergunta: quanta água se perde na distribuição e quanto se consome por pessoa,
--           por UF e ano? UF/região SEMPRE da DTB (§1.2.8).
-- D3 (perdas = IN049 completo): (AG006+AG018-AG010-AG024)/(AG006+AG018-AG024)*100
--   AG006=volume_agua_produzido, AG018=volume_agua_tratada_importado,
--   AG010=volume_agua_consumido, AG024=volume_servico_agua.
--   AG018 e AG024 nulos contam como 0 (coalesce); exige AG006 e AG010 não nulos.
--   Soma sobre soma por UF e ano, NUNCA média de índice.
-- Salvaguarda D3 (exclusão com flag, 2 componentes): sai do cálculo a linha com
--   den = (AG006+AG018-AG024) <= 0  OU  AG010 > den. Contagens por componente.
-- D25 (consumo per capita = IN022): (AG010 - AG019) / média da pop. atendida do
--   ano e do ano anterior. AG019 = volume_agua_tratada_exportado (nulo = 0).
--   Unidade: volume em 1.000 m³/ano -> x 1.000.000 (L) / (pop_med x 365) = L/hab.dia.
--   pop_ant só vale quando é o ano EXATAMENTE anterior (lag(ano)=ano-1); senão
--   pop_med = pop (fallback). populacao_atendida_agua = total atendida (urbana+rural).
-- Diagnóstico D25: linhas_consumo_liquido_negativo (AG010-AG019 < 0), NÃO excluído.
-- D20: só este SELECT; o executor compõe o CREATE TABLE.
WITH base AS (
  SELECT
    s.ano,
    d.sigla_uf,
    d.nome_uf,
    d.nome_regiao,
    s.volume_agua_produzido                      AS ag006,
    coalesce(s.volume_agua_tratada_importado, 0) AS ag018,
    s.volume_agua_consumido                      AS ag010,
    coalesce(s.volume_servico_agua, 0)           AS ag024,
    coalesce(s.volume_agua_tratada_exportado, 0) AS ag019,
    s.populacao_atendida_agua                    AS pop,
    -- população atendida e ano da linha anterior do município (ordem por ano)
    lag(s.populacao_atendida_agua) OVER (PARTITION BY s.id_municipio ORDER BY s.ano) AS lag_pop,
    lag(s.ano)                     OVER (PARTITION BY s.id_municipio ORDER BY s.ano) AS lag_ano
  FROM silver.municipio_agua_esgoto s
  JOIN silver.ibge_dtb_municipio d ON d.id_municipio = s.id_municipio
),
m AS (
  SELECT
    *,
    (ag006 + ag018 - ag024) AS den,
    -- IN022: média do ano e do ano anterior EXATO; fallback pop_med = pop (D25)
    (pop + coalesce(CASE WHEN lag_ano = ano - 1 THEN lag_pop END, pop)) / 2.0 AS pop_med,
    (ag006 IS NOT NULL AND ag010 IS NOT NULL) AS tem_perdas,
    (ag006 IS NOT NULL AND ag010 IS NOT NULL
       AND ((ag006 + ag018 - ag024) <= 0 OR ag010 > (ag006 + ag018 - ag024))) AS inconsist,
    (ag010 IS NOT NULL AND pop IS NOT NULL AND pop > 0) AS tem_consumo
  FROM base
)
SELECT
  ano,
  sigla_uf,
  nome_uf,
  nome_regiao,
  -- perdas IN049 (%), soma sobre soma, sem as inconsistentes (D3)
  100.0 * sum(ag006 + ag018 - ag010 - ag024) FILTER (WHERE tem_perdas AND NOT inconsist)
    / nullif(sum(den) FILTER (WHERE tem_perdas AND NOT inconsist), 0)
    AS indice_perdas_in049,
  -- consumo per capita IN022 (L/hab.dia): volume em 1.000 m³ -> x 1.000.000 L / (pop_med x 365) (D25)
  sum((ag010 - ag019) * 1000000.0) FILTER (WHERE tem_consumo)
    / nullif(sum(pop_med * 365.0) FILTER (WHERE tem_consumo), 0)
    AS consumo_per_capita,
  -- informantes = entram no cálculo (não nulos e consistentes); fecha a identidade
  count(*) FILTER (WHERE tem_perdas AND NOT inconsist) AS municipios_informantes_perdas,
  count(*) FILTER (WHERE tem_consumo)                  AS municipios_informantes_consumo,
  -- salvaguarda D3: total e componentes (somam o total)
  count(*) FILTER (WHERE tem_perdas AND inconsist)                        AS linhas_inconsistentes_in049,
  count(*) FILTER (WHERE tem_perdas AND den <= 0)                         AS excluidas_den_nao_positivo,
  count(*) FILTER (WHERE tem_perdas AND den > 0 AND ag010 > den)          AS excluidas_consumo_acima,
  -- diagnóstico D25 (não excluído)
  count(*) FILTER (WHERE tem_consumo AND (ag010 - ag019) < 0)             AS linhas_consumo_liquido_negativo
FROM m
GROUP BY ano, sigla_uf, nome_uf, nome_regiao
