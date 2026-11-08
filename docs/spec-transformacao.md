# Spec da transformação (bronze → silver)

| | |
|---|---|
| **Status** | rascunho para aprovação |
| **Versão** | 2 |
| **Data** | 2026-11-08 |
| **Responsável** | Luiz |
| **Origem** | `bronze.municipio_agua_esgoto` (somente leitura) |
| **Destino** | banco `snis.duckdb` · schema `silver` · tabela `municipio_agua_esgoto` |

> **Base dos números:** [`docs/investigacao-silver.md`](investigacao-silver.md)
> (rodadas 1 e 2). Os nomes, a ordem e as contagens das 133 colunas foram
> reconferidos na bronze via MCP (somente leitura, `duckdb_columns()`) na
> escrita desta spec: **26 INTEGER · 2 VARCHAR · 105 DECIMAL**.

---

## 0. Contrato de dados

| | |
|---|---|
| **Fonte** | SNIS (Sistema Nacional de Informações sobre Saneamento), via Base dos Dados |
| **Grão** | um município por ano |
| **Chave** | `(ano, id_municipio)` — 0 duplicatas, 0 nulos |
| **Cobertura** | 1995–2022 · 5.549 municípios · 27 UFs |
| **Volume** | 119.256 linhas · 133 colunas |
| **Atualização** | anual — ano novo significa recarregar a bronze e reexecutar a silver |

**Fora de escopo** (tudo isto é responsabilidade da gold, não da silver):

- nomes de município e de UF (a silver carrega só `id_municipio` e `sigla_uf`);
- correção de anomalias (negativos, índices acima de 100, divergências de população);
- conversão de unidades;
- deflação ou qualquer ajuste monetário;
- cálculo de indicadores.

A silver faz **uma coisa só**: tipar fielmente a bronze e corrigir o único erro
de digitação de nome de coluna. Nada de semântica de negócio.

---

## 1. Escopo

| Origem | Destino | Linhas | Colunas |
|---|---|---|---|
| `bronze.municipio_agua_esgoto` | `silver.municipio_agua_esgoto` | 119.256 → 119.256 | 133 |

- **119.256 linhas entram e 119.256 saem.** Nenhuma linha é filtrada,
  deduplicada ou acrescentada.
- **133 colunas**, na **mesma ordem** da bronze. Nenhuma coluna é descartada
  nem criada. Sem colunas de auditoria.

---

## 2. Nomes

Todos os nomes de coluna são mantidos exatamente como na bronze, com **uma única
exceção**:

| Bronze | Silver | Motivo |
|---|---|---|
| `populacao_atentida_esgoto` | `populacao_atendida_esgoto` | corrige erro de digitação da fonte (*atentida* → *atendida*) |

O nome corrigido **não colide** com nenhuma outra coluna da tabela (conferido:
não existe `populacao_atendida_esgoto` na bronze). O conteúdo da coluna é
preservado valor a valor; só o rótulo muda.

---

## 3. Tipos

A conversão é feita **em SQL pelo DuckDB** (`CAST` dentro do `CREATE OR REPLACE
TABLE ... AS SELECT`), **nunca** com pandas.

| Classe | Nº | Tipo silver | Motivo |
|---|---|---|---|
| `ano` | 1 | `INTEGER` | ano é inteiro de 4 dígitos (1995–2022); cabe com folga em `INTEGER` |
| `id_municipio`, `sigla_uf` | 2 | `VARCHAR` | são códigos/rótulos, não números. `id_municipio` tem zeros à esquerda estruturais (prefixo de UF); virar número destruiria o código. `sigla_uf` é texto |
| `populacao_*` e `quantidade_*` | 25 | `INTEGER` | investigação: todos inteiros, sem casas decimais, sem negativos; máximo ≈ 12,4 mi (`populacao_*`) e ≈ 6,45 mil (`quantidade_empregado`) — tudo abaixo de 2,1 bi, logo `INTEGER` basta |
| monetárias (`receita_*`, `arrecadacao_total`, `credito_areceber`, `despesa*`, `investimento_*`) | 51 | `DECIMAL(18,2)` | valores em reais com **no máximo 2 casas decimais**; máximo observado de 26.465.758.127 (≈26,5 bi) (`investimento_agua_prestador`). `DECIMAL` evita o erro de arredondamento binário do `DOUBLE` em dinheiro |
| medidas/índices (`volume_*`, `extensao_*`, `consumo_eletrico_*`, `indice_*`) | 54 | `DECIMAL(18,2)` | decimais com **no máximo 2 casas**; máximo observado ≈ 47,5 mi (`volume_esgoto_*`). `DECIMAL(18,2)` cobre magnitude e escala sem perda de precisão |

