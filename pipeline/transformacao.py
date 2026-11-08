"""Transformação bronze -> silver do SNIS (municipio_agua_esgoto).

Implementa docs/spec-transformacao.md. A silver faz UMA coisa só: tipar
fielmente a bronze (que está toda em VARCHAR por causa do `all_varchar=true`
da ingestão) e corrigir o único erro de digitação de nome de coluna
(`populacao_atentida_esgoto` -> `populacao_atendida_esgoto`). Nada de
semântica de negócio: nenhuma linha é filtrada, nenhuma anomalia é corrigida
e nenhuma unidade é convertida — isso tudo é responsabilidade da gold.

Porquê das regras (resumo da spec):

- Tipos 26 INTEGER / 2 VARCHAR / 105 DECIMAL(18,2):
  * INTEGER (não BIGINT) porque o maior inteiro observado (~12,4 mi) está
    muito abaixo de 2,1 bi; BIGINT seria capacidade ociosa.
  * VARCHAR em `id_municipio` porque é código com zeros à esquerda
    estruturais (prefixo de UF); virar número destruiria o código.
    `sigla_uf` é texto por natureza.
  * DECIMAL(18,2) (não DOUBLE) porque DOUBLE tem erro de arredondamento
    binário; em dinheiro e medida com 2 casas, DECIMAL é exato. A
    investigação mostrou no máximo 2 casas decimais em todas as 105 colunas.

- CAST estrito: qualquer valor que não converta derruba a transação. Não se
  usa TRY_CAST no caminho de gravação porque TRY_CAST mascararia lixo
  virando NULL.

- As verificações de formato rodam por REGEX sobre o TEXTO da bronze, ANTES
  do CAST. O motivo crítico é o B4: `CAST('10.239' AS DECIMAL(18,2))`
  devolve `10.24` SEM erro — arredonda dinheiro/medida em silêncio, que é
  perda de dado disfarçada de sucesso. Só a checagem prévia no texto
  (> 2 casas) detecta e falha de propósito.

- Tudo roda numa transação única: qualquer bloqueante faz ROLLBACK, então
  nenhuma tabela parcial fica no banco.
"""

import sys

import duckdb

from pipeline.db import conectar

BRONZE = "bronze.municipio_agua_esgoto"
SILVER = "silver.municipio_agua_esgoto"

# Renomeações de coluna: nome na bronze (erro de digitação) -> nome corrigido
# na silver. É a ÚNICA fonte da verdade da diferença de nomes entre as camadas.
RENOMEACOES = {"populacao_atentida_esgoto": "populacao_atendida_esgoto"}

# Inverso: nome silver -> nome bronze (usado para ler/consultar a bronze).
_SILVER_PARA_BRONZE = {silver: bronze for bronze, silver in RENOMEACOES.items()}


def nome_bronze(col_silver):
    """Traduz um nome de coluna da silver para o nome correspondente na bronze.

    As constantes do Anexo A usam os nomes silver (já corrigidos), mas a bronze
    guarda o nome original. Toda consulta que LÊ a bronze deve passar por aqui.
    """
    return _SILVER_PARA_BRONZE.get(col_silver, col_silver)


def nome_silver(col_bronze):
    """Traduz um nome de coluna da bronze para o nome usado na silver."""
    return RENOMEACOES.get(col_bronze, col_bronze)

# --- Anexo A da spec: fonte única de verdade dos tipos -----------------------
# As listas usam os nomes SILVER (ou seja, já com a correção de digitação).
# `ano` entra aqui como INTEGER.

