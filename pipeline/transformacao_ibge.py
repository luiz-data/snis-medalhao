"""Silver das três fontes IBGE (spec-ibge.md §5) — tipada e validada.

Segue o espírito da silver do SNIS (pipeline/transformacao.py): CAST estrito
(sem TRY_CAST no caminho de gravação), regex de pré-validação ANTES do CAST,
transação única com ROLLBACK e alertas no modelo A1–A4 (aqui IA*/IB*).

Pontos fechados por decisão:
- D10: a coluna de população chama `populacao_total_ibge`.
- D14: `populacao` é a população residente TOTAL (urbana+rural, ref. 1º/jul).
- D15: `pib_municipio` é **BIGINT em Mil Reais** — nunca DECIMAL; a conversão
  para reais é só na gold.
- D13: população nula permitida (IA7/IB10); linha sem id excluída (IA6/IB9).
- D11: símbolo de ausência do SIDRA vira NULL (IA8); texto inválido é IB11.
- D12: a DTB tem 5.571 linhas.
"""

import sys

import duckdb

from pipeline.db import conectar
from pipeline.ibge import JANELA_FIM, JANELA_INICIO, MAPA_UF, case_sql

# --- Sanidades de referência (spec-ibge.md §5.1/§5.2, critérios P7 e B8) -----
SP = "3550308"
SP_POP_2021 = 12_396_372  # §5.1 / §9.1 P7
SP_PIB_2021 = 828_980_747  # Mil Reais; §5.2 / §9.2 B8

# Símbolos de ausência do SIDRA (spec-ibge.md §5.2, D11).
SIMBOLOS_SIDRA = ("-", "..", "...", "X")

# Máximo de PIBs negativos aceitos como fato real (IA9, D17). Acima disto, IA9
# vira BLOQUEANTE — proteção contra erro de leitura ou de sinal (spec-ibge.md
# §5.2/§9.2). Medido na extração 2026-11-08: 1 negativo (Guamaré/RN, 2012).
PIB_NEGATIVOS_MAX = 5


def fmt(n):
    return f"{n:,}".replace(",", ".")


def q(nome):
    return '"' + nome.replace('"', '""') + '"'


def erro(con, msg):
    """ROLLBACK defensivo, imprime e sai com 1 (igual à silver do SNIS)."""
    try:
        con.execute("ROLLBACK")
    except duckdb.Error:
        pass
    print(msg)
    con.close()
    sys.exit(1)


def _bronze_existe(con, tabela):
    schema, nome = tabela.split(".")
    return (
        con.execute(
            "SELECT count(*) FROM duckdb_tables() "
            "WHERE schema_name = ? AND table_name = ?",
            [schema, nome],
        ).fetchone()[0]
        > 0
    )


def _um(con, sql):
    return con.execute(sql).fetchone()[0]


# ===========================================================================
# 5.1 — silver.ibge_populacao_municipio
# ===========================================================================


