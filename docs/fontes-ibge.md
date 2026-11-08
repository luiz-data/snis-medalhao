# Catálogo de fontes externas — IBGE

Este catálogo é **obrigatório**: nada vindo do IBGE entra no projeto sem uma
linha aqui. Nenhuma tabela, seed, mart ou ficha de indicador pode citar uma
fonte do IBGE que não esteja descrita neste arquivo. Toda ingestão nova começa
pela entrada correspondente abaixo (ou pela criação dela).

---

## IBGE-POP — População residente municipal

- **ID interno:** IBGE-POP
- **Nome:** População residente municipal
- **Definição (D14):** a coluna `populacao` é a **estimativa da população
  residente total** do município — **urbana e rural** —, com **data de
  referência em 1º de julho** (estimativas SIDRA 6579). É o denominador dos
  marts 6–8. **NÃO** é a população urbana do SNIS (`populacao_urbana`): são
  medidas distintas (universo total vs. subconjunto urbano autodeclarado), não
  comparáveis diretamente.
- **Origem:** Base dos Dados (console do BigQuery)
- **Tabela/identificador:** `br_ibge_populacao.municipio`
- **URL:** https://basedosdados.org/dataset/br-ibge-populacao
- **Data de acesso:** 2026-11-08
- **Versão/publicação:** municípios atualizados pelo Censo 2022; série montada
  a partir de estimativas (SIDRA 6579, 2001–2021, referência 1º de julho) e
  Censos/Contagem (SIDRA 202, 793, 9514)
- **Cobertura temporal:** 1991–2025 (191.099 linhas; 5.570 municípios/ano em
  2012–2025, 5.565 em 2010–2011)
- **Chave de junção:** `id_municipio` (7 dígitos, texto)
- **Uso no projeto (marts):** `atendimento_porte_ano`,
  `populacao_sem_servico_uf_ano`, `investimento_per_capita_uf_ano`,
  `atendimento_vs_pib_2021`, `avanco_por_renda_painel`
- **Limitações conhecidas:** série montada a partir de várias pesquisas; valores
  de anos antigos podem ser revisados entre publicações. Há **534 populações
  nulas** (533 em 1996, 1 em 2009; nenhuma em 2010–2021) e **1 linha sem
  `id_municipio`** (ano 2025, pop. 5.877), excluída da silver (D13).
- **Ressalva — quebra de série 2021 → 2022 (Censo 2022):** a estimativa de 2021
  (ex.: São Paulo 12.396.372) é substituída pelo **Censo 2022** (São Paulo
  11.451.999, repetido em 2023). É mudança de método, **não** erro. A janela
  analítica do projeto (**2010–2021**) usa só valores pré-Censo 2022 e **não é
  afetada** (D13).

---

## IBGE-DTB — Divisão Territorial Brasileira

- **ID interno:** IBGE-DTB
- **Nome:** Divisão Territorial Brasileira (municípios, UF e região)
- **Origem:** DTB (IBGE) — arquivo oficial `DTB_2025.zip`
- **Tabela/identificador:** relatório de municípios DTB 2025
  (`RELATORIO_DTB_BRASIL_2025_MUNICIPIOS.xls`, aba `DTB_Municípios`)
- **URL:** https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial/2025/DTB_2025.zip
  (página oficial `.../23701-divisao-territorial-brasileira.html` deu HTTP 403 na
  coleta automatizada; download pelo servidor geoftp)
- **Data de acesso:** 2026-11-08
- **Versão/publicação:** **DTB 2025** (DATA BASE 31/12/2025)
- **Cobertura temporal:** fotografia territorial 2025 — **5.571 municípios**
  (5.570 instalados + `5101837` Boa Esperança do Norte/MT, criado e ainda sem
  população estimada; D12)
- **Chave de junção:** `id_municipio` (7 dígitos; 2 primeiros = código da UF).
  A sigla da UF e a macrorregião **não existem no arquivo** e são derivadas do
  código da UF por mapa estático na silver (spec-ibge.md §5.3)
