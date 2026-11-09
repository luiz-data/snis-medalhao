"""Testes da silver IBGE e do teste de cobertura (spec-ibge.md §5, §7, §9).

Cobre:
- critérios de aceite P1–P9 (POP), B1–B8 (PIB), D1–D6 (DTB);
- mapa estático de UF: completude (27 entradas, todos os códigos da DTB
  cobertos) e cruzamento `sigla_uf` derivada (DTB) × `sigla_uf` do SNIS;
- critérios de cobertura D7 e D12, inclusive os casos BLOQUEANTES, em cópias
  temporárias do banco.

As expectativas numéricas ficam SÓ aqui; as listas/mapa vêm de pipeline.*.
"""

import shutil

import duckdb
import pytest

import pipeline.cobertura as cob
import pipeline.db as db_mod
import pipeline.ingestao as ing_snis
import pipeline.ingestao_ibge as ing_ibge
import pipeline.transformacao as transf_snis
import pipeline.transformacao_ibge as transf_ibge
from pipeline.ibge import JANELA_FIM, JANELA_INICIO, MACRORREGIOES, MAPA_UF

# --- Expectativas numéricas (spec-ibge.md §9) -------------------------------
POP_LINHAS = 191_098  # P1: 191.099 − 1 (linha de id vazio excluída, IA6)
PIB_LINHAS = 66_840  # B1
DTB_LINHAS = 5_571  # D1 (D12)
SP = "3550308"
SP_POP_2021 = 12_396_372  # P7
SP_PIB_2021 = 828_980_747  # B8 (Mil Reais)
N_UF = 27
N_MACRORREGIOES = 5

POP = "silver.ibge_populacao_municipio"
PIB = "silver.ibge_pib_municipio"
DTB = "silver.ibge_dtb_municipio"
SNIS = "silver.municipio_agua_esgoto"


def _ro(banco):
    return duckdb.connect(str(banco), read_only=True)


@pytest.fixture(scope="module")
def ibge_db(tmp_path_factory):
    """Pipeline completo (SNIS + IBGE) uma vez; devolve o CAMINHO do banco."""
    banco = tmp_path_factory.mktemp("db") / "snis.duckdb"
    original = db_mod.CAMINHO_BANCO
    db_mod.CAMINHO_BANCO = banco
    try:
        ing_snis.main()
        transf_snis.main()
        ing_ibge.main()
        transf_ibge.main()
        yield banco
    finally:
        db_mod.CAMINHO_BANCO = original


# ===========================================================================
# POP — critérios P1–P9
# ===========================================================================


def test_pop_linhas_e_tipos(ibge_db):
    con = _ro(ibge_db)
    try:
        assert con.execute(f"SELECT count(*) FROM {POP}").fetchone()[0] == POP_LINHAS
        tipos = {c[0]: c[1] for c in con.execute(f"DESCRIBE {POP}").fetchall()}
    finally:
        con.close()
    assert tipos == {
        "ano": "INTEGER",
        "id_municipio": "VARCHAR",
        "populacao_total_ibge": "INTEGER",
    }


def test_pop_chave_unica_e_id(ibge_db):
    con = _ro(ibge_db)
    try:
        dup = con.execute(
            f"SELECT count(*) FROM (SELECT 1 FROM {POP} "
            "GROUP BY ano, id_municipio HAVING count(*) > 1)"
        ).fetchone()[0]
        nulos = con.execute(
            f"SELECT count(*) FROM {POP} WHERE id_municipio IS NULL"
        ).fetchone()[0]
        mal = con.execute(
            f"SELECT count(*) FROM {POP} "
            "WHERE NOT regexp_full_match(id_municipio, '^[0-9]{7}$')"
        ).fetchone()[0]
    finally:
        con.close()
    assert dup == 0 and nulos == 0 and mal == 0  # P3, P4


def test_pop_nulos_conhecidos_e_sanidade(ibge_db):
    con = _ro(ibge_db)
    try:
        por_ano = dict(
            con.execute(
                f"SELECT ano, count(*) FROM {POP} "
                "WHERE populacao_total_ibge IS NULL GROUP BY ano"
            ).fetchall()
        )
        na_janela = con.execute(
            f"SELECT count(*) FROM {POP} WHERE populacao_total_ibge IS NULL "
            f"AND ano BETWEEN {JANELA_INICIO} AND {JANELA_FIM}"
        ).fetchone()[0]
        sp = con.execute(
            f"SELECT populacao_total_ibge FROM {POP} "
            f"WHERE id_municipio = '{SP}' AND ano = 2021"
        ).fetchone()[0]
    finally:
        con.close()
    assert por_ano == {1996: 533, 2009: 1}  # P8
    assert na_janela == 0
    assert sp == SP_POP_2021  # P7


# ===========================================================================
# PIB — critérios B1–B8
# ===========================================================================


