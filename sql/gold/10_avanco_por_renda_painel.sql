-- Mart 10: gold.avanco_por_renda_painel (spec-gold.md §2, ficha Mart 10; D33)
-- Grão: uma linha por (quartil_pib, ano), ano fixo em {2010, 2021}. PK (quartil_pib, ano) = 8 linhas.
-- Pergunta: o atendimento URBANO DE ÁGUA avançou mais entre 2010 e 2021 em
--   municípios de maior ou menor renda?
-- D33: ÁGUA-ONLY. O esgoto NÃO entra neste mart (limitação declarada na ficha):
--   um painel de esgoto exigiria informar esgoto nos 12 anos — recorte com viés
--   de seleção, não o Brasil — e fica como extensão futura, fora do escopo.
-- Painel (D19/D24): painel fixo único = municípios com as colunas-chave
--   (populacao_urbana_atendida_agua E populacao_urbana) não nulas nos 12
--   anos de 2010 a 2021 = 4.472. É o mesmo painel do mart 4. SEM exclusão A2 aqui
--   (a cobertura é agregada soma/soma; não há linha de município de onde excluir).
--   Sensibilidade registrada na ficha: painel menos as 41 violações A2 = 4.431,
--   cobertura 2021 = 93,40% (contra 93,52% com os 4.472).
-- D5/D32 (>100%): o truncamento do mart 1 (D5) exclui a violação A2 do AGREGADO;
--   aqui NÃO se aplica — seguimos o princípio D32 (preservar o valor, sem clamp):
--   a cobertura do quartil é soma/soma incluindo os municípios >100% (o excedente
--   entra no numerador). Não há coluna de sinalização porque o grão é agregado
--   (quartil, ano), não o município; os 26 casos >100% em 2010 e 16 em 2021 ficam
--   descritos na ficha (contagem), não como coluna.
-- Quartil (ficha): ntile(4) NACIONAL sobre pib_per_capita de BASE 2021, fixo para
--   os dois anos (um município não muda de quartil entre 2010 e 2021). ≈1.118 por
--   quartil (4×1.118 = 4.472).
-- D15 (conversão do PIB): pib_municipio está em MIL REAIS (BIGINT) na silver; a
--   conversão para reais é só aqui (× 1000). pib_per_capita = pib×1000 / pop IBGE.
-- D17 (PIB per capita negativo): sem clamp, sem filtro, sem log — cai naturalmente
--   no 1º quartil. Em base 2021 há 0 negativos (Guamaré/RN voltou a positivo);
--   a regra fica registrada.
-- Medida principal: variacao_pp (avanço em pontos percentuais 2021 − 2010).
--   reducao_relativa_deficit é coluna de APOIO (ficha): quanto do déficit de 2010
--   foi fechado até 2021, em %. As duas contam histórias opostas (Q1 avança mais
--   em pp; Q4 fecha mais déficit relativo) — por isso ambas ficam, sem causa.
-- variacao_pp e reducao_relativa_deficit são atributos do QUARTIL: repetem-se nas
--   duas linhas de ano do mesmo quartil (derivados de 2021 − 2010).
-- Sem relação monotônica no grão município: Spearman renda×avanço = 0,0075 (não
--   ponderado) e −0,0809 (ponderado por população). Registrado na ficha; sem causa.
-- UF/nome/região: não entram (grão é quartil nacional, não território).
-- D20: só este SELECT; o executor compõe o CREATE TABLE.
WITH painel AS (  -- D19: 4.472 municípios não nulos nas colunas-chave nos 12 anos
  SELECT id_municipio
  FROM silver.municipio_agua_esgoto
  WHERE ano BETWEEN 2010 AND 2021
    AND populacao_urbana_atendida_agua IS NOT NULL
    AND populacao_urbana IS NOT NULL
  GROUP BY id_municipio
  HAVING count(DISTINCT ano) = 12
),
per_capita AS (  -- PIB per capita nominal 2021 (R$), base única do quartil
  SELECT
    p.id_municipio,
    pib.pib_municipio * 1000.0 / nullif(po.populacao_total_ibge, 0) AS pib_per_capita
  FROM painel p
  JOIN silver.ibge_pib_municipio pib      ON pib.id_municipio = p.id_municipio AND pib.ano = 2021
  JOIN silver.ibge_populacao_municipio po ON po.id_municipio  = p.id_municipio AND po.ano  = 2021
),
quartis AS (  -- ntile(4) nacional sobre o painel; negativo (D17) cai no quartil 1
  SELECT id_municipio, ntile(4) OVER (ORDER BY pib_per_capita) AS quartil_pib
  FROM per_capita
),
anos AS (  -- valores de água urbana dos dois anos fixos, por município do painel
  SELECT
    s.id_municipio,
    max(CASE WHEN s.ano = 2010 THEN s.populacao_urbana_atendida_agua END) AS atendida_2010,
    max(CASE WHEN s.ano = 2010 THEN s.populacao_urbana END)               AS urbana_2010,
    max(CASE WHEN s.ano = 2021 THEN s.populacao_urbana_atendida_agua END) AS atendida_2021,
    max(CASE WHEN s.ano = 2021 THEN s.populacao_urbana END)               AS urbana_2021
  FROM silver.municipio_agua_esgoto s
  WHERE s.ano IN (2010, 2021)
  GROUP BY s.id_municipio
),
agregado AS (  -- soma/soma por quartil (universo comum; sem exclusão A2)
  SELECT
    q.quartil_pib,
    count(*)             AS municipios_painel,
    sum(a.atendida_2010) AS at10,
    sum(a.urbana_2010)   AS urb10,
    sum(a.atendida_2021) AS at21,
    sum(a.urbana_2021)   AS urb21
  FROM quartis q
  JOIN anos a ON a.id_municipio = q.id_municipio
  GROUP BY q.quartil_pib
),
derivado AS (  -- cobertura dos dois anos + medidas de avanço por quartil
  SELECT
    quartil_pib,
    municipios_painel,
    100.0 * at10 / nullif(urb10, 0) AS cobertura_2010,
    100.0 * at21 / nullif(urb21, 0) AS cobertura_2021,
    (100.0 * at21 / nullif(urb21, 0)) - (100.0 * at10 / nullif(urb10, 0)) AS variacao_pp,
    -- redução relativa do déficit (%): (déficit_2010 − déficit_2021) / déficit_2010 × 100
    100.0 * ((100.0 - 100.0 * at10 / nullif(urb10, 0)) - (100.0 - 100.0 * at21 / nullif(urb21, 0)))
      / nullif(100.0 - 100.0 * at10 / nullif(urb10, 0), 0) AS reducao_relativa_deficit
  FROM agregado
),
grade AS (SELECT unnest([2010, 2021]) AS ano)  -- expande cada quartil nos dois anos
SELECT
  d.quartil_pib,
  g.ano,
  CASE WHEN g.ano = 2010 THEN d.cobertura_2010 ELSE d.cobertura_2021 END AS cobertura_urbana_agua,
  d.municipios_painel,
  d.variacao_pp,
  d.reducao_relativa_deficit
FROM derivado d
CROSS JOIN grade g
ORDER BY d.quartil_pib, g.ano