def silver_populacao(con):
    bronze = "bronze.ibge_populacao_municipio"
    silver = "silver.ibge_populacao_municipio"
    if not _bronze_existe(con, bronze):  # IB1
        erro(con, f"[BLOQUEANTE] Tabela {bronze} ausente. Rode a bronze antes.")

    # IA6/IB9: linha sem id_municipio. Dentro da janela é bloqueante.
    sem_id = f"FROM {bronze} WHERE (id_municipio IS NULL OR trim(id_municipio) = '')"
    na_janela = _um(
        con,
        f"SELECT count(*) {sem_id} "
        f"AND CAST(ano AS INTEGER) BETWEEN {JANELA_INICIO} AND {JANELA_FIM}",
    )
    if na_janela:  # IB9
        erro(
            con,
            f"[BLOQUEANTE] IB9: {fmt(na_janela)} linha(s) sem id_municipio "
            f"dentro de {JANELA_INICIO}–{JANELA_FIM}.",
        )
    excluidas = con.execute(f"SELECT ano, populacao {sem_id} ORDER BY ano").fetchall()

    # Pré-validação (regex) sobre as linhas que FICAM (já sem id vazio).
    validas = (
        f"FROM {bronze} WHERE id_municipio IS NOT NULL AND trim(id_municipio) <> ''"
    )
    mal_ano = _um(
        con, f"SELECT count(*) {validas} AND NOT regexp_full_match(ano, '^[0-9]{{4}}$')"
    )
    mal_id = _um(
        con,
        f"SELECT count(*) {validas} AND NOT regexp_full_match(id_municipio, '^[0-9]{{7}}$')",
    )
    mal_pop = _um(
        con,
        f"SELECT count(*) {validas} AND populacao IS NOT NULL "
        f"AND trim(populacao) <> '' AND NOT regexp_full_match(populacao, '^[0-9]+$')",
    )
    if mal_ano or mal_id or mal_pop:  # IB2
        erro(
            con,
            f"[BLOQUEANTE] IB2: formato inválido — ano={mal_ano}, "
            f"id_municipio={mal_id}, populacao={mal_pop}.",
        )

    # IA7/IB10: população nula. Qualquer nula em 2010–2021 é bloqueante.
    nula_janela = _um(
        con,
        f"SELECT count(*) {validas} AND (populacao IS NULL OR trim(populacao) = '') "
        f"AND CAST(ano AS INTEGER) BETWEEN {JANELA_INICIO} AND {JANELA_FIM}",
    )
    if nula_janela:  # IB10
        erro(
            con,
            f"[BLOQUEANTE] IB10: {fmt(nula_janela)} população(ões) nula(s) em "
            f"{JANELA_INICIO}–{JANELA_FIM}.",
        )
    nulas_por_ano = con.execute(
        f"SELECT ano, count(*) {validas} "
        f"AND (populacao IS NULL OR trim(populacao) = '') GROUP BY ano ORDER BY ano"
    ).fetchall()

    try:
        con.execute("BEGIN TRANSACTION")
        con.execute("CREATE SCHEMA IF NOT EXISTS silver")
        con.execute(
            f"""
            CREATE OR REPLACE TABLE {silver} AS
            SELECT
                CAST(ano AS INTEGER) AS ano,
                CAST(id_municipio AS VARCHAR) AS id_municipio,
                CAST(NULLIF(trim(populacao), '') AS INTEGER) AS populacao_total_ibge
            {validas}
            """
        )
        # IB6: chave única.
        dup = _um(
            con,
            f"SELECT count(*) FROM (SELECT 1 FROM {silver} "
            f"GROUP BY ano, id_municipio HAVING count(*) > 1)",
        )
        if dup:
            erro(con, f"[BLOQUEANTE] IB6: {fmt(dup)} chave(s) (ano, id) repetida(s).")
        con.execute("COMMIT")
    except duckdb.Error as exc:
        erro(con, f"[BLOQUEANTE] Falha ao gravar {silver}: {exc}")

    # IA5: sanidade de série de São Paulo em 2021 (não bloqueante).
    sp = _um(
        con,
        f"SELECT populacao_total_ibge FROM {silver} "
        f"WHERE id_municipio = '{SP}' AND ano = 2021",
    )
    linhas = _um(con, f"SELECT count(*) FROM {silver}")
    print(f"{silver} · {fmt(linhas)} linhas")
    print(
        f"  IA6 linha(s) sem id excluída(s): {len(excluidas)} "
        + (f"({excluidas})" if excluidas else "")
    )
    print(f"  IA7 população nula por ano: {dict(nulas_por_ano) or 'nenhuma'}")
    print(
        f"  IA5 SP 2021 = {fmt(sp) if sp is not None else '—'} "
        f"(ref. {fmt(SP_POP_2021)}; dif. "
        f"{fmt(sp - SP_POP_2021) if sp is not None else '—'})"
    )


# ===========================================================================
# 5.2 — silver.ibge_pib_municipio
# ===========================================================================