INTEIROS = [
    "ano",
    "populacao_atendida_agua",
    "populacao_atendida_esgoto",  # renomeada (bronze: populacao_atentida_esgoto)
    "populacao_urbana",
    "populacao_urbana_residente_agua",
    "populacao_urbana_atendida_agua",
    "populacao_urbana_atendida_agua_ibge",
    "populacao_urbana_residente_esgoto",
    "populacao_urbana_atendida_esgoto",
    "populacao_urbana_residente_esgoto_ibge",
    "quantidade_sede_municipal_agua",
    "quantidade_sede_municipal_esgoto",
    "quantidade_localidade_agua",
    "quantidade_localidade_esgoto",
    "quantidade_ligacao_ativa_agua",
    "quantidade_ligacao_ativa_esgoto",
    "quantidade_ligacao_total_agua",
    "quantidade_ligacao_total_esgoto",
    "quantidade_economia_ativa_agua",
    "quantidade_economia_ativa_esgoto",
    "quantidade_ligacao_micromedia_ativa_agua",
    "quantidade_economia_residencial_ativa_agua",
    "quantidade_economia_residencial_ativa_esgoto",
    "quantidade_economia_micromedida_ativa_agua",
    "quantidade_economia_residencial_micromedida_ativa_agua",
    "quantidade_empregado",
]

TEXTOS = [
    "id_municipio",
    "sigla_uf",
]

DECIMAIS = [
    # Medidas/índices (54)
    "extensao_rede_agua",
    "extensao_rede_esgoto",
    "volume_agua_produzido",
    "volume_agua_tratada_eta",
    "volume_agua_micromedido",
    "volume_agua_consumido",
    "volume_agua_faturado",
    "volume_agua_macromedido",
    "volume_agua_tratada_desinfeccao",
    "volume_agua_bruta_exportado",
    "volume_agua_tratada_importado",
    "volume_agua_tratada_exportado",
    "volume_agua_micromedido_economia_ativa",
    "volume_servico_agua",
    "volume_agua_fluoretada",
    "consumo_eletrico_sistemas_agua",
    "volume_esgoto_coletado",
    "volume_esgoto_tratado",
    "volume_esgoto_faturado",
    "volume_esgoto_bruto_exportado",
    "volume_esgoto_bruto_importado",
    "volume_esgoto_importado",
    "volume_esgoto_bruto_exportado_tratamento_importador",
    "consumo_eletrico_sistemas_esgoto",
    "indice_agua_ligacao",
    "indice_hidrometracao",
    "indice_macromedicao_volume_disponibilizado",
    "indice_macromedicao",
    "indice_perda_faturamento",
    "indice_micromedido_economia",
    "indice_coleta_esgoto",
    "indice_tratamento_esgoto",
    "indice_consumo_agua_faturado",
    "indice_extensao_agua_ligacao",
    "indice_extensao_esgoto_ligacao",
    "indice_consumo_agua_per_capita",
    "indice_atendimento_urbano_agua",
    "indice_atendimento_agua_esgoto",
    "indice_volume_agua_economia",
    "indice_faturamento_agua",
    "indice_participacao_economia_agua",
    "indice_micromedicao_relativo_agua",
    "indice_esgotamento_agua_consumida",
    "indice_atendimento_esgoto_esgoto",
    "indice_perda_distribuicao_agua",
    "indice_perda_linear_agua",
    "indice_perda_ligacao_agua",
    "indice_consumo_agua",
    "indice_consumo_medio_agua",
    "indice_atendimento_total_agua",
    "indice_atendimento_esgoto_agua",
    "indice_fluoretacao_agua",
    "indice_consumo_energia_agua",
    "indice_consumo_energia_esgoto",
    # Monetárias (51)
    "receita_operacional_direta",
    "receita_operacional_direta_agua",
    "receita_operacional_direta_esgoto",
    "receita_operacional_indireta",
    "receita_operacional_direta_agua_exportada",
    "receita_operacional",
    "receita_operacional_direta_esgoto_importado",
    "arrecadacao_total",
    "credito_areceber",
    "despesa_pessoal",
    "despesa_produto_quimico",
    "despesa_energia",
    "despesa_servico_terceiro",
    "despesa_exploracao",
    "despesas_juros_divida",
    "despesa_total_servico",
    "despesa_ativo",
    "despesa_agua_importada",
    "despesa_fiscal",
    "despesa_fiscal_nao_computada",
    "despesa_exploracao_outro",
    "despesa_servico_outro",
    "despesa_amortizacao_divida",
    "despesas_juros_divida_excecao",
    "despesa_divida_variacao",
    "despesa_divida_total",
    "despesa_esgoto_exportado",
    "despesa_capitalizavel_municipio",
    "despesa_capitalizavel_estado",
    "despesa_capitalizavel_prestador",
    "investimento_agua_prestador",
    "investimento_esgoto_prestador",
    "investimento_outro_prestador",
    "investimento_recurso_proprio_prestador",
    "investimento_recurso_oneroso_prestador",
    "investimento_recurso_nao_oneroso_prestador",
    "investimento_total_prestador",
    "investimento_agua_municipio",
    "investimento_esgoto_municipio",
    "investimento_outro_municipio",
    "investimento_recurso_proprio_municipio",
    "investimento_recurso_oneroso_municipio",
    "investimento_recurso_nao_oneroso_municipio",
    "investimento_total_municipio",
    "investimento_agua_estado",
    "investimento_esgoto_estado",
    "investimento_outro_estado",
    "investimento_recurso_proprio_estado",
    "investimento_recurso_oneroso_estado",
    "investimento_recurso_nao_oneroso_estado",
    "investimento_total_estado",
]

