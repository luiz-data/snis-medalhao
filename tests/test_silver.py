"""Testes da camada silver — spec-transformacao.md.

Cobre os "Critérios de aceite" (1–12) e os bloqueantes (B2/B4/B9/B7/B1) da
spec. Segue o estilo de tests/test_bronze.py.

Estratégia de isolamento (nunca toca o snis.duckdb real):

- Um banco temporário por MÓDULO: `ingestao.main()` + `transformacao.main()`
  rodam UMA vez (fixture `silver_db`), via monkeypatch de
  `pipeline.db.CAMINHO_BANCO`. A fixture entrega só o CAMINHO do banco; cada
  teste abre sua própria conexão read-only e a fecha (duckdb não mistura
  conexões read-only e read-write no mesmo processo/arquivo).

- Testes de bloqueio trabalham em CÓPIAS do arquivo do banco (uma por teste,
  para não repetir a ingestão). Em cada cópia derruba-se a silver existente,
  corrompe-se a bronze e roda-se a transformação, que deve sair com código 1
  (ROLLBACK) e deixar o banco SEM a tabela silver.

As expectativas numéricas (119256, 133, 5549, 47934, 15460, 10890, 1,
5659843, 5425) vêm da spec e de docs/contagens.md e ficam SÓ aqui, nunca em
pipeline/. As listas das 133 colunas e o mapa de nomes vêm de
pipeline.transformacao (INTEIROS/DECIMAIS/TEXTOS/nome_bronze), não são
copiados.
"""

import shutil

import duckdb
import pytest

import pipeline.db as db_mod
import pipeline.ingestao as ingestao_mod
import pipeline.transformacao as transf_mod

# --- Expectativas numéricas (spec + docs/contagens.md) ----------------------

N_LINHAS = 119_256
N_COLUNAS = 133
N_MUNICIPIOS = 5_549
N_INTEIROS, N_TEXTOS, N_DECIMAIS = 26, 2, 105
TOTAL_CELULAS_NULAS = 5_659_843
POP_ATENDIDA_MAIOR_URBANA = 47_934  # A2
LINHAS_2022 = 5_425  # A4: 100% nula em populacao_urbana_atendida_esgoto
N_COLUNAS_NEGATIVAS = 43  # A1
NEG_DESPESA, NEG_INDICE, NEG_VOLUME = 15_460, 10_890, 1  # A1 por prefixo

# Nomes das colunas por tipo (fonte: pipeline.transformacao, não copiados).
INTEIROS = transf_mod.INTEIROS
TEXTOS = transf_mod.TEXTOS
DECIMAIS = transf_mod.DECIMAIS
TODAS = INTEIROS + TEXTOS + DECIMAIS
q = transf_mod.q
nome_bronze = transf_mod.nome_bronze

BRONZE = "bronze.municipio_agua_esgoto"
SILVER = "silver.municipio_agua_esgoto"


# --- Infra ------------------------------------------------------------------


def _ro(banco):
    """Conexão read-only ao banco temporário."""
    return duckdb.connect(str(banco), read_only=True)


@pytest.fixture(scope="module")
def silver_db(tmp_path_factory):
    """Roda ingestão + transformação UMA vez e devolve o CAMINHO do banco."""
    banco = tmp_path_factory.mktemp("db") / "snis.duckdb"
    original = db_mod.CAMINHO_BANCO
    db_mod.CAMINHO_BANCO = banco
    try:
        ingestao_mod.main()
        transf_mod.main()
        yield banco
    finally:
        db_mod.CAMINHO_BANCO = original


def _silver_ausente(banco):
    """True se a cópia não tem nenhuma tabela no schema silver (ROLLBACK ok)."""
    con = _ro(banco)
    try:
        n = con.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE schema_name = 'silver'"
        ).fetchone()[0]
    finally:
        con.close()
    return n == 0


def _preparar_copia(banco_origem, destino, corrupcao_sql):
    """Copia o banco, derruba a silver e aplica a corrupção na bronze."""
    shutil.copy(banco_origem, destino)
    con = duckdb.connect(str(destino))
    try:
        con.execute(f"DROP TABLE IF EXISTS {SILVER}")
        con.execute(corrupcao_sql)
    finally:
        con.close()