def silver_pib(con):
    bronze = "bronze.ibge_pib_municipio"
    silver = "silver.ibge_pib_municipio"
    if not _bronze_existe(con, bronze):  # IB1
        erro(con, f"[BLOQUEANTE] Tabela {bronze} ausente. Rode a bronze antes.")

    simbolos = ", ".join(f"'{s}'" for s in SIMBOLOS_SIDRA)

    # Pré-validação de formato (regex), chave e valor.
    mal_ano = _um(
        con,
        f"SELECT count(*) FROM {bronze} WHERE NOT regexp_full_match(ano, '^[0-9]{{4}}$')",
    )
    mal_id = _um(
        con,
        f"SELECT count(*) FROM {bronze} WHERE NOT regexp_full_match(id_municipio, '^[0-9]{{7}}$')",
    )
    if mal_ano or mal_id:  # IB2
        erro(con, f"[BLOQUEANTE] IB2: ano inválido={mal_ano}, id inválido={mal_id}.")

    # IB11: valor que não é inteiro NEM símbolo de ausência conhecido.
    # Observação: o PIB municipal PODE ser negativo (componente de impostos
    # líquidos de subsídios negativo); por isso o inteiro aceita sinal (^-?...).
    # É fato real do SIDRA, não erro — ver alerta IA9 abaixo. (A spec-ibge.md
    # §5.2/§9.2 assumia pib ≥ 0; ponto sinalizado para decisão.)
    invalidos = con.execute(
        f"""
        SELECT DISTINCT valor FROM {bronze}
        WHERE NOT regexp_full_match(valor, '^-?[0-9]+$')
          AND valor NOT IN ({simbolos})
        LIMIT 10
        """
    ).fetchall()
    if invalidos:  # IB11
        erro(
            con,
            f"[BLOQUEANTE] IB11: valor(es) não inteiro nem símbolo conhecido "
            f"{SIMBOLOS_SIDRA}: {[v[0] for v in invalidos]}",
        )

    # IA8: símbolos de ausência por ano (viram NULL).
    simbolo_por_ano = con.execute(
        f"SELECT ano, count(*) FROM {bronze} WHERE valor IN ({simbolos}) "
        f"GROUP BY ano ORDER BY ano"
    ).fetchall()
    # IA9 (fato real, não bloqueante até PIB_NEGATIVOS_MAX): PIB negativo
    # preservado. Acima do teto vira BLOQUEANTE (D17).
    negativos = con.execute(
        f"SELECT id_municipio, ano, valor FROM {bronze} "
        f"WHERE regexp_full_match(valor, '^-[0-9]+$') ORDER BY ano, id_municipio"
    ).fetchall()
    if len(negativos) > PIB_NEGATIVOS_MAX:  # IA9 → bloqueante
        erro(
            con,
            f"[BLOQUEANTE] IA9: {len(negativos)} PIBs negativos (> "
            f"PIB_NEGATIVOS_MAX={PIB_NEGATIVOS_MAX}). Provável erro de leitura "
            f"ou de sinal. Exemplos: {[(i, a, v) for i, a, v in negativos[:10]]}",
        )

    try:
        con.execute("BEGIN TRANSACTION")
        con.execute("CREATE SCHEMA IF NOT EXISTS silver")
        # D15: BIGINT em Mil Reais. A silver NÃO converte para reais (gold).
        con.execute(
            f"""
            CREATE OR REPLACE TABLE {silver} AS
            SELECT
                CAST(ano AS INTEGER) AS ano,
                CAST(id_municipio AS VARCHAR) AS id_municipio,
                CASE WHEN valor IN ({simbolos}) THEN NULL
                     ELSE CAST(valor AS BIGINT) END AS pib_municipio
            FROM {bronze}
            """
        )
        dup = _um(
            con,
            f"SELECT count(*) FROM (SELECT 1 FROM {silver} "
            f"GROUP BY ano, id_municipio HAVING count(*) > 1)",
        )
        if dup:
            erro(con, f"[BLOQUEANTE] IB6: {fmt(dup)} chave(s) (ano, id) repetida(s).")
        nulos_chave = _um(
            con,
            f"SELECT count(*) FROM {silver} WHERE ano IS NULL OR id_municipio IS NULL",
        )
        if nulos_chave:
            erro(con, f"[BLOQUEANTE] IB6: {fmt(nulos_chave)} chave(s) nula(s).")
        con.execute("COMMIT")
    except duckdb.Error as exc:
        erro(con, f"[BLOQUEANTE] Falha ao gravar {silver}: {exc}")

    # B8: sanidade de unidade (Mil Reais) — São Paulo 2021.
    sp = _um(
        con,
        f"SELECT pib_municipio FROM {silver} WHERE id_municipio = '{SP}' AND ano = 2021",
    )
    linhas = _um(con, f"SELECT count(*) FROM {silver}")
    print(f"{silver} · {fmt(linhas)} linhas · pib_municipio BIGINT em Mil Reais (D15)")
    print(f"  IA8 símbolo de ausência por ano: {dict(simbolo_por_ano) or 'nenhum'}")
    print(
        f"  IA9 PIB negativo (preservado, fato real; teto {PIB_NEGATIVOS_MAX}): "
        f"{len(negativos)} " + (f"({negativos})" if negativos else "")
    )
    ok = "ok" if sp == SP_PIB_2021 else "DIVERGE"
    print(f"  B8 SP 2021 = {fmt(sp) if sp is not None else '—'} Mil Reais ({ok})")


