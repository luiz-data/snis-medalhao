"""Testes da camada bronze — spec-ingestao.md."""

import hashlib
from pathlib import Path

import duckdb
import pytest

import pipeline.db as db_mod
import pipeline.ingestao as ingestao_mod

ARQUIVO_FONTE = db_mod.PASTA_RAW / "br_mdr_snis_municipio_agua_esgoto.csv.gz"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


_hash_antes: str = ""


@pytest.fixture(scope="module")
def bronze_db(tmp_path_factory):
    """Roda a ingestão num banco temporário e retorna a conexão."""
    global _hash_antes
    _hash_antes = _sha256(ARQUIVO_FONTE)

    banco = tmp_path_factory.mktemp("db") / "snis.duckdb"
    original = db_mod.CAMINHO_BANCO
    db_mod.CAMINHO_BANCO = banco

    ingestao_mod.main()
    con = duckdb.connect(str(banco))
    yield con
    con.close()
    db_mod.CAMINHO_BANCO = original


# ---- 1. Linhas ----


def test_linhas(bronze_db):
    total = bronze_db.execute(
        "SELECT count(*) FROM bronze.municipio_agua_esgoto"
    ).fetchone()[0]
    assert total == 119_256


# ---- 2. Colunas ----


def test_colunas(bronze_db):
    colunas = bronze_db.execute("DESCRIBE bronze.municipio_agua_esgoto").fetchall()
    assert len(colunas) == 133


# ---- 3. Tudo VARCHAR ----


def test_tudo_varchar(bronze_db):
    tipos = bronze_db.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = 'bronze' "
        "AND table_name = 'municipio_agua_esgoto'"
    ).fetchall()
    assert all(t[0] == "VARCHAR" for t in tipos)


# ---- 4. Nomes e ordem ----


def test_nomes_e_ordem(bronze_db):
    colunas_tabela = [
        r[0]
        for r in bronze_db.execute("DESCRIBE bronze.municipio_agua_esgoto").fetchall()
    ]
    fonte = (
        f"read_csv('{ARQUIVO_FONTE}', all_varchar=true, header=true, "
        f"delim=',', encoding='utf-8')"
    )
    colunas_csv = [
        r[0] for r in bronze_db.execute(f"DESCRIBE SELECT * FROM {fonte}").fetchall()
    ]
    assert colunas_tabela == colunas_csv


# ---- 5. Nulos consistentes ----


def test_nulos_consistentes(bronze_db):
    coluna = "populacao_atendida_agua"
    fonte = (
        f"read_csv('{ARQUIVO_FONTE}', all_varchar=true, header=true, "
        f"delim=',', encoding='utf-8')"
    )
    nulos_fonte = bronze_db.execute(
        f'SELECT count(*) - count("{coluna}") FROM {fonte}'
    ).fetchone()[0]
    nulos_tabela = bronze_db.execute(
        f'SELECT count(*) - count("{coluna}") FROM bronze.municipio_agua_esgoto'
    ).fetchone()[0]
    assert nulos_tabela == nulos_fonte


# ---- 6. Idempotência ----


def test_idempotencia(bronze_db):
    ingestao_mod.main()
    total = bronze_db.execute(
        "SELECT count(*) FROM bronze.municipio_agua_esgoto"
    ).fetchone()[0]
    colunas = bronze_db.execute("DESCRIBE bronze.municipio_agua_esgoto").fetchall()
    assert total == 119_256
    assert len(colunas) == 133


# ---- 7. Arquivo ausente ----


def test_arquivo_ausente(monkeypatch):
    monkeypatch.setattr(ingestao_mod, "ARQUIVO", Path("/inexistente/nada.csv.gz"))
    with pytest.raises(SystemExit) as exc:
        ingestao_mod.main()
    assert exc.value.code == 1


# ---- 8. Hash da fonte inalterado ----


def test_hash_fonte_inalterado(bronze_db):
    hash_depois = _sha256(ARQUIVO_FONTE)
    assert _hash_antes == hash_depois
