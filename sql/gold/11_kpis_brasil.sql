-- Mart 11 — gold.kpis_brasil (D34): KPIs NACIONAIS por ano para o dashboard.
-- Um SELECT só (D20); o executor compõe o CREATE TABLE.
--
-- Princípio (D34): não redefine indicador nenhum. Cada coluna reusa a fórmula
-- EXATA do mart de origem sobre a silver (soma-sobre-soma), reproduzindo o valor
-- nacional travado no teste do mart de origem. Alimenta os cartões e o resumo
-- executivo do painel SEM cálculo na tela (regra 7b de spec-dashboard.md).
--
-- Janela 2010-2021 (12 linhas). Os urbanos só valem aqui (D2/D36). A série longa
-- de coleta/tratamento (1995-2022) é lida direto do mart 2 no gráfico de série.
-- Valores monetarios NOMINAIS (regra 7e do dashboard; sem coluna de metadado).
-- PK: ano.
--
-- Origem por coluna:
--   cobertura_urbana_agua_br    -> mart 1 (D5: exclui A2 num>den)
--   cobertura_agua_in055_br     -> mart 6 (IN055, base pop total IBGE informantes de agua)
--   cobertura_esgoto_in056_br   -> mart 6 (IN056, denominador = informantes de AGUA, D29)
--   indice_coleta_esgoto_br     -> mart 2 (universo comum: consumido>0)
--   indice_tratamento_esgoto_br -> mart 2 (universo comum: coletado>0)
--   perdas_in049_br             -> mart 3 (D3; POR ANO: 2021 = 36,86%; 37,42% e o
--                                  agregado 2010-2021, nao um ano isolado)
--   consumo_per_capita_br       -> mart 3 (IN022/D25; pop_med = media atendida ano e ano-1)
--   pop_sem_agua_br / pct       -> mart 7 (greatest por municipio, informantes de agua)
--   pop_sem_esgoto_br / pct     -> mart 7 (IN056/D30; denominador = informantes de agua)
--   municipios_sem_info_agua_br -> mart 7 (municipios com pop IBGE e agua nula/ausente; piso)
--   investimento_total_br       -> mart 5 (soma sobre o conjunto inteiro; R$ nominal)
--   investimento_per_capita_br  -> mart 8 (D31: universo comum, entre quem declarou investimento)
WITH anos AS (
    SELECT generate_series AS ano FROM generate_series(2010, 2021)
),
snis AS (
    SELECT * FROM silver.municipio_agua_esgoto WHERE ano BETWEEN 2010 AND 2021
),
pop AS (
    SELECT id_municipio, ano, populacao_total_ibge
    FROM silver.ibge_populacao_municipio
),
atend AS (  -- atendida de agua de qualquer ano, para o lag do IN022 (D25)
    SELECT id_municipio, ano, populacao_atendida_agua
    FROM silver.municipio_agua_esgoto
),
m1 AS (  -- mart 1: agua urbana nacional (D5)
    SELECT ano,
        100.0 * sum(populacao_urbana_atendida_agua)
            FILTER (populacao_urbana_atendida_agua IS NOT NULL
                AND populacao_urbana IS NOT NULL
                AND populacao_urbana_atendida_agua <= populacao_urbana)
        / nullif(sum(populacao_urbana)
            FILTER (populacao_urbana_atendida_agua IS NOT NULL
                AND populacao_urbana IS NOT NULL
                AND populacao_urbana_atendida_agua <= populacao_urbana), 0)
            AS cobertura_urbana_agua_br
    FROM snis GROUP BY ano
),
m6 AS (  -- mart 6: IN055 (agua) e IN056 (esgoto), base pop total IBGE informantes de agua
    SELECT s.ano,
        100.0 * sum(s.populacao_atendida_agua)
            / nullif(sum(p.populacao_total_ibge)
                FILTER (s.populacao_atendida_agua IS NOT NULL), 0)
            AS cobertura_agua_in055_br,
        100.0 * sum(s.populacao_atendida_esgoto)
            FILTER (s.populacao_atendida_agua IS NOT NULL)
            / nullif(sum(p.populacao_total_ibge)
                FILTER (s.populacao_atendida_agua IS NOT NULL), 0)
            AS cobertura_esgoto_in056_br
    FROM snis s
    JOIN pop p ON p.id_municipio = s.id_municipio AND p.ano = s.ano
    WHERE p.populacao_total_ibge IS NOT NULL
    GROUP BY s.ano
),
m2 AS (  -- mart 2: coleta e tratamento (universo comum, den > 0)
    SELECT ano,
        100.0 * sum(volume_esgoto_coletado)
            FILTER (volume_esgoto_coletado IS NOT NULL
                AND volume_agua_consumido IS NOT NULL
                AND volume_agua_consumido > 0)
        / nullif(sum(volume_agua_consumido)
            FILTER (volume_esgoto_coletado IS NOT NULL
                AND volume_agua_consumido IS NOT NULL
                AND volume_agua_consumido > 0), 0)
            AS indice_coleta_esgoto_br,
        100.0 * sum(volume_esgoto_tratado)
            FILTER (volume_esgoto_tratado IS NOT NULL
                AND volume_esgoto_coletado IS NOT NULL
                AND volume_esgoto_coletado > 0)
        / nullif(sum(volume_esgoto_coletado)
            FILTER (volume_esgoto_tratado IS NOT NULL
                AND volume_esgoto_coletado IS NOT NULL
                AND volume_esgoto_coletado > 0), 0)
            AS indice_tratamento_esgoto_br
    FROM snis GROUP BY ano
),
m3p AS (  -- mart 3: perdas IN049 por ano (D3; exclui num<0 ou den<=0 = salvaguarda)
    SELECT ano,
        100.0 * sum(num) FILTER (num >= 0 AND den > 0)
        / nullif(sum(den) FILTER (num >= 0 AND den > 0), 0) AS perdas_in049_br
    FROM (
        SELECT ano,
            volume_agua_produzido + coalesce(volume_agua_tratada_importado, 0)
                - coalesce(volume_servico_agua, 0) AS den,
            volume_agua_produzido + coalesce(volume_agua_tratada_importado, 0)
                - volume_agua_consumido - coalesce(volume_servico_agua, 0) AS num
        FROM snis
        WHERE volume_agua_produzido IS NOT NULL AND volume_agua_consumido IS NOT NULL
    ) t
    GROUP BY ano
),
m3c AS (  -- mart 3: consumo per capita IN022 (D25; pop_med = media ano e ano-1)
    SELECT c.ano,
        sum(c.volume_agua_consumido - coalesce(c.volume_agua_tratada_exportado, 0))
            * 1000000.0
        / nullif(sum(((c.populacao_atendida_agua
            + coalesce(a.populacao_atendida_agua, c.populacao_atendida_agua)) / 2.0)
            * 365), 0) AS consumo_per_capita_br
    FROM snis c
    LEFT JOIN atend a ON a.id_municipio = c.id_municipio AND a.ano = c.ano - 1
    WHERE c.volume_agua_consumido IS NOT NULL
        AND c.populacao_atendida_agua IS NOT NULL
        AND c.populacao_atendida_agua > 0
    GROUP BY c.ano
),
m7 AS (  -- mart 7: sem agua / sem esgoto (D30); base = municipios com pop IBGE
    SELECT p.ano,
        sum(greatest(p.populacao_total_ibge - s.populacao_atendida_agua, 0))
            FILTER (s.populacao_atendida_agua IS NOT NULL) AS pop_sem_agua_br,
        sum(greatest(p.populacao_total_ibge
                - coalesce(s.populacao_atendida_esgoto, 0), 0))
            FILTER (s.populacao_atendida_agua IS NOT NULL) AS pop_sem_esgoto_br,
        sum(p.populacao_total_ibge)
            FILTER (s.populacao_atendida_agua IS NOT NULL) AS pop_informante_agua_br,
        count(*) FILTER (s.populacao_atendida_agua IS NULL)
            AS municipios_sem_info_agua_br
    FROM pop p
    LEFT JOIN snis s ON s.id_municipio = p.id_municipio AND s.ano = p.ano
    WHERE p.ano BETWEEN 2010 AND 2021 AND p.populacao_total_ibge IS NOT NULL
    GROUP BY p.ano
),
m5 AS (  -- mart 5: investimento total (soma do conjunto inteiro; R$ nominal)
    SELECT ano, sum(investimento_total_prestador) AS investimento_total_br
    FROM snis GROUP BY ano
),
m8 AS (  -- mart 8: investimento per capita (D31, universo comum)
    SELECT s.ano,
        sum(s.investimento_total_prestador)
            FILTER (s.investimento_total_prestador IS NOT NULL)
        / nullif(sum(p.populacao_total_ibge)
            FILTER (s.investimento_total_prestador IS NOT NULL), 0)
            AS investimento_per_capita_br
    FROM snis s
    JOIN pop p ON p.id_municipio = s.id_municipio AND p.ano = s.ano
    WHERE p.populacao_total_ibge IS NOT NULL
    GROUP BY s.ano
)
SELECT
    a.ano,
    m1.cobertura_urbana_agua_br,
    m6.cobertura_agua_in055_br,
    m6.cobertura_esgoto_in056_br,
    m2.indice_coleta_esgoto_br,
    m2.indice_tratamento_esgoto_br,
    m3p.perdas_in049_br,
    m3c.consumo_per_capita_br,
    m7.pop_sem_agua_br,
    m7.pop_sem_esgoto_br,
    100.0 * m7.pop_sem_agua_br / nullif(m7.pop_informante_agua_br, 0) AS pct_sem_agua_br,
    100.0 * m7.pop_sem_esgoto_br / nullif(m7.pop_informante_agua_br, 0) AS pct_sem_esgoto_br,
    m7.municipios_sem_info_agua_br,
    m5.investimento_total_br,
    m8.investimento_per_capita_br
FROM anos a
LEFT JOIN m1 ON m1.ano = a.ano
LEFT JOIN m6 ON m6.ano = a.ano
LEFT JOIN m2 ON m2.ano = a.ano
LEFT JOIN m3p ON m3p.ano = a.ano
LEFT JOIN m3c ON m3c.ano = a.ano
LEFT JOIN m7 ON m7.ano = a.ano
LEFT JOIN m5 ON m5.ano = a.ano
LEFT JOIN m8 ON m8.ano = a.ano
ORDER BY a.ano