def _primeira_coluna(sql_set):
    """UPDATE que altera a linha de menor rowid (uma única linha)."""
    return (
        f"UPDATE {BRONZE} SET {sql_set} WHERE rowid = (SELECT min(rowid) FROM {BRONZE})"
    )


# ---- 1. Linhas: 119.256 na bronze e na silver ----


def test_linhas(silver_db):
    con = _ro(silver_db)
    try:
        bronze = con.execute(f"SELECT count(*) FROM {BRONZE}").fetchone()[0]
        silver = con.execute(f"SELECT count(*) FROM {SILVER}").fetchone()[0]
    finally:
        con.close()
    assert bronze == N_LINHAS
    assert silver == N_LINHAS


# ---- 2. Colunas: 133 ----


def test_colunas(silver_db):
    con = _ro(silver_db)
    try:
        colunas = con.execute(f"DESCRIBE {SILVER}").fetchall()
    finally:
        con.close()
    assert len(colunas) == N_COLUNAS


# ---- 3. Tipos: 26 INTEGER / 2 VARCHAR / 105 DECIMAL(18,2) ----


def test_tipos(silver_db):
    con = _ro(silver_db)
    try:
        linhas = con.execute(
            "SELECT data_type, count(*) FROM duckdb_columns() "
            "WHERE schema_name = 'silver' "
            "AND table_name = 'municipio_agua_esgoto' "
            "GROUP BY data_type"
        ).fetchall()
    finally:
        con.close()
    tipos = dict(linhas)
    assert tipos.get("INTEGER") == N_INTEIROS
    assert tipos.get("VARCHAR") == N_TEXTOS
    assert tipos.get("DECIMAL(18,2)") == N_DECIMAIS


# ---- 4. Nulos por coluna iguais (e total 5.659.843) ----


def test_nulos_por_coluna(silver_db):
    con = _ro(silver_db)
    try:
        expr_bronze = ", ".join(f"count(*) - count({q(nome_bronze(c))})" for c in TODAS)
        expr_silver = ", ".join(f"count(*) - count({q(c)})" for c in TODAS)
        nulos_bronze = con.execute(f"SELECT {expr_bronze} FROM {BRONZE}").fetchone()
        nulos_silver = con.execute(f"SELECT {expr_silver} FROM {SILVER}").fetchone()
    finally:
        con.close()
    assert list(nulos_bronze) == list(nulos_silver)
    assert sum(nulos_silver) == TOTAL_CELULAS_NULAS


# ---- 5. Somas das 105 DECIMAL iguais (silver vs CAST bronze AS DECIMAL) ----


def test_somas_decimais(silver_db):
    con = _ro(silver_db)
    try:
        expr_bronze = ", ".join(
            f"sum(CAST({q(nome_bronze(c))} AS DECIMAL(38,6)))" for c in DECIMAIS
        )
        expr_silver = ", ".join(f"sum(CAST({q(c)} AS DECIMAL(38,6)))" for c in DECIMAIS)
        somas_bronze = con.execute(f"SELECT {expr_bronze} FROM {BRONZE}").fetchone()
        somas_silver = con.execute(f"SELECT {expr_silver} FROM {SILVER}").fetchone()
    finally:
        con.close()
    assert list(somas_bronze) == list(somas_silver)


# ---- 6. Somas das 26 inteiras iguais (incl. ano) ----


def test_somas_inteiras(silver_db):
    con = _ro(silver_db)
    try:
        expr_bronze = ", ".join(
            f"sum(CAST({q(nome_bronze(c))} AS DECIMAL(38,6)))" for c in INTEIROS
        )
        expr_silver = ", ".join(f"sum(CAST({q(c)} AS DECIMAL(38,6)))" for c in INTEIROS)
        somas_bronze = con.execute(f"SELECT {expr_bronze} FROM {BRONZE}").fetchone()
        somas_silver = con.execute(f"SELECT {expr_silver} FROM {SILVER}").fetchone()
    finally:
        con.close()
    assert list(somas_bronze) == list(somas_silver)