# Tipo-alvo de cada coluna silver.
TIPO = {c: "INTEGER" for c in INTEIROS}
TIPO.update({c: "VARCHAR" for c in TEXTOS})
TIPO.update({c: "DECIMAL(18,2)" for c in DECIMAIS})

# Regex de validação (sobre o TEXTO da bronze), ver §3 e §4.1 da spec.
RE_DECIMAL = r"^-?[0-9]+(\.[0-9]{1,2})?$"
RE_INTEIRO = r"^-?[0-9]+$"
RE_ANO = r"^[0-9]{4}$"
RE_ID_MUNICIPIO = r"^[0-9]{7}$"

# Lista do que foi assumido além do texto literal da spec (impressa ao final).
ASSUNCOES = [
    (
        "A ordem física das 133 colunas da silver é lida da bronze em tempo de "
        "execução (duckdb_columns.column_index); as listas do Anexo A servem só "
        "para tipar, não para ordenar."
    ),
    (
        "A faixa de INTEGER (B3: estouro de 2,1 bi) é garantida pelo próprio "
        "CAST estrito dentro da transação — se estourar, o CREATE falha e "
        "dispara o ROLLBACK; não há checagem numérica separada antes do CAST."
    ),
    (
        "O detalhamento por grupo do alerta de negativos (despesa*/indice_*/"
        "volume_*) é calculado por prefixo de nome de coluna."
    ),
]


def fmt(n):
    """Inteiro com milhar separado por ponto (sem depender de locale)."""
    return f"{n:,}".replace(",", ".")


def q(nome):
    """Identificador entre aspas duplas para uso seguro no SQL."""
    return '"' + nome.replace('"', '""') + '"'


def erro(con, msg):
    """ROLLBACK defensivo (se houver transação aberta), imprime e sai com 1."""
    try:
        con.execute("ROLLBACK")
    except duckdb.Error:
        pass  # nenhuma transação aberta ainda — tudo bem.
    print(msg)
    con.close()
    sys.exit(1)


def colunas_bronze(con):
    """Nomes das colunas da bronze na ordem física (column_index)."""
    linhas = con.execute(
        """
        SELECT column_name
        FROM duckdb_columns()
        WHERE schema_name = 'bronze'
          AND table_name = 'municipio_agua_esgoto'
        ORDER BY column_index
        """
    ).fetchall()
    return [r[0] for r in linhas]


