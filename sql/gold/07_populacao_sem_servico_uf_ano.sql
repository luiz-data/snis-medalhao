-- Mart 7: gold.populacao_sem_servico_uf_ano (spec-gold.md §2, ficha Mart 7)
-- Grão: uma linha por (sigla_uf, ano). PK (ano, sigla_uf). 27 UF × 12 anos = 324.
-- Pergunta: quantos habitantes, em números absolutos, estão sem água e sem
--   coleta de esgoto por rede, por UF?
--
-- Universo = silver.ibge_dtb_municipio; população de silver.ibge_populacao_municipio
--   (residente total, D14); atendidos de silver.municipio_agua_esgoto (SNIS).
--   Janela 2010–2021. 5.570 municípios têm pop na janela (o 5101837 Boa Esperança
--   do Norte/MT, D12, não tem linha de pop e fica fora; nenhuma pop nula).
--
-- D30 (esgoto pela IN056; revoga a convenção antiga da ficha):
--   * ÁGUA — "sem água" = déficit por município entre os INFORMANTES de água:
--       pop_sem_agua = Σ greatest(populacao_total_ibge − populacao_atendida_agua, 0)
--       sobre os municípios que informam água. Quem NÃO informa água não é "sem
--       água": entra em pop_sem_informacao_agua / municipios_sem_informacao_agua
--       (o tamanho do que não se sabe). O absoluto é um PISO (esses ficam fora).
--   * ESGOTO (IN056, lição do mart 6 / D29) — "sem esgoto" = déficit entre os
--       informantes de ÁGUA, tratando o branco de esgoto como "sem rede":
--       pop_sem_esgoto = Σ greatest(populacao_total_ibge − coalesce(populacao_atendida_esgoto,0), 0)
--       sobre os municípios que informam água (atendido de esgoto nulo = 0).
--       Em 2021, 2.531 de 2.532 brancos de esgoto têm as colunas físicas
--       (extensao_rede_esgoto, volume_esgoto_coletado, quantidade_ligacao_ativa_esgoto)
--       nulas/zero -> o branco é "sem sistema", não "informou zero". A convenção
--       anterior da ficha (só informantes de esgoto, 57,9 mi) é REVOGADA por não
--       conferir com o oficial; a IN056 dá 92,9 mi (= 100 − IN056 55,81%).
--   * "Sem esgoto" é SEM COLETA POR REDE: quem usa fossa séptica conta como "sem
--     esgoto" aqui — o rótulo é "sem coleta por rede", não "sem saneamento".
--
-- greatest(..., 0) por MUNICÍPIO: revisões de série podem dar atendido > pop
--   (2010–2021: água 63 grãos / 387.725 hab / 0,097%; esgoto 11 grãos / 90.404
--   hab) — imaterial, truncado em 0 na origem (pop_sem_* nunca negativo).
--
-- Percentuais: ambos sobre pop_informante_agua (Σ pop IBGE dos informantes de
--   água), coerente com IN055/IN056. Nacional 2021: água 15,8%, esgoto 44,19%.
-- D20: só este SELECT; o executor compõe o CREATE TABLE.
SELECT
  p.ano,
  d.sigla_uf,
  d.nome_uf,
  d.nome_regiao,
  -- população residente total IBGE da UF no ano (universo inteiro)
  sum(p.populacao_total_ibge)                                                       AS pop_total_ibge,
  -- denominador dos percentuais: pop. IBGE dos informantes de água
  sum(p.populacao_total_ibge) FILTER (WHERE s.populacao_atendida_agua IS NOT NULL)  AS pop_informante_agua,
  -- ÁGUA: déficit por município entre informantes de água (nunca negativo)
  sum(greatest(p.populacao_total_ibge - s.populacao_atendida_agua, 0))
      FILTER (WHERE s.populacao_atendida_agua IS NOT NULL)                          AS pop_sem_agua,
  -- piso: população em municípios SEM informação de água (ficam fora de pop_sem_agua)
  coalesce(sum(p.populacao_total_ibge) FILTER (WHERE s.populacao_atendida_agua IS NULL), 0)
                                                                                    AS pop_sem_informacao_agua,
  -- ESGOTO (IN056/D30): déficit entre informantes de ÁGUA, branco = sem rede (0)
  sum(greatest(p.populacao_total_ibge - coalesce(s.populacao_atendida_esgoto, 0), 0))
      FILTER (WHERE s.populacao_atendida_agua IS NOT NULL)                          AS pop_sem_esgoto,
  -- percentuais nacionais/por UF (denominador = pop_informante_agua)
  100.0 * sum(greatest(p.populacao_total_ibge - s.populacao_atendida_agua, 0))
          FILTER (WHERE s.populacao_atendida_agua IS NOT NULL)
        / nullif(sum(p.populacao_total_ibge) FILTER (WHERE s.populacao_atendida_agua IS NOT NULL), 0)
                                                                                    AS pct_sem_agua,
  100.0 * sum(greatest(p.populacao_total_ibge - coalesce(s.populacao_atendida_esgoto, 0), 0))
          FILTER (WHERE s.populacao_atendida_agua IS NOT NULL)
        / nullif(sum(p.populacao_total_ibge) FILTER (WHERE s.populacao_atendida_agua IS NOT NULL), 0)
                                                                                    AS pct_sem_esgoto,
  -- contagens: informantes de água, sem informação de água, informantes de esgoto
  count(*) FILTER (WHERE s.populacao_atendida_agua IS NOT NULL)                     AS municipios_informantes_agua,
  count(*) FILTER (WHERE s.populacao_atendida_agua IS NULL)                         AS municipios_sem_informacao_agua,
  count(*) FILTER (WHERE s.populacao_atendida_esgoto IS NOT NULL)                   AS municipios_informantes_esgoto
FROM silver.ibge_populacao_municipio p
JOIN silver.ibge_dtb_municipio d
  ON d.id_municipio = p.id_municipio
LEFT JOIN silver.municipio_agua_esgoto s
  ON s.id_municipio = p.id_municipio AND s.ano = p.ano
WHERE p.ano BETWEEN 2010 AND 2021
GROUP BY p.ano, d.sigla_uf, d.nome_uf, d.nome_regiao