# ---- 7. Negativos por coluna e totais ----


def test_negativos(silver_db):
    con = _ro(silver_db)
    numericas = INTEIROS + DECIMAIS
    colunas_com_neg = 0
    por_prefixo = {"despesa": 0, "indice": 0, "volume": 0}
    try:
        for c in numericas:
            neg_silver = con.execute(
                f"SELECT count(*) FROM {SILVER} WHERE {q(c)} < 0"
            ).fetchone()[0]
            neg_bronze = con.execute(
                f"SELECT count(*) FROM {BRONZE} "
                f"WHERE TRY_CAST({q(nome_bronze(c))} AS DECIMAL(38,6)) < 0"
            ).fetchone()[0]
            # Critério 7: negativos por coluna iguais em bronze e silver.
            assert neg_silver == neg_bronze, c
            if neg_silver:
                colunas_com_neg += 1
                for pref in por_prefixo:
                    if c.startswith(pref):
                        por_prefixo[pref] += neg_silver
    finally:
        con.close()
    assert colunas_com_neg == N_COLUNAS_NEGATIVAS
    assert por_prefixo["despesa"] == NEG_DESPESA
    assert por_prefixo["indice"] == NEG_INDICE
    assert por_prefixo["volume"] == NEG_VOLUME


# ---- 8. Chave: id_municipio com 7 dígitos e 5.549 distintos ----


def test_id_municipio(silver_db):
    con = _ro(silver_db)
    try:
        fora = con.execute(
            f"SELECT count(*) FROM {SILVER} "
            "WHERE NOT regexp_full_match(id_municipio, '^[0-9]{7}$')"
        ).fetchone()[0]
        distintos = con.execute(
            f"SELECT count(DISTINCT id_municipio) FROM {SILVER}"
        ).fetchone()[0]
    finally:
        con.close()
    assert fora == 0
    assert distintos == N_MUNICIPIOS


# ---- 9. Anomalia de população preservada (A2) ----


def test_anomalia_populacao(silver_db):
    con = _ro(silver_db)
    try:
        n = con.execute(
            f"SELECT count(*) FROM {SILVER} "
            "WHERE populacao_atendida_agua > populacao_urbana"
        ).fetchone()[0]
    finally:
        con.close()
    assert n == POP_ATENDIDA_MAIOR_URBANA


# ---- 10. 100% nulo em 2022 (A4) ----


def test_nulo_total_2022(silver_db):
    con = _ro(silver_db)
    try:
        total = con.execute(
            f"SELECT count(*) FROM {SILVER} WHERE ano = 2022"
        ).fetchone()[0]
        nulos = con.execute(
            f"SELECT count(*) FROM {SILVER} "
            "WHERE ano = 2022 AND populacao_urbana_atendida_esgoto IS NULL"
        ).fetchone()[0]
    finally:
        con.close()
    assert total == LINHAS_2022
    assert nulos == LINHAS_2022


# ---- 11. Coluna renomeada ----


def test_coluna_renomeada(silver_db):
    con = _ro(silver_db)
    try:
        cols = {
            r[0]
            for r in con.execute(
                "SELECT column_name FROM duckdb_columns() "
                "WHERE schema_name = 'silver' "
                "AND table_name = 'municipio_agua_esgoto'"
            ).fetchall()
        }
        # Valores batem 1:1 com a coluna original da bronze (join pela chave).
        divergentes = con.execute(
            f"SELECT count(*) FROM {SILVER} s "
            f"JOIN {BRONZE} b "
            "  ON s.ano = CAST(b.ano AS INTEGER) "
            "  AND s.id_municipio = b.id_municipio "
            "WHERE s.populacao_atendida_esgoto "
            "  IS DISTINCT FROM CAST(b.populacao_atentida_esgoto AS INTEGER)"
        ).fetchone()[0]
    finally:
        con.close()
    assert "populacao_atendida_esgoto" in cols
    assert "populacao_atentida_esgoto" not in cols
    assert divergentes == 0


# ---- 12. Idempotência: rodar a transformação 2x dá a mesma tabela ----


