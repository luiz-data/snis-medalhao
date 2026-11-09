-- Mart 8: gold.investimento_per_capita_uf_ano (spec-gold.md §2, ficha Mart 8)
-- Grão: uma linha por (ano, sigla_uf), janela 2010–2021. PK (ano, sigla_uf).
-- Pergunta: quanto se investe por habitante, por UF e ano, em R$ NOMINAIS?
--           (R$/hab por ano; não comparar entre anos sem correção.)
--           UF/nome/região SEMPRE da DTB; população = IBGE-POP (residente total).
--
-- D31 (denominador = universo comum): o per capita é "entre os municípios que
--   DECLARARAM investimento" — num e den só nos municípios com investimento
--   não nulo e população IBGE não nula (`tem_percapita`). O branco de
--   investimento é majoritariamente de município que informou o SNIS
--   (tem despesa/receita) e deixou o investimento em branco; os não
--   informantes de investimento NÃO entram no denominador (senão o per capita
--   afundaria por população que ninguém reportou). Sensibilidade 2021:
--   R$ 75,82/hab (universo comum) contra R$ 71,71/hab se cada nulo fosse zero
--   (−5,4%) — registrada na ficha, não vira coluna.
--
-- D4/D28 (investimento atípico): MESMA regra e MESMO nome do mart 5, predicado
--   replicado VERBATIM de sql/gold/05_financeiro_uf_ano.sql — flag quando o
--   investimento per capita do município > R$ 1.000/hab (limiar NOMINAL, sem
--   ajuste por inflação; exige pop IBGE na janela 2010–2021). Os atípicos
--   PERMANECEM nas colunas `…_com_atipicos`/`investimento_total` (o dinheiro foi
--   gasto) e SAEM das colunas `…_sem_atipicos`. A igualdade com o mart 5
--   (Σinv, municipios_investimento_atipico, investimento_total_sem_atipicos por
--   ano e UF) é travada por pytest local — é consistência interna (mesma silver),
--   protege contra deriva da regra, não é validação externa. Hipótese de
--   prestador regional é hipótese, não fato (a silver não tem coluna de prestador).
--   Nota de UF: RN é a mais afetada (−29% do total de RN 2010–2021 se os atípicos
--   saíssem; pico 2019 = 48 atípicos, 45 em RN); cita MA/SE/PE.
-- D20: só este SELECT; o executor compõe o CREATE TABLE.
WITH base AS (
  SELECT s.ano, d.sigla_uf, d.nome_uf, d.nome_regiao,
    s.investimento_total_prestador AS inv,
    p.populacao_total_ibge AS pop
  FROM silver.municipio_agua_esgoto s
  JOIN silver.ibge_dtb_municipio d ON d.id_municipio = s.id_municipio
  LEFT JOIN silver.ibge_populacao_municipio p
    ON p.id_municipio = s.id_municipio AND p.ano = s.ano
  WHERE s.ano BETWEEN 2010 AND 2021
),
m AS (
  SELECT
    *,
    -- universo comum (D31): investimento e população IBGE não nulos, pop > 0
    (inv IS NOT NULL AND pop IS NOT NULL AND pop > 0)             AS tem_percapita,
    -- D4/D28: predicado idêntico ao do mart 5 (R$ 1.000/hab nominal, na janela)
    (inv IS NOT NULL AND pop IS NOT NULL AND pop > 0
       AND ano BETWEEN 2010 AND 2021 AND inv / pop > 1000.0)      AS investimento_atipico
  FROM base
)
SELECT
  ano, sigla_uf, nome_uf, nome_regiao,
  -- per capita = Σinvestimento ÷ Σpop IBGE (soma sobre soma), universo comum
  sum(inv) FILTER (WHERE tem_percapita)
    / nullif(sum(pop) FILTER (WHERE tem_percapita), 0)            AS investimento_per_capita_com_atipicos,
  -- idem, excluindo os municípios com flag investimento_atipico (mesmo universo)
  sum(inv) FILTER (WHERE tem_percapita AND NOT investimento_atipico)
    / nullif(sum(pop) FILTER (WHERE tem_percapita AND NOT investimento_atipico), 0)
                                                                  AS investimento_per_capita_sem_atipicos,
  -- transparência: totais nominais (numeradores) e população do denominador
  sum(inv) FILTER (WHERE tem_percapita)                          AS investimento_total,
  sum(inv) FILTER (WHERE tem_percapita AND NOT investimento_atipico)
                                                                  AS investimento_total_sem_atipicos,
  sum(pop) FILTER (WHERE tem_percapita)                          AS pop_informante_investimento,
  -- contagens (universo comum e atípicos)
  count(*) FILTER (WHERE tem_percapita)                          AS municipios_informantes,
  count(*) FILTER (WHERE investimento_atipico)                   AS municipios_investimento_atipico,
  true                                                           AS valor_nominal
FROM m
GROUP BY ano, sigla_uf, nome_uf, nome_regiao