- **Uso no projeto (marts):** dimensão territorial que **substitui a seed de
  UF**; origem de UF e região para todos os marts por UF
  (`atendimento_uf_ano`, `perdas_consumo_uf_ano`, `financeiro_uf_ano`,
  `populacao_sem_servico_uf_ano`, `investimento_per_capita_uf_ano`)
- **Limitações conhecidas:** a lista muda com a criação/fusão de municípios;
  registrar a versão (ano) usada para garantir reprodutibilidade das junções.

---

## IBGE-PIB — PIB dos Municípios

- **ID interno:** IBGE-PIB
- **Nome:** Produto Interno Bruto dos Municípios
- **Origem:** **SIDRA — API `apisidra`** (D11). **A Base dos Dados
  (`br_ibge_pib.municipio`) é alternativa não usada** (tabela não confirmada).
- **Tabela/identificador:** **SIDRA 5938**, variável **37** ("Produto Interno
  Bruto a preços correntes"), unidade **Mil Reais** (código 40), nível `n6`
- **URL (valores):** `https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/<ANO>`
  · **metadados:** `https://servicodados.ibge.gov.br/api/v3/agregados/5938/metadados`
- **Data de acesso:** 2026-11-08
- **Versão/publicação:** tabela 5938 (Referência 2010); baixada **ano a ano**
- **Unidade:** **Mil Reais** (valor inteiro nominal; D9/D11). Tipagem na silver:
  **`BIGINT` em Mil Reais** (D15), sem `DECIMAL`; conversão para reais só na gold.
- **Cobertura temporal:** **2010–2021** (12 anos, = janela do projeto); 66.840
  linhas (5.570 municípios × 12 anos)
- **Chave de junção:** `id_municipio` (7 dígitos, texto; campo `D1C` do SIDRA)
- **Uso no projeto (marts):** `atendimento_vs_pib_2021`, `avanco_por_renda_painel`
- **Limitações conhecidas:** **valores nominais em Mil Reais** (só comparar
  dentro do mesmo ano, sem correção). O SIDRA usa símbolos de ausência
  {`-`,`..`,`...`,`X`}; nesta extração só `...` aparece (15 células, 2010–2012,
  5 municípios novos), tratado como NULL na silver (D11). **O PIB pode ser
  negativo** (impostos sobre produtos líquidos de subsídios negativos): 1 caso
  medido — **Guamaré/RN, 2012, −19.046 Mil Reais** —, preservado na silver com
  alerta IA9 (D17). Sem publicação regular em 2024 por mudança de ano-base das
  Contas Nacionais.

---

## Convenções

- **Nomes de tabela — prefixo `ibge_`:**
  - `bronze.ibge_populacao_municipio` → `silver.ibge_populacao_municipio`
  - `bronze.ibge_pib_municipio` → `silver.ibge_pib_municipio`
  - `bronze.ibge_dtb_municipio` → `silver.ibge_dtb_municipio`
- **Arquivos brutos:** `data/raw/ibge/<fonte>/AAAA-MM-DD/`, cada pasta com
  um `MANIFEST.md` contendo: origem, data, número de linhas e checksum. A
  extração atual é a de **2026-11-08** (as três fontes).
- **Chave:** `id_municipio` com **7 dígitos, como texto** (preservar zeros à
  esquerda).
- **Teste de cobertura de junção** com o SNIS **antes de qualquer join** —
  medir quantos `id_municipio` casam entre as fontes e registrar os não casados.

## Regra de citação

- Todo **mart** e toda **ficha de indicador** cita o **ID da fonte**
  (IBGE-POP, IBGE-DTB, IBGE-PIB).
- O **dashboard** exibe: `Fonte: IBGE (<ID>), SNIS`.

## Janela analítica

- **2010–2021** para tudo que usa o IBGE (limitada pela série do PIB).