def test_idempotencia(silver_db, monkeypatch):
    def assinatura():
        con = _ro(silver_db)
        try:
            linhas = con.execute(f"SELECT count(*) FROM {SILVER}").fetchone()[0]
            nulas = con.execute(
                "SELECT "
                + " + ".join(f"(count(*) - count({q(c)}))" for c in TODAS)
                + f" FROM {SILVER}"
            ).fetchone()[0]
            soma_ano = con.execute(
                f"SELECT sum(CAST(ano AS BIGINT)) FROM {SILVER}"
            ).fetchone()[0]
        finally:
            con.close()
        return (linhas, nulas, soma_ano)

    antes = assinatura()
    # Roda a transformação de novo sobre o mesmo banco (nenhuma conexão aberta).
    monkeypatch.setattr(db_mod, "CAMINHO_BANCO", silver_db)
    transf_mod.main()
    depois = assinatura()
    assert antes == depois


# ---- Bloqueantes: SystemExit(1) e silver ausente depois (ROLLBACK) ----


def test_bloqueio_decimal_3_casas(silver_db, tmp_path, monkeypatch):
    """B4: decimal com 3 casas é detectado no texto ANTES do CAST."""
    copia = tmp_path / "snis.duckdb"
    _preparar_copia(silver_db, copia, _primeira_coluna("extensao_rede_agua = '10.239'"))
    monkeypatch.setattr(db_mod, "CAMINHO_BANCO", copia)
    with pytest.raises(SystemExit) as exc:
        transf_mod.main()
    assert exc.value.code == 1
    assert _silver_ausente(copia)


def test_bloqueio_nao_numerico(silver_db, tmp_path, monkeypatch):
    """B2: valor que não converte para o tipo-alvo."""
    copia = tmp_path / "snis.duckdb"
    _preparar_copia(silver_db, copia, _primeira_coluna("extensao_rede_agua = 'abc'"))
    monkeypatch.setattr(db_mod, "CAMINHO_BANCO", copia)
    with pytest.raises(SystemExit) as exc:
        transf_mod.main()
    assert exc.value.code == 1
    assert _silver_ausente(copia)


def test_bloqueio_string_vazia(silver_db, tmp_path, monkeypatch):
    """B9: '' (ou só espaços) é quebra de contrato da ingestão."""
    copia = tmp_path / "snis.duckdb"
    _preparar_copia(silver_db, copia, _primeira_coluna("extensao_rede_agua = '   '"))
    monkeypatch.setattr(db_mod, "CAMINHO_BANCO", copia)
    with pytest.raises(SystemExit) as exc:
        transf_mod.main()
    assert exc.value.code == 1
    assert _silver_ausente(copia)


def test_bloqueio_chave_duplicada(silver_db, tmp_path, monkeypatch):
    """B7: chave (ano, id_municipio) repetida — a silver não deduplica."""
    copia = tmp_path / "snis.duckdb"
    # Faz a linha de maior rowid repetir a chave da linha de menor rowid.
    dup = (
        f"UPDATE {BRONZE} SET "
        f"  ano = (SELECT ano FROM {BRONZE} ORDER BY rowid LIMIT 1), "
        f"  id_municipio = "
        f"    (SELECT id_municipio FROM {BRONZE} ORDER BY rowid LIMIT 1) "
        f"WHERE rowid = (SELECT max(rowid) FROM {BRONZE})"
    )
    _preparar_copia(silver_db, copia, dup)
    monkeypatch.setattr(db_mod, "CAMINHO_BANCO", copia)
    with pytest.raises(SystemExit) as exc:
        transf_mod.main()
    assert exc.value.code == 1
    assert _silver_ausente(copia)


def test_bloqueio_bronze_ausente(tmp_path, monkeypatch):
    """B1: bronze inexistente — nada a transformar."""
    banco = tmp_path / "vazio.duckdb"
    monkeypatch.setattr(db_mod, "CAMINHO_BANCO", banco)
    with pytest.raises(SystemExit) as exc:
        transf_mod.main()
    assert exc.value.code == 1
    assert _silver_ausente(banco)