# ===========================================================================
# 5.3 — silver.ibge_dtb_municipio
# ===========================================================================


def silver_dtb(con):
    bronze = "bronze.ibge_dtb_municipio"
    silver = "silver.ibge_dtb_municipio"
    if not _bronze_existe(con, bronze):  # IB1
        erro(con, f"[BLOQUEANTE] Tabela {bronze} ausente. Rode a bronze antes.")

    cod_uf = q("UF")
    id_col = q("Código Município Completo")

    # Pré-validação: id 7 dígitos, cod_uf 2 dígitos e presente no mapa das 27 UFs.
    mal_id = _um(
        con,
        f"SELECT count(*) FROM {bronze} WHERE NOT regexp_full_match({id_col}, '^[0-9]{{7}}$')",
    )
    mal_uf = _um(
        con,
        f"SELECT count(*) FROM {bronze} WHERE NOT regexp_full_match({cod_uf}, '^[0-9]{{2}}$')",
    )
    codigos = ", ".join(f"'{c}'" for c in MAPA_UF)
    fora_mapa = _um(
        con, f"SELECT count(*) FROM {bronze} WHERE {cod_uf} NOT IN ({codigos})"
    )
    if mal_id or mal_uf or fora_mapa:  # IB2
        erro(
            con,
            f"[BLOQUEANTE] IB2: id inválido={mal_id}, cod_uf inválido={mal_uf}, "
            f"cod_uf fora do mapa das 27 UFs={fora_mapa}.",
        )

    try:
        con.execute("BEGIN TRANSACTION")
        con.execute("CREATE SCHEMA IF NOT EXISTS silver")
        con.execute(
            f"""
            CREATE OR REPLACE TABLE {silver} AS
            SELECT
                CAST({id_col} AS VARCHAR) AS id_municipio,
                CAST({cod_uf} AS VARCHAR) AS cod_uf,
                {case_sql(cod_uf, 0)} AS sigla_uf,
                CAST({q("Nome_UF")} AS VARCHAR) AS nome_uf,
                CAST({q("Nome_Município")} AS VARCHAR) AS nome_municipio,
                CAST({q("Região Geográfica Intermediária")} AS VARCHAR) AS cod_regiao_intermediaria,
                CAST({q("Nome Região Geográfica Intermediária")} AS VARCHAR) AS nome_regiao_intermediaria,
                CAST({q("Região Geográfica Imediata")} AS VARCHAR) AS cod_regiao_imediata,
                CAST({q("Nome Região Geográfica Imediata")} AS VARCHAR) AS nome_regiao_imediata,
                {case_sql(cod_uf, 1)} AS nome_regiao
            FROM {bronze}
            """
        )
        dup = _um(
            con,
            f"SELECT count(*) FROM (SELECT 1 FROM {silver} "
            f"GROUP BY id_municipio HAVING count(*) > 1)",
        )
        if dup:  # IB6
            erro(con, f"[BLOQUEANTE] IB6: {fmt(dup)} id_municipio repetido(s) na DTB.")
        con.execute("COMMIT")
    except duckdb.Error as exc:
        erro(con, f"[BLOQUEANTE] Falha ao gravar {silver}: {exc}")

    # IA3: prefixo do id divergente do cod_uf (não bloqueante).
    ia3 = _um(
        con, f"SELECT count(*) FROM {silver} WHERE left(id_municipio, 2) <> cod_uf"
    )
    linhas = _um(con, f"SELECT count(*) FROM {silver}")
    ufs = _um(con, f"SELECT count(DISTINCT sigla_uf) FROM {silver}")
    print(f"{silver} · {fmt(linhas)} linhas · {ufs} UFs distintas")
    print(f"  IA3 prefixo id ≠ cod_uf: {fmt(ia3)} linha(s)")


def main():
    print("IBGE silver:")
    con = conectar()
    silver_populacao(con)
    silver_pib(con)
    silver_dtb(con)
    con.close()


if __name__ == "__main__":
    main()