def test_pib_linhas_tipos_sanidade(ibge_db):
    con = _ro(ibge_db)
    try:
        assert con.execute(f"SELECT count(*) FROM {PIB}").fetchone()[0] == PIB_LINHAS
        tipo = {c[0]: c[1] for c in con.execute(f"DESCRIBE {PIB}").fetchall()}[
            "pib_municipio"
        ]
        sp = con.execute(
            f"SELECT pib_municipio FROM {PIB} WHERE id_municipio = '{SP}' AND ano = 2021"
        ).fetchone()[0]
    finally:
        con.close()
    assert tipo == "BIGINT"  # B2, D15
    assert sp == SP_PIB_2021  # B8


def test_pib_simbolos_viram_nulo(ibge_db):
    con = _ro(ibge_db)
    try:
        por_ano = dict(
            con.execute(
                f"SELECT ano, count(*) FROM {PIB} WHERE pib_municipio IS NULL "
                "GROUP BY ano"
            ).fetchall()
        )
    finally:
        con.close()
    # B7: só os 5 municípios novos em 2010, 2011 e 2012 (símbolo '...').
    assert por_ano == {2010: 5, 2011: 5, 2012: 5}


def test_pib_negativo_preservado(ibge_db):
    """B9/IA9 (D17): PIB negativo é preservado; 1 caso (Guamaré/RN, 2012)."""
    con = _ro(ibge_db)
    try:
        negativos = con.execute(
            f"SELECT id_municipio, ano, pib_municipio FROM {PIB} "
            "WHERE pib_municipio < 0 ORDER BY ano, id_municipio"
        ).fetchall()
    finally:
        con.close()
    assert negativos == [("2404507", 2012, -19046)]
    assert len(negativos) <= transf_ibge.PIB_NEGATIVOS_MAX  # não bloqueia


def test_pib_negativos_acima_do_teto_bloqueia(ibge_db, tmp_path):
    """IA9 (D17): mais de PIB_NEGATIVOS_MAX negativos → silver_pib bloqueia.

    Numa cópia do banco, inverte o sinal de (teto + 1) valores do PIB na bronze
    e reroda silver_pib: deve sair com código 1 (ROLLBACK) e deixar a silver do
    PIB sem alteração/ausente.
    """
    destino = _copia(ibge_db, tmp_path / "c.duckdb")
    con = duckdb.connect(str(destino))
    bronze_pib = "bronze.ibge_pib_municipio"
    try:
        con.execute(f"DROP TABLE IF EXISTS {PIB}")
        # Torna negativos (teto + 1) valores inteiros positivos distintos.
        n = transf_ibge.PIB_NEGATIVOS_MAX + 1
        con.execute(
            f"""
            UPDATE {bronze_pib} SET valor = '-' || valor
            WHERE (id_municipio, ano) IN (
                SELECT id_municipio, ano FROM {bronze_pib}
                WHERE regexp_full_match(valor, '^[1-9][0-9]*$')
                ORDER BY ano, id_municipio LIMIT {n}
            )
            """
        )
        with pytest.raises(SystemExit) as exc:
            transf_ibge.silver_pib(con)
        assert exc.value.code == 1
    finally:
        con.close()
    # A silver do PIB não pode ter sido criada (ROLLBACK).
    con2 = _ro(destino)
    try:
        existe = con2.execute(
            "SELECT count(*) FROM duckdb_tables() "
            "WHERE schema_name = 'silver' AND table_name = 'ibge_pib_municipio'"
        ).fetchone()[0]
    finally:
        con2.close()
    assert existe == 0


# ===========================================================================
# DTB — critérios D1–D5
# ===========================================================================


def test_dtb_linhas_chave_ufs(ibge_db):
    con = _ro(ibge_db)
    try:
        assert con.execute(f"SELECT count(*) FROM {DTB}").fetchone()[0] == DTB_LINHAS
        dup = con.execute(
            f"SELECT count(*) FROM (SELECT 1 FROM {DTB} "
            "GROUP BY id_municipio HAVING count(*) > 1)"
        ).fetchone()[0]
        ufs = con.execute(f"SELECT count(DISTINCT sigla_uf) FROM {DTB}").fetchone()[0]
        regioes = {
            r[0]
            for r in con.execute(f"SELECT DISTINCT nome_regiao FROM {DTB}").fetchall()
        }
    finally:
        con.close()
    assert dup == 0  # D2
    assert ufs == N_UF  # D4
    assert regioes == set(MACRORREGIOES)  # D5


def test_dtb_municipio_extra_presente(ibge_db):
    """D12: o 5.571º é Boa Esperança do Norte/MT (5101837)."""
    con = _ro(ibge_db)
    try:
        n = con.execute(
            f"SELECT count(*) FROM {DTB} WHERE id_municipio = '5101837'"
        ).fetchone()[0]
    finally:
        con.close()
    assert n == 1


# ===========================================================================
# Mapa estático de UF — completude e cruzamento com o SNIS
# ===========================================================================