**Totais: 26 `INTEGER` · 2 `VARCHAR` · 105 `DECIMAL(18,2)`** (= 51 + 54).

Observações:

- `quantidade_sede_municipal_agua` e `quantidade_sede_municipal_esgoto`
  continuam **`INTEGER`**, não booleano: hoje só assumem 0/1, mas são contagens
  por definição e nada garante que não passem de 1 numa carga futura.
- `quantidade_empregado` é **`INTEGER`** (valores inteiros), apesar de aparecer
  perto das monetárias no arquivo.
- `DECIMAL(18,2)`: 18 dígitos totais, 2 decimais → até 16 dígitos inteiros
  (≈ 10 quatrilhões), muito acima do maior valor observado (≈ 26,5 bi). Margem
  deliberada para cargas futuras.

### Regra do CAST

- O `CAST` é **estrito**: qualquer valor que não converta para o tipo-alvo
  **derruba a transação** (ver §4). Não se usa `TRY_CAST` para produzir dado —
  `TRY_CAST` mascararia lixo transformando-o em `NULL`.
- `TRY_CAST` só é permitido **depois** de uma falha, em consulta de
  **diagnóstico**, para localizar a coluna/linha culpada e montar a mensagem de
  erro. Nunca no caminho de gravação.

---

## 4. Regras de qualidade

Três níveis: **bloqueante** (derruba tudo), **alerta** (passa, mas conta e
avisa) e **informação** (só conta).

### 4.1 Bloqueantes → `ROLLBACK` + `sys.exit(1)`

Cada falha imprime uma mensagem clara com **a coluna e o valor** culpados. Como
tudo roda numa transação única, o `ROLLBACK` garante que **nenhuma tabela
parcial** fique no banco.

| # | Condição | Observação |
|---|---|---|
| B1 | `bronze.municipio_agua_esgoto` ausente | pré-condição; nada a transformar |
| B2 | valor que **não converte** para o tipo-alvo | `CAST` estrito; diagnóstico com `TRY_CAST` depois da falha |
| B3 | valor **fora da faixa** do tipo-alvo | ex.: inteiro acima de `INTEGER`, decimal que estoura `DECIMAL(18,2)` |
| B4 | valor de uma das **105 colunas `DECIMAL`** com **mais de 2 casas decimais** | o `CAST` para `DECIMAL(_,2)` **arredonda em silêncio**; por isso a verificação acontece **ANTES** de converter, sobre o texto da bronze |
| B5 | `ano` fora do formato `AAAA` (4 dígitos) | chave temporal |
| B6 | `id_municipio` fora de **7 dígitos** (`^[0-9]{7}$`) | integridade de chave |
| B7 | chave `(ano, id_municipio)` **nula ou repetida** | grão do contrato (ver §5) |
| B8 | contagem de **linhas** ou de **colunas** diferente da bronze | espelho fiel em volume e largura |

> **Por que B4 vem antes do CAST:** `CAST('1,235' ...)` nem é o caso (o separador
> é ponto), mas `CAST('10.239' AS DECIMAL(18,2))` devolve `10.24` **sem erro**.
> Arredondar dinheiro ou medida em silêncio é perda de dado disfarçada de
> sucesso. A spec exige detectar `> 2` casas **no texto** e **falhar**, não
> arredondar.

### 4.2 Alertas → preservar o dado, imprimir a contagem

Não bloqueiam. São **fatos conhecidos** da investigação; a silver os **mantém** e
apenas **conta e reporta** (o tratamento é da gold). Contagens de referência:

| # | Alerta | Contagem de referência |
|---|---|---|
| A1 | colunas com valores **negativos** | **43 colunas**: `despesa*` 15.460 · `indice_*` 10.890 · `volume_*` 1 (`volume_agua_micromedido_economia_ativa`) + receita/crédito/investimento |
| A2 | `populacao_atendida_agua` > `populacao_urbana` | **47.934 linhas** |
| A3 | `indice_*` acima de **100** | 23 das 30 colunas `indice_*` (nem todo índice é percentual) |
| A4 | `populacao_urbana_atendida_esgoto` **100% nula em 2022** | 5.425/5.425 |

