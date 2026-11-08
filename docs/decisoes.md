# Decisões do pipeline SNIS — camada gold

Registro das decisões fechadas que orientam a spec da gold e a ingestão do IBGE.
Base de evidência: seções "Rodada 3" e "Verificação das decisões" de
[`investigacao-silver.md`](investigacao-silver.md); fontes externas em
[`fontes-ibge.md`](fontes-ibge.md); fórmulas em [`indicadores.md`](indicadores.md).

## Decisões

| # | Data | Decisão | Motivo | Veredito final |
|---|---|---|---|---|
| D1 | 2026-11-08 | Marts **6 a 10** dependem de **IBGE-POP**; **9 e 10** também de **IBGE-PIB**; marts **1, 3, 4, 5, 7 e 8** usam **IBGE-DTB** (UF/região). Só o **mart 2** é 100% SNIS. | A silver não tem população total, PIB nem região (0 colunas em `duckdb_columns()` para `%pib%`, `%total_ibge%`, `%regiao%`); as 13 colunas SNIS das fórmulas existem. | **CONFIRMA** |
| D2 | 2026-11-08 | **2021 é o ano de referência dos marts urbanos** (1, 4, 9, 10). As colunas `_ibge` entram **apenas como série alternativa rotulada**. **Nenhum mart urbano usa 2022.** | Em 2022 a população urbana autodeclarada é 100% nula; em 2021 a água urbana é completa (~5.300 informantes). As `_ibge` diferem ~38% na mediana da autodeclarada (>10% em ~89% dos municípios) → medida distinta, não recálculo. | **CONFIRMA COM AJUSTE** (frear uso de `_ibge` como "sensibilidade") |
| D3 | 2026-11-08 | Perdas (mart 3) pela **fórmula completa do IN049**: `(AG006+AG018−AG010−AG024)/(AG006+AG018−AG024)×100`, com `volume_agua_produzido`, `volume_agua_tratada_importado`, `volume_agua_consumido`, `volume_servico_agua`. **Excluir linhas inconsistentes** `(AG006+AG018−AG024) < AG010` **com flag e contagem por ano**, como salvaguarda. | Com o IN049 completo o índice nacional já fica em **~36–39% com todas as linhas** (nível oficial ~40%); as inconsistentes caem para **0–57/ano** e a exclusão é **imaterial** (≤0,15 pp; 0 UFs mudam >5 pp). A regra simplificada `produzido<consumido` daria ~23% e **excluiria importadores legítimos** (que usam AG018). | **CONFIRMA COM AJUSTE** (usar fórmula completa; exclusão vira salvaguarda) |
| D4 | 2026-11-08 | **Flag `prestador_regional_provavel`** quando investimento **per capita > R$ 1.000/hab** (≈ p99,5 nacional). Manter esses municípios **nos totais por UF**. **Mart 8 com duas colunas** (com e sem os sinalizados). UFs afetadas recebem **nota visível** (destaque para **RN**). | A distorção é concentração no município-sede (não duplicação; só 3 valores repetidos). Excluir dos totais destruiria **RN (−36%)** e afetaria MA/SE/PE; o critério R$ 1.000/hab flaga ~290 casos sem derrubar os totais. | **CONFIRMA COM AJUSTE** (critério objetivo + mart 8 com 2 colunas) |
| D5 | 2026-11-08 | Violação A2 residual (`populacao_urbana_atendida_agua > populacao_urbana`) tratada por **exclusão com flag**, **sem clamp**. | Impacto negligível (exclusão e clamp diferem do baseline em ≤0,17 pp; só **TO** passa de 1% das linhas). Exclusão é mais transparente (dado inválido não entra). | **CONFIRMA COM AJUSTE** (baixo risco; exclusão por transparência) |
| D6 | 2026-11-08 | Usar a **DTB mais recente (2025)**. Os **31 municípios de ano único** (12 entrantes em 2022, 19 de meio de série) entram no **teste de cobertura como divergências**, **sem correção manual**. | Nenhum id está fora do padrão de 7 dígitos; são majoritariamente novos informantes de 2022 e reportes esporádicos. A conciliação é de cobertura/vigência, não de formato. | **CONFIRMA** |

## Pendências

### Spec da silver v2.1
- **Alerta A2** — formalizar o alerta `populacao_urbana_atendida_agua >
  populacao_urbana` como flag por linha (ver D5); residual pequeno em 2010–2021
  (≤43/ano em água), mas massivo antes de 2010.
- **Escopo do alerta de 2022 nulo** — fechar a lista das **8 colunas 100% nulas
  em 2022**: `populacao_urbana`, `populacao_urbana_residente_agua`,
  `populacao_urbana_atendida_agua`, `populacao_urbana_residente_esgoto`,
  `populacao_urbana_atendida_esgoto`, `indice_atendimento_urbano_agua`,
  `indice_atendimento_agua_esgoto`, `indice_atendimento_esgoto_esgoto`. As
  variantes `_ibge` **não** entram (têm dados em 2022).

### Dicionário SNIS — itens "a confirmar"
- **IN049 / "volume disponibilizado"** — confirmar a definição oficial exata
  (AG006 + AG018 − AG024 vs. variações com AG019/AG020 de exportação) no
  glossário; a redação atual usa AG006, AG018, AG010, AG024.
- **Semântica das colunas de população** — confirmar se `populacao_atendida_agua`
  é total (urbano+rural) e os campos `urbana*` são subconjuntos (hipótese da
  Rodada 1/2, não confirmada no dicionário).
- **Investimento e receita** — confirmar a semântica fina (prestador vs.
  município vs. estado; receita direta vs. indireta) para os marts 5 e 8.
- **Classificação percentual vs. taxa** dos `indice_*` — confirmar no dicionário
  oficial quais índices são 0–100 e quais são razões sem teto.
- **Versão/ano da DTB e da série IBGE-POP/PIB** — registrar na ingestão
  (ver [`fontes-ibge.md`](fontes-ibge.md)); nomes, emancipações e fusões dos 31
  municípios de ano único ficam **a confirmar na ingestão da DTB**.