def validar_constantes(con):
    """Confere tamanhos e cobertura exata das listas do Anexo A vs. bronze."""
    if len(INTEIROS) != 26 or len(DECIMAIS) != 105 or len(TEXTOS) != 2:
        erro(
            con,
            "Constantes inconsistentes com a spec: esperado 26 INTEIROS / "
            f"105 DECIMAIS / 2 TEXTOS; obtido {len(INTEIROS)} / "
            f"{len(DECIMAIS)} / {len(TEXTOS)}.",
        )

    # Conjunto silver -> traduzido para nomes da bronze.
    silver_cols = set(INTEIROS) | set(DECIMAIS) | set(TEXTOS)
    if len(silver_cols) != 133:
        erro(
            con,
            f"Nomes duplicados nas constantes: {len(silver_cols)} nomes "
            "únicos, esperado 133.",
        )
    esperado_bronze = {nome_bronze(c) for c in silver_cols}

    atual = set(colunas_bronze(con))
    if not atual:
        erro(
            con,
            f"Tabela {BRONZE} ausente ou sem colunas. Rode a ingestão antes: "
            "uv run python executar.py",
        )

    faltando = esperado_bronze - atual
    sobrando = atual - esperado_bronze
    if faltando or sobrando:
        erro(
            con,
            "Divergência entre as constantes e as colunas da bronze.\n"
            f"  Nas constantes mas não na bronze: {sorted(faltando)}\n"
            f"  Na bronze mas não nas constantes: {sorted(sobrando)}",
        )


def checar_regex(con, col_bronze, padrao, rotulo):
    """Falha (bloqueante) se algum valor não-nulo violar o regex no texto."""
    col = q(col_bronze)
    sql = f"""
        SELECT count(*) AS n, min({col}) AS exemplo
        FROM {BRONZE}
        WHERE {col} IS NOT NULL AND {col} <> ''
          AND NOT regexp_full_match({col}, '{padrao}')
    """
    n, exemplo = con.execute(sql).fetchone()
    if n:
        erro(
            con,
            f"[BLOQUEANTE] Coluna '{col_bronze}' ({rotulo}): {fmt(n)} "
            f"valor(es) fora do formato esperado. Exemplo: {exemplo!r}",
        )


def validar_sem_vazios(con):
    """B9: string vazia ou só espaços é BLOQUEANTE em qualquer coluna.

    A ingestão garante NULL para célula vazia da fonte; um '' (ou só espaços)
    na bronze indica quebra do contrato da ingestão, não um dado legítimo.
    Por isso NÃO se trata como NULL nem se usa NULLIF: para e mostra a coluna.
    """
    for col in colunas_bronze(con):
        c = q(col)
        # trim(c) = '' cobre '' e strings só com espaços; NULL é permitido.
        n = con.execute(
            f"SELECT count(*) FROM {BRONZE} "
            f"WHERE {c} IS NOT NULL AND trim({c}) = ''"
        ).fetchone()[0]
        if n:
            erro(
                con,
                f"[BLOQUEANTE] Coluna '{col}': {fmt(n)} valor(es) vazio(s) ou "
                "só com espaços. A ingestão deveria gravar NULL para célula "
                "vazia; '' indica quebra do contrato da ingestão.",
            )


def validacoes_antes_do_cast(con):
    """B2/B3(formato)/B4/B5/B6: regex sobre o texto da bronze, sem TRY_CAST."""
    # Decimais: '^-?[0-9]+(\\.[0-9]{1,2})?$' detecta formato inválido E mais de
    # 2 casas decimais (B4) — por isso roda ANTES do CAST, que arredondaria.
    for c in DECIMAIS:
        checar_regex(con, nome_bronze(c), RE_DECIMAL, "DECIMAL(18,2)")

    # Inteiros, exceto `ano` que tem regra própria (4 dígitos exatos).
    for c in INTEIROS:
        if c == "ano":
            continue
        checar_regex(con, nome_bronze(c), RE_INTEIRO, "INTEGER")

    checar_regex(con, "ano", RE_ANO, "ano AAAA")
    checar_regex(con, "id_municipio", RE_ID_MUNICIPIO, "id_municipio 7 dígitos")