As contagens são **recalculadas na execução** sobre a tabela silver; os números
acima são referência da investigação para os testes, não constantes do código.

### 4.3 Informação → só contar

- **Nulos por coluna**: mantidos (célula vazia da bronze continua `NULL`),
  contados e somados no total de células nulas da saída (§7). Nenhum nulo é
  preenchido.

---

## 5. Duplicatas

A chave é `(ano, id_municipio)`. Se a transformação encontrar a chave repetida,
ela **para** (bloqueante B7) e **mostra as linhas** envolvidas — **sem escolher**
qual manter. Deduplicar seria decisão de negócio, e isso é da gold. A
investigação confirma 0 duplicatas na bronze; o teste existe para proteger
cargas futuras.

---

## 6. Nulos, zeros, negativos e anomalias

A silver **não apaga, não preenche, não arredonda e não corrige**:

- **nulos** permanecem nulos;
- **zeros** permanecem zeros;
- **negativos** permanecem negativos (estornos, ajustes contábeis ou erros de
  origem — não cabe à silver decidir);
- **anomalias** (índices acima de 100, população atendida maior que a urbana,
  volume negativo, coluna que zera em 2022) **ficam na tabela** e são
  **documentadas** via alertas (§4.2).

Qualquer tratamento, imputação ou correção é responsabilidade da **gold**.

---

## 7. Saída na tela

UTF-8. Milhar separado por **ponto**. Duas partes:

1. **Uma linha de resumo** com: nome da tabela, linhas de entrada e de saída,
   número de colunas, total de células nulas. Ex.:

   ```
   silver.municipio_agua_esgoto · entrada 119.256 · saída 119.256 · 133 colunas · 5.659.843 células nulas (referência da carga atual)
   ```

2. **Um bloco "Alertas"** com as contagens de §4.2:

   ```
   Alertas:
   - negativos: 43 colunas (despesa* 15.460 · indice_* 10.890 · volume 1 · ...)
   - populacao_atendida_agua > populacao_urbana: 47.934 linhas
   - indice_* acima de 100: 23 colunas
   - populacao_urbana_atendida_esgoto 100% nula em 2022
   ```

---

## Regras transversais

- Gravação com **`CREATE OR REPLACE TABLE silver.municipio_agua_esgoto`** dentro
  de **uma transação única**; qualquer bloqueante faz **`ROLLBACK`**.
- **`CREATE SCHEMA IF NOT EXISTS silver`** antes de gravar.
- A **bronze nunca é alterada** (conexão de leitura sobre ela); `data/raw/`
  nunca é tocado.
- **Sem colunas de auditoria** (sem `carregado_em`, sem hash, sem origem).
- **Idempotente**: rodar duas vezes dá o mesmo resultado; a tabela é recriada,
  não acumulada.

---

## Critérios de aceite

| # | Critério | Como verificar |
|---|---|---|
| 1 | 119.256 linhas | `SELECT count(*)` na silver = 119.256 |
| 2 | 133 colunas | `count(*)` em `duckdb_columns()` da silver = 133 |
| 3 | tipos 26/2/105 | contar por `data_type`: 26 `INTEGER`, 2 `VARCHAR`, 105 `DECIMAL(18,2)` |
| 4 | nulos iguais | para cada uma das 133 colunas, `count(*)-count(col)` igual em bronze e silver (par por nome, usando `populacao_atendida_esgoto` ↔ `populacao_atentida_esgoto`); total de células nulas = 5.659.843 |
| 5 | somas das 105 `DECIMAL` iguais | `sum(CAST(col AS DECIMAL(38,6)))` na bronze = `sum(CAST(col AS DECIMAL(38,6)))` na silver, coluna a coluna |
| 6 | somas das 26 inteiras iguais | `sum(CAST(col AS DECIMAL(38,6)))` igual em bronze e silver para as 26 colunas inteiras (incl. `ano`) |
| 7 | negativos iguais | para as 43 colunas com negativos, `count(*) WHERE col < 0` igual em bronze (via `TRY_CAST`) e silver |
| 8 | chaves | `id_municipio` 100% com 7 dígitos; `count(DISTINCT id_municipio)` = 5.549 |
| 9 | anomalia de população preservada | `populacao_atendida_agua > populacao_urbana` = 47.934 linhas na silver |
| 10 | 100% nulo em 2022 | `populacao_urbana_atendida_esgoto` com 5.425 nulos em 5.425 linhas de 2022 |
| 11 | coluna renomeada | `populacao_atendida_esgoto` existe na silver, `populacao_atentida_esgoto` não, e os valores batem 1:1 com a coluna original da bronze |
| 12 | duas execuções iguais + fontes intactas | rodar 2× → mesma contagem/soma; bronze e `data/raw/` inalterados |

