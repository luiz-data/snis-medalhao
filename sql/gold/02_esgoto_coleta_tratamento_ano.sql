-- Mart 2: gold.esgoto_coleta_tratamento_ano (spec-gold.md §2, ficha Mart 2)
-- Grão: uma linha por ano, agregado Brasil. PK (ano). 100% SNIS (D1, sem DTB/IBGE).
-- Pergunta: quanto do esgoto é coletado e tratado no Brasil, ano a ano?
-- Unidade: volumes em 1.000 m³/ano; razões volume/volume -> resultado em %.
-- Índices soma sobre soma (§1.2.1), universo comum: num e den não nulos E den > 0 (D23).
--   coleta     = Σvolume_esgoto_coletado / Σvolume_agua_consumido × 100 (coletado ÷ água consumida; NÃO IN046)
--   tratamento = Σvolume_esgoto_tratado  / Σvolume_esgoto_coletado × 100 (IN016; tratado ÷ coletado, NÃO sobre água)
-- D23: tratado > coletado NÃO é excluído (esgoto importado p/ tratamento; índice pode passar de 100),
--      só é contado em municipios_tratado_acima_coletado. Colunas excluidas_den_zero_* fecham a identidade
--      informantes + excluidas_den_zero = municípios com os dois volumes não nulos.
-- D24: painel de esgoto = regra D19 aplicada às colunas-chave de cada índice (um painel por família):
--      coleta 1.473 mun. / tratamento 1.440 mun., valor nos 12 anos de 2010 a 2021. Índices de painel
--      NULL fora de 2010–2021 (lêem a tendência sem efeito de composição; não o nível nacional).
-- serie_robusta: coleta passa de 1.000 informantes em 2006 (R3). Anos frágeis ficam na tabela, sem exclusão
--      (anomalias Fortaleza/1998 e Recife/1999 são erro de dado preservado, isolado por serie_robusta).
-- D20: só este SELECT; o executor compõe o CREATE TABLE.
WITH painel_coleta AS (                                 -- D19/D24: colunas-chave da COLETA
  SELECT id_municipio FROM silver.municipio_agua_esgoto
  WHERE ano BETWEEN 2010 AND 2021
    AND volume_esgoto_coletado IS NOT NULL
    AND volume_agua_consumido IS NOT NULL AND volume_agua_consumido > 0
  GROUP BY id_municipio HAVING count(DISTINCT ano) = 12  -- 1.473 municípios
),
painel_trat AS (                                        -- D19/D24: colunas-chave do TRATAMENTO
  SELECT id_municipio FROM silver.municipio_agua_esgoto
  WHERE ano BETWEEN 2010 AND 2021
    AND volume_esgoto_tratado IS NOT NULL
    AND volume_esgoto_coletado IS NOT NULL AND volume_esgoto_coletado > 0
  GROUP BY id_municipio HAVING count(DISTINCT ano) = 12  -- 1.440 municípios
),
base AS (
  SELECT
    s.ano,
    s.volume_esgoto_coletado AS coletado,
    s.volume_agua_consumido  AS consumido,
    s.volume_esgoto_tratado  AS tratado,
    (s.id_municipio IN (SELECT id_municipio FROM painel_coleta)) AS no_painel_coleta,
    (s.id_municipio IN (SELECT id_municipio FROM painel_trat))   AS no_painel_trat
  FROM silver.municipio_agua_esgoto s
)
SELECT
  ano,
  -- índices de todos os informantes (universo comum den > 0)
  100.0 * sum(coletado) FILTER (WHERE coletado IS NOT NULL AND consumido IS NOT NULL AND consumido > 0)
    / nullif(sum(consumido) FILTER (WHERE coletado IS NOT NULL AND consumido IS NOT NULL AND consumido > 0), 0)
    AS indice_coleta_esgoto,
  100.0 * sum(tratado) FILTER (WHERE tratado IS NOT NULL AND coletado IS NOT NULL AND coletado > 0)
    / nullif(sum(coletado) FILTER (WHERE tratado IS NOT NULL AND coletado IS NOT NULL AND coletado > 0), 0)
    AS indice_tratamento_esgoto,
  -- índices no painel de esgoto; fora de 2010–2021 o den filtrado é 0 -> nullif -> NULL
  100.0 * sum(coletado) FILTER (WHERE no_painel_coleta AND ano BETWEEN 2010 AND 2021 AND consumido > 0)
    / nullif(sum(consumido) FILTER (WHERE no_painel_coleta AND ano BETWEEN 2010 AND 2021 AND consumido > 0), 0)
    AS indice_coleta_painel,
  100.0 * sum(tratado) FILTER (WHERE no_painel_trat AND ano BETWEEN 2010 AND 2021 AND coletado > 0)
    / nullif(sum(coletado) FILTER (WHERE no_painel_trat AND ano BETWEEN 2010 AND 2021 AND coletado > 0), 0)
    AS indice_tratamento_painel,
  -- informantes = universo comum (num e den não nulos e den > 0)
  count(*) FILTER (WHERE coletado IS NOT NULL AND consumido IS NOT NULL AND consumido > 0)
    AS municipios_informantes_coleta,
  count(*) FILTER (WHERE tratado IS NOT NULL AND coletado IS NOT NULL AND coletado > 0)
    AS municipios_informantes_tratamento,
  -- contagem do painel por ano; NULL fora de 2010–2021 (constante 1.473 / 1.440 dentro)
  CASE WHEN ano BETWEEN 2010 AND 2021
    THEN count(*) FILTER (WHERE no_painel_coleta AND consumido > 0) END AS municipios_painel_coleta,
  CASE WHEN ano BETWEEN 2010 AND 2021
    THEN count(*) FILTER (WHERE no_painel_trat AND coletado > 0)   END AS municipios_painel_tratamento,
  -- denominador zero (fecham a identidade com os informantes)
  count(*) FILTER (WHERE coletado IS NOT NULL AND consumido IS NOT NULL AND consumido = 0)
    AS excluidas_den_zero_coleta,
  count(*) FILTER (WHERE tratado IS NOT NULL AND coletado IS NOT NULL AND coletado = 0)
    AS excluidas_den_zero_tratamento,
  -- diagnóstico: tratado > coletado (mantidos no índice, D23)
  count(*) FILTER (WHERE tratado IS NOT NULL AND coletado IS NOT NULL AND coletado > 0 AND tratado > coletado)
    AS municipios_tratado_acima_coletado,
  -- robustez: coleta passa de 1.000 informantes em 2006 (R3)
  (count(*) FILTER (WHERE coletado IS NOT NULL AND consumido IS NOT NULL AND consumido > 0) > 1000)
    AS serie_robusta
FROM base
GROUP BY ano