def validar_chave(con):
    """B7: chave (ano, id_municipio) nula ou repetida -> para e mostra linhas."""
    nulos = con.execute(
        f"""
        SELECT count(*) FROM {BRONZE}
        WHERE ano IS NULL OR id_municipio IS NULL
        """
    ).fetchone()[0]
    if nulos:
        erro(con, f"[BLOQUEANTE] Chave nula em {fmt(nulos)} linha(s).")

    dups = con.execute(
        f"""
        SELECT ano, id_municipio, count(*) AS n
        FROM {BRONZE}
        GROUP BY ano, id_municipio
        HAVING count(*) > 1
        ORDER BY n DESC, ano, id_municipio
        LIMIT 20
        """
    ).fetchall()
    if dups:
        linhas = "\n".join(
            f"  ano={a} id_municipio={m}: {fmt(n)} ocorrências"
            for a, m, n in dups
        )
        erro(
            con,
            "[BLOQUEANTE] Chave (ano, id_municipio) repetida — a silver não "
            "deduplica (decisão de negócio é da gold):\n" + linhas,
        )


def montar_select(con):
    """SELECT de CAST na ORDEM física da bronze, aplicando a renomeação."""
    partes = []
    for col in colunas_bronze(con):  # ordem física da bronze
        silver_nome = nome_silver(col)
        tipo = TIPO[silver_nome]
        partes.append(f"CAST({q(col)} AS {tipo}) AS {q(silver_nome)}")
    return ",\n    ".join(partes)


def contar_negativos(con):
    """A1: colunas DECIMAL/INTEGER com algum valor negativo na silver."""
    numericas = INTEIROS + DECIMAIS
    with_neg = []
    por_prefixo = {"despesa": 0, "indice": 0, "volume": 0}
    for c in numericas:
        n = con.execute(
            f"SELECT count(*) FROM {SILVER} WHERE {q(c)} < 0"
        ).fetchone()[0]
        if n:
            with_neg.append(c)
            for pref in por_prefixo:
                if c.startswith(pref):
                    por_prefixo[pref] += n
    return with_neg, por_prefixo


def contar_indices_acima_100(con):
    """A3: quantas colunas indice_* têm algum valor > 100."""
    cols = [c for c in DECIMAIS if c.startswith("indice_")]
    acima = 0
    for c in cols:
        n = con.execute(
            f"SELECT count(*) FROM {SILVER} WHERE {q(c)} > 100"
        ).fetchone()[0]
        if n:
            acima += 1
    return acima, len(cols)


def total_celulas_nulas(con, cols):
    """Soma de (total - não-nulos) por coluna = total de células nulas."""
    total = con.execute(f"SELECT count(*) FROM {SILVER}").fetchone()[0]
    expr = " + ".join(f"(count(*) - count({q(c)}))" for c in cols)
    nulas = con.execute(f"SELECT {expr} FROM {SILVER}").fetchone()[0]
    return total, nulas


def imprimir_saida(con):
    """§7: linha de resumo + bloco de Alertas, com contagens lidas do banco."""
    cols = colunas_bronze(con)
    silver_cols = [nome_silver(c) for c in cols]

    entrada = con.execute(f"SELECT count(*) FROM {BRONZE}").fetchone()[0]
    saida, nulas = total_celulas_nulas(con, silver_cols)

    print(
        f"{SILVER} · entrada {fmt(entrada)} · saída {fmt(saida)} · "
        f"{fmt(len(silver_cols))} colunas · {fmt(nulas)} células nulas "
        "(referência da carga atual)"
    )

    # Alertas (A1–A4), recalculados sobre a silver.
    with_neg, por_pref = contar_negativos(con)
    a2 = con.execute(
        f"""
        SELECT count(*) FROM {SILVER}
        WHERE populacao_atendida_agua > populacao_urbana
        """
    ).fetchone()[0]
    a3_cols, _ = contar_indices_acima_100(con)

    tot_2022 = con.execute(
        f"SELECT count(*) FROM {SILVER} WHERE ano = 2022"
    ).fetchone()[0]
    nulos_2022 = con.execute(
        f"""
        SELECT count(*) FROM {SILVER}
        WHERE ano = 2022 AND populacao_urbana_atendida_esgoto IS NULL
        """
    ).fetchone()[0]

    print("\nAlertas:")
    print(
        f"- negativos: {fmt(len(with_neg))} colunas "
        f"(despesa* {fmt(por_pref['despesa'])} · "
        f"indice_* {fmt(por_pref['indice'])} · "
        f"volume {fmt(por_pref['volume'])} · ...)"
    )
    print(
        f"- populacao_atendida_agua > populacao_urbana: {fmt(a2)} linhas"
    )
    print(f"- indice_* acima de 100: {fmt(a3_cols)} colunas")
    nulo_total = "sim" if (tot_2022 and nulos_2022 == tot_2022) else "não"
    print(
        f"- populacao_urbana_atendida_esgoto 100% nula em 2022: {nulo_total} "
        f"({fmt(nulos_2022)}/{fmt(tot_2022)})"
    )