def test_mapa_uf_completude():
    """27 entradas, siglas únicas, macrorregião coerente com o 1º dígito."""
    assert len(MAPA_UF) == N_UF
    siglas = [s for s, _ in MAPA_UF.values()]
    assert len(set(siglas)) == N_UF
    assert {r for _, r in MAPA_UF.values()} == set(MACRORREGIOES)
    primeiro = {
        "1": "Norte",
        "2": "Nordeste",
        "3": "Sudeste",
        "4": "Sul",
        "5": "Centro-Oeste",
    }
    for cod, (_sigla, regiao) in MAPA_UF.items():
        assert primeiro[cod[0]] == regiao


def test_mapa_uf_cobre_todos_os_codigos_da_dtb(ibge_db):
    """Todo cod_uf presente na DTB tem entrada no mapa estático."""
    con = _ro(ibge_db)
    try:
        codigos_dtb = {
            r[0] for r in con.execute(f"SELECT DISTINCT cod_uf FROM {DTB}").fetchall()
        }
    finally:
        con.close()
    assert codigos_dtb <= set(MAPA_UF)
    assert len(codigos_dtb) == N_UF


def test_sigla_derivada_bate_com_snis(ibge_db):
    """Para todo município em ambas as silvers, a sigla_uf derivada da DTB deve
    ser igual à sigla_uf do SNIS. Qualquer divergência falha e lista os casos."""
    con = _ro(ibge_db)
    try:
        divergencias = con.execute(
            f"""
            SELECT DISTINCT s.id_municipio, s.sigla_uf AS snis, d.sigla_uf AS dtb
            FROM {SNIS} s
            JOIN {DTB} d USING (id_municipio)
            WHERE s.sigla_uf <> d.sigla_uf
            ORDER BY s.id_municipio
            """
        ).fetchall()
    finally:
        con.close()
    assert divergencias == [], f"sigla_uf divergente SNIS×DTB: {divergencias}"


# ===========================================================================
# Cobertura — D7 e D12, incluindo os casos BLOQUEANTES (cópias temporárias)
# ===========================================================================


def _copia(banco_origem, destino):
    shutil.copy(banco_origem, destino)
    return destino


def test_cobertura_ok_no_banco_real(ibge_db):
    """Com o banco completo: DTB sem divergência e cobertura 100% (não bloqueia)."""
    con = _ro(ibge_db)
    try:
        div, bloqueia_dtb = cob.cobertura_dtb(con)
        bloqueia_pop = cob.cobertura_por_ano(con, "POP", POP)
        bloqueia_pib = cob.cobertura_por_ano(con, "PIB", PIB)
    finally:
        con.close()
    assert div == 0 and not bloqueia_dtb
    assert not bloqueia_pop and not bloqueia_pib


def test_cobertura_dtb_bloqueante(ibge_db, tmp_path):
    """D12: apagar da DTB mais que o limite de municípios do SNIS → bloqueia."""
    destino = _copia(ibge_db, tmp_path / "c.duckdb")
    con = duckdb.connect(str(destino))
    try:
        # Remove da DTB (DTB_MAX_DIVERGENCIAS + 5) ids que existem no SNIS.
        n = cob.DTB_MAX_DIVERGENCIAS + 5
        con.execute(
            f"""
            DELETE FROM {DTB} WHERE id_municipio IN (
                SELECT DISTINCT id_municipio FROM {SNIS} LIMIT {n}
            )
            """
        )
        div, bloqueia = cob.cobertura_dtb(con)
    finally:
        con.close()
    assert div >= n and bloqueia


def test_cobertura_pop_bloqueante(ibge_db, tmp_path):
    """D7: derrubar a cobertura de um ano abaixo de 95% → bloqueia."""
    destino = _copia(ibge_db, tmp_path / "c.duckdb")
    con = duckdb.connect(str(destino))
    try:
        # Apaga 20% dos municípios de 2015 da POP (cobertura cai para ~80%).
        con.execute(
            f"""
            DELETE FROM {POP} WHERE ano = 2015 AND id_municipio IN (
                SELECT id_municipio FROM {POP} WHERE ano = 2015
                USING SAMPLE 20 PERCENT (bernoulli, 42)
            )
            """
        )
        bloqueia = cob.cobertura_por_ano(con, "POP", POP)
    finally:
        con.close()
    assert bloqueia


def test_cobertura_pop_alerta_nao_bloqueia(ibge_db, tmp_path):
    """D7: queda pequena (entre 95% e 99%) é alerta, não bloqueia."""
    destino = _copia(ibge_db, tmp_path / "c.duckdb")
    con = duckdb.connect(str(destino))
    try:
        # Remove ~3% dos municípios de 2015 (cobertura ~97%: alerta, sem bloquear).
        con.execute(
            f"""
            DELETE FROM {POP} WHERE ano = 2015 AND id_municipio IN (
                SELECT id_municipio FROM {POP} WHERE ano = 2015
                USING SAMPLE 3 PERCENT (bernoulli, 7)
            )
            """
        )
        bloqueia = cob.cobertura_por_ano(con, "POP", POP)
    finally:
        con.close()
    assert not bloqueia