---

## Limitações e perguntas em aberto

- **Unidades** das medidas (volume, extensão, consumo elétrico) a confirmar no
  dicionário do SNIS. A silver **não converte** unidade nenhuma.
- **Valores monetários** são provavelmente **nominais** (reais da data da
  coleta); não há deflação na silver.
- Por que `populacao_urbana_atendida_esgoto` é **100% nula em 2022** — mudança
  metodológica da fonte ou falha de carga? Não confirmado.
- **Semântica de `populacao_atendida_agua`** frente à população urbana: a
  hipótese é que seja atendimento total (urbano+rural), o que explicaria as
  47.934 linhas em que supera `populacao_urbana`; não confirmado no dicionário.
- **Nem todo `indice_*` é percentual**: alguns são taxas/razões cujo valor acima
  de 100 é esperado (ex.: consumo per capita em L/hab·dia). A classificação
  percentual × taxa não foi confirmada no dicionário oficial.

---

## Registro de decisões

| Decisão | Alternativa | Motivo |
|---|---|---|
| `DECIMAL(18,2)` nas 105 colunas | `DOUBLE` | `DOUBLE` tem erro de arredondamento binário; em dinheiro e medida com 2 casas, `DECIMAL` é exato. A investigação mostrou máx. 2 casas decimais em todas |
| `INTEGER` nas 26 inteiras | `BIGINT` | maior valor observado ≈ 12,4 mi, muito abaixo de 2,1 bi; `INTEGER` é suficiente e mais enxuto. `BIGINT` seria capacidade ociosa |
| Corrigir `populacao_atentida_esgoto` → `populacao_atendida_esgoto` | manter a grafia da fonte | é erro de digitação óbvio; a silver é a camada onde se corrige nome. Não colide com coluna existente |
| Preservar anomalias | corrigir/filtrar na silver | separação de responsabilidades: a silver tipa fielmente, a gold trata. Corrigir aqui esconderia o dado bruto |
| Verificar casas decimais **antes** do `CAST` | confiar no `CAST` | `CAST(... AS DECIMAL(_,2))` arredonda em silêncio; só a checagem prévia no texto detecta perda de precisão e falha de propósito |

---

## Entrega do Claude Code (quando for implementar)

- **Docstring** no módulo/função com o **motivo de cada regra** (não só o quê, o
  porquê).
- **Comentários** apenas onde a decisão não é óbvia (ex.: por que B4 roda antes
  do `CAST`, por que `INTEGER` e não `BIGINT`).
- **Lista do que foi assumido fora da spec** impressa ou documentada ao final.

---

## Anexo A — As 133 colunas por tipo

Confirmado via MCP (`duckdb_columns()` sobre `bronze.municipio_agua_esgoto`,
somente leitura): nomes e ordem batem com a bronze; contagens **26 / 2 / 105**.
Usa-se o nome **`populacao_atendida_esgoto`** (corrigido).

### INTEGER (26)

```
ano
populacao_atendida_agua
populacao_atendida_esgoto          -- renomeada (bronze: populacao_atentida_esgoto)
populacao_urbana
populacao_urbana_residente_agua
populacao_urbana_atendida_agua
populacao_urbana_atendida_agua_ibge
populacao_urbana_residente_esgoto
populacao_urbana_atendida_esgoto
populacao_urbana_residente_esgoto_ibge
quantidade_sede_municipal_agua
quantidade_sede_municipal_esgoto
quantidade_localidade_agua
quantidade_localidade_esgoto
quantidade_ligacao_ativa_agua
quantidade_ligacao_ativa_esgoto
quantidade_ligacao_total_agua
quantidade_ligacao_total_esgoto
quantidade_economia_ativa_agua
quantidade_economia_ativa_esgoto
quantidade_ligacao_micromedia_ativa_agua
quantidade_economia_residencial_ativa_agua
quantidade_economia_residencial_ativa_esgoto
quantidade_economia_micromedida_ativa_agua
quantidade_economia_residencial_micromedida_ativa_agua
quantidade_empregado
```