def main():
    con = conectar()

    # B1: pré-condição — a bronze precisa existir.
    existe = con.execute(
        """
        SELECT count(*) FROM duckdb_tables()
        WHERE schema_name = 'bronze' AND table_name = 'municipio_agua_esgoto'
        """
    ).fetchone()[0]
    if not existe:
        erro(
            con,
            f"Tabela {BRONZE} não encontrada. Rode a ingestão primeiro: "
            "uv run python executar.py",
        )

    # Guarda-de-corpo: as listas do Anexo A têm de cobrir a bronze exatamente.
    validar_constantes(con)

    # Verificações bloqueantes ANTES do CAST (sobre o texto da bronze).
    validar_sem_vazios(con)
    validacoes_antes_do_cast(con)
    validar_chave(con)

    # Contagens de referência lidas do banco (nunca fixas no código).
    linhas_bronze = con.execute(f"SELECT count(*) FROM {BRONZE}").fetchone()[0]
    colunas_bronze_n = len(colunas_bronze(con))

    try:
        con.execute("BEGIN TRANSACTION")
        con.execute("CREATE SCHEMA IF NOT EXISTS silver")

        select_sql = montar_select(con)
        con.execute(
            f"CREATE OR REPLACE TABLE {SILVER} AS\n"
            f"  SELECT\n    {select_sql}\n  FROM {BRONZE}"
        )

        # B8: espelho fiel em volume e largura.
        linhas_silver = con.execute(
            f"SELECT count(*) FROM {SILVER}"
        ).fetchone()[0]
        colunas_silver = len(
            con.execute(f"DESCRIBE {SILVER}").fetchall()
        )
        if linhas_silver != linhas_bronze:
            erro(
                con,
                f"[BLOQUEANTE] Divergência de linhas: bronze={linhas_bronze}, "
                f"silver={linhas_silver}.",
            )
        if colunas_silver != colunas_bronze_n:
            erro(
                con,
                f"[BLOQUEANTE] Divergência de colunas: bronze={colunas_bronze_n}, "
                f"silver={colunas_silver}.",
            )

        con.execute("COMMIT")
    except duckdb.Error as exc:
        # CAST estrito que não converte (B2) ou estoura a faixa (B3) cai aqui,
        # mas também qualquer outro erro do DuckDB (p.ex. lock de arquivo). Por
        # isso a mensagem ORIGINAL é sempre incluída — não se presume conversão.
        # O ROLLBACK garante que nenhuma tabela parcial fique no banco.
        erro(
            con,
            "[BLOQUEANTE] Falha ao gravar a silver (pode ser conversão de "
            f"tipo B2/B3 ou outro erro do DuckDB). Mensagem original: {exc}",
        )

    # Saída na tela (sobre a tabela já commitada).
    imprimir_saida(con)

    print("\nAssumido fora da spec:")
    for a in ASSUNCOES:
        print(f"- {a}")

    con.close()


if __name__ == "__main__":
    main()
