"""Testes da bronze IBGE (spec-ibge.md §4 e §9) — espelho fiel, tudo VARCHAR.

As contagens esperadas vêm de pipeline.ingestao_ibge (as mesmas constantes que
o código usa em BB2/BB3), não são recopiadas aqui.
"""


import duckdb
import pytest

import pipeline.db as db_mod
import pipeline.ingestao_ibge as ing_ibge

FONTES = ing_ibge.FONTES


def _ro(banco):
    return duckdb.connect(str(banco), read_only=True)


@pytest.fixture(scope="module")
def bronze_db(tmp_path_factory):
    """Roda só a bronze IBGE uma vez e devolve o CAMINHO do banco temporário."""
    banco = tmp_path_factory.mktemp("db") / "snis.duckdb"
    original = db_mod.CAMINHO_BANCO
    db_mod.CAMINHO_BANCO = banco
    try:
        ing_ibge.main()
        yield banco
    finally:
        db_mod.CAMINHO_BANCO = original


@pytest.mark.parametrize("fonte", list(FONTES))
def test_linhas_e_colunas(bronze_db, fonte):
    tabela, _arq, linhas_esp, colunas_esp = FONTES[fonte]
    con = _ro(bronze_db)
    try:
        linhas = con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]
        colunas = con.execute(f"DESCRIBE {tabela}").fetchall()
    finally:
        con.close()
    assert linhas == linhas_esp
    assert len(colunas) == colunas_esp


@pytest.mark.parametrize("fonte", list(FONTES))
def test_tudo_varchar(bronze_db, fonte):
    tabela = FONTES[fonte][0]
    con = _ro(bronze_db)
    try:
        tipos = {t[1] for t in con.execute(f"DESCRIBE {tabela}").fetchall()}
    finally:
        con.close()
    assert tipos == {"VARCHAR"}


def test_idempotente(bronze_db):
    """Rodar a bronze de novo no mesmo banco mantém as contagens (CREATE OR REPLACE)."""
    original = db_mod.CAMINHO_BANCO
    db_mod.CAMINHO_BANCO = bronze_db
    try:
        ing_ibge.main()
    finally:
        db_mod.CAMINHO_BANCO = original
    con = _ro(bronze_db)
    try:
        for tabela, _a, linhas_esp, _c in FONTES.values():
            n = con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]
            assert n == linhas_esp
    finally:
        con.close()
