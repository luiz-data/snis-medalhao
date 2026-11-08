# Catálogo de fontes externas — IBGE

Este catálogo é **obrigatório**: nada vindo do IBGE entra no projeto sem uma
linha aqui. Nenhuma tabela, seed, mart ou ficha de indicador pode citar uma
fonte do IBGE que não esteja descrita neste arquivo. Toda ingestão nova começa
pela entrada correspondente abaixo (ou pela criação dela).

---

## IBGE-POP — População residente municipal

- **ID interno:** IBGE-POP
- **Nome:** População residente municipal
- **Origem:** Base dos Dados
- **Tabela/identificador:** `br_ibge_populacao.municipio`
- **URL:** https://basedosdados.org/dataset/br-ibge-populacao
- **Data de acesso:** a preencher na ingestão
- **Versão/publicação:** municípios atualizados pelo Censo 2022; série montada
  a partir de estimativas (SIDRA 6579, 2001–2021, referência 1º de julho) e
  Censos/Contagem (SIDRA 202, 793, 9514)
- **Cobertura temporal:** 1991–2025
- **Chave de junção:** `id_municipio` (7 dígitos, texto)
- **Uso no projeto (marts):** `atendimento_porte_ano`,
  `populacao_sem_servico_uf_ano`, `investimento_per_capita_uf_ano`,
  `atendimento_vs_pib_2021`, `avanco_por_renda_painel`
- **Limitações conhecidas:** série montada a partir de várias pesquisas; valores
  de anos antigos podem ser revisados entre publicações.

---

## IBGE-DTB — Divisão Territorial Brasileira

- **ID interno:** IBGE-DTB
- **Nome:** Divisão Territorial Brasileira (municípios, UF e região)
- **Origem:** DTB (IBGE)
- **Tabela/identificador:** DTB — tabela de municípios/UF/região
- **URL:** https://www.ibge.gov.br/geociencias/organizacao-do-territorio/estrutura-territorial/23701-divisao-territorial-brasileira.html
- **Data de acesso:** a preencher na ingestão
- **Versão/publicação:** registrar o **ano** da DTB usada na ingestão
- **Cobertura temporal:** fotografia territorial do ano da publicação
- **Chave de junção:** `id_municipio` (7 dígitos; 2 primeiros = código da UF)
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
- **Origem:** SIDRA
- **Tabela/identificador:** SIDRA 5938
- **URL:** https://sidra.ibge.gov.br/tabela/5938
- **Data de acesso:** a preencher na ingestão
- **Versão/publicação:** série 2002–2021 (2002–2009 retropolada)
- **Cobertura temporal:** 2002–2021; **janela do projeto: 2010–2021**
- **Chave de junção:** `id_municipio` (7 dígitos, texto)
- **Uso no projeto (marts):** `atendimento_vs_pib_2021`, `avanco_por_renda_painel`
- **Limitações conhecidas:** não houve publicação regular em 2024 por mudança de
  ano-base das Contas Nacionais; **valores nominais** (só comparar dentro do
  mesmo ano, sem correção).

---

## Convenções

- **Nomes de tabela — prefixo `ibge_`:**
  - `bronze.ibge_populacao_municipio` → `silver.ibge_populacao_municipio`
  - `bronze.ibge_pib_municipio` → `silver.ibge_pib_municipio`
  - `bronze.ibge_dtb_municipio` → `silver.ibge_dtb_municipio`
- **Arquivos brutos:** `data/raw/ibge/<fonte>/<data_extracao>/`, cada pasta com
  um `MANIFEST.md` contendo: origem, data, número de linhas e checksum.
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