### VARCHAR (2)

```
id_municipio
sigla_uf
```

### DECIMAL(18,2) (105)

**Medidas/índices (54):**

```
extensao_rede_agua
extensao_rede_esgoto
volume_agua_produzido
volume_agua_tratada_eta
volume_agua_micromedido
volume_agua_consumido
volume_agua_faturado
volume_agua_macromedido
volume_agua_tratada_desinfeccao
volume_agua_bruta_exportado
volume_agua_tratada_importado
volume_agua_tratada_exportado
volume_agua_micromedido_economia_ativa
volume_servico_agua
volume_agua_fluoretada
consumo_eletrico_sistemas_agua
volume_esgoto_coletado
volume_esgoto_tratado
volume_esgoto_faturado
volume_esgoto_bruto_exportado
volume_esgoto_bruto_importado
volume_esgoto_importado
volume_esgoto_bruto_exportado_tratamento_importador
consumo_eletrico_sistemas_esgoto
indice_agua_ligacao
indice_hidrometracao
indice_macromedicao_volume_disponibilizado
indice_macromedicao
indice_perda_faturamento
indice_micromedido_economia
indice_coleta_esgoto
indice_tratamento_esgoto
indice_consumo_agua_faturado
indice_extensao_agua_ligacao
indice_extensao_esgoto_ligacao
indice_consumo_agua_per_capita
indice_atendimento_urbano_agua
indice_atendimento_agua_esgoto
indice_volume_agua_economia
indice_faturamento_agua
indice_participacao_economia_agua
indice_micromedicao_relativo_agua
indice_esgotamento_agua_consumida
indice_atendimento_esgoto_esgoto
indice_perda_distribuicao_agua
indice_perda_linear_agua
indice_perda_ligacao_agua
indice_consumo_agua
indice_consumo_medio_agua
indice_atendimento_total_agua
indice_atendimento_esgoto_agua
indice_fluoretacao_agua
indice_consumo_energia_agua
indice_consumo_energia_esgoto
```

**Monetárias (51):**

```
receita_operacional_direta
receita_operacional_direta_agua
receita_operacional_direta_esgoto
receita_operacional_indireta
receita_operacional_direta_agua_exportada
receita_operacional
receita_operacional_direta_esgoto_importado
arrecadacao_total
credito_areceber
despesa_pessoal
despesa_produto_quimico
despesa_energia
despesa_servico_terceiro
despesa_exploracao
despesas_juros_divida
despesa_total_servico
despesa_ativo
despesa_agua_importada
despesa_fiscal
despesa_fiscal_nao_computada
despesa_exploracao_outro
despesa_servico_outro
despesa_amortizacao_divida
despesas_juros_divida_excecao
despesa_divida_variacao
despesa_divida_total
despesa_esgoto_exportado
despesa_capitalizavel_municipio
despesa_capitalizavel_estado
despesa_capitalizavel_prestador
investimento_agua_prestador
investimento_esgoto_prestador
investimento_outro_prestador
investimento_recurso_proprio_prestador
investimento_recurso_oneroso_prestador
investimento_recurso_nao_oneroso_prestador
investimento_total_prestador
investimento_agua_municipio
investimento_esgoto_municipio
investimento_outro_municipio
investimento_recurso_proprio_municipio
investimento_recurso_oneroso_municipio
investimento_recurso_nao_oneroso_municipio
investimento_total_municipio
investimento_agua_estado
investimento_esgoto_estado
investimento_outro_estado
investimento_recurso_proprio_estado
investimento_recurso_oneroso_estado
investimento_recurso_nao_oneroso_estado
investimento_total_estado
```

> **Ordem na tabela:** as colunas acima estão listadas agrupadas por tipo para
> leitura. Na tabela silver a **ordem física é a mesma da bronze** (coluna 1 a
> 133); `quantidade_empregado` (posição 92) fica entre as monetárias no arquivo,
> mas é `INTEGER`.
