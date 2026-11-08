"""Testes do EXECUTOR da gold (spec-gold.md §4/§4.1, D20).

Apenas os testes do executor — os testes dos 10 marts vêm depois, junto com os
SQL de cada mart. Estilo dos testes da silver (tests/test_silver.py):

- banco temporário via tmp_path, monkeypatch de pipeline.db.CAMINHO_BANCO;
- os arquivos sql/gold/*.sql são simulados num diretório temporário, via
  monkeypatch de pipeline.gold.PASTA_SQL (não dependemos dos marts reais);
- casos bloqueantes trabalham em CÓPIAS do banco (shutil.copy): a gold já
  construída tem de sobreviver intacta ao ROLLBACK (nenhum schema parcial).

O executor não precisa da silver para estes testes (os SELECTs são sintéticos),
então não rodamos o pipeline completo — só exercitamos a mecânica do executor.
"""

import shutil

import duckdb
import pytest

import pipeline.db as db_mod
import pipeline.gold as gold_mod
import pipeline.ingestao as ing_snis
import pipeline.ingestao_ibge as ing_ibge
import pipeline.transformacao as transf_snis
import pipeline.transformacao_ibge as transf_ibge

# --- Infra ------------------------------------------------------------------


def _ro(banco):
    return duckdb.connect(str(banco), read_only=True)


def _escrever(pasta, **arquivos):
    """Grava {nome_arquivo: conteudo_sql} em `pasta` e devolve a pasta."""
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, corpo in arquivos.items():
        (pasta / nome).write_text(corpo, encoding="utf-8")
    return pasta


def _apontar(monkeypatch, banco, pasta_sql):
    monkeypatch.setattr(db_mod, "CAMINHO_BANCO", banco)
    monkeypatch.setattr(gold_mod, "PASTA_SQL", pasta_sql)


def _tabelas_gold(banco):
    con = _ro(banco)
    try:
        return {
            r[0]
            for r in con.execute(
                "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'gold'"
            ).fetchall()
        }
    finally:
        con.close()


def _schema_gold_existe(banco):
    con = _ro(banco)
    try:
        return con.execute(
            "SELECT count(*) FROM duckdb_schemas() WHERE schema_name = 'gold'"
        ).fetchone()[0] > 0
    finally:
        con.close()


# ---- Critério 1: cria gold.teste com 1 linha, 1 coluna (x = 1) -------------


def test_executor_cria_tabela_1x1(tmp_path, monkeypatch):
    banco = tmp_path / "snis.duckdb"
    pasta = _escrever(tmp_path / "sql", **{"00_teste.sql": "SELECT 1 AS x"})
    _apontar(monkeypatch, banco, pasta)

    gold_mod.main()

    con = _ro(banco)
    try:
        linhas = con.execute("SELECT count(*) FROM gold.teste").fetchone()[0]
        colunas = con.execute(
            "SELECT count(*) FROM duckdb_columns() "
            "WHERE schema_name = 'gold' AND table_name = 'teste'"
        ).fetchone()[0]
        x = con.execute("SELECT x FROM gold.teste").fetchone()[0]
    finally:
        con.close()
    assert (linhas, colunas, x) == (1, 1, 1)


# ---- Critério 2: schema recriado (DROP+CREATE) a cada execução -------------


def test_executor_idempotente(tmp_path, monkeypatch):
    banco = tmp_path / "snis.duckdb"
    pasta = _escrever(tmp_path / "sql", **{"00_teste.sql": "SELECT 1 AS x"})
    _apontar(monkeypatch, banco, pasta)

    gold_mod.main()
    gold_mod.main()  # segunda execução: DROP+CREATE, sem erro de "já existe"

    assert _tabelas_gold(banco) == {"teste"}


# ---- Critério 2b: pasta vazia recria o schema, 0 tabelas, sai com 0 --------


def test_executor_pasta_vazia(tmp_path, monkeypatch):
    banco = tmp_path / "snis.duckdb"
    pasta = tmp_path / "sql"
    pasta.mkdir()
    _apontar(monkeypatch, banco, pasta)

    gold_mod.main()  # não deve levantar SystemExit

    assert _schema_gold_existe(banco)
    assert _tabelas_gold(banco) == set()


# ---- Critério 5: leitura em ordem numérica (02 depende de 01) --------------


def test_executor_ordem_numerica(tmp_path, monkeypatch):
    banco = tmp_path / "snis.duckdb"
    # 02 referencia gold.a (criada por 01); só funciona se 01 vier antes.
    pasta = _escrever(
        tmp_path / "sql",
        **{
            "01_a.sql": "SELECT 1 AS x",
            "02_b.sql": "SELECT x FROM gold.a",
        },
    )
    _apontar(monkeypatch, banco, pasta)

    gold_mod.main()

    assert _tabelas_gold(banco) == {"a", "b"}


# ---- Critério 3: erro de SQL -> ROLLBACK + exit 1, sem schema parcial ------


def test_executor_rollback_em_erro(tmp_path, monkeypatch):
    # Primeiro, uma gold válida (gold.um). Copia. Na cópia, roda um lote com um
    # arquivo que falha: o ROLLBACK tem de preservar gold.um e não deixar parcial.
    banco = tmp_path / "snis.duckdb"
    pasta_ok = _escrever(tmp_path / "sql_ok", **{"01_um.sql": "SELECT 1 AS x"})
    _apontar(monkeypatch, banco, pasta_ok)
    gold_mod.main()
    assert _tabelas_gold(banco) == {"um"}

    copia = tmp_path / "copia.duckdb"
    shutil.copy(banco, copia)
    pasta_ruim = _escrever(
        tmp_path / "sql_ruim",
        **{
            "01_um.sql": "SELECT 1 AS x",
            "02_dois.sql": "SELECT * FROM tabela_que_nao_existe",
        },
    )
    _apontar(monkeypatch, copia, pasta_ruim)

    with pytest.raises(SystemExit) as exc:
        gold_mod.main()
    assert exc.value.code == 1
    # ROLLBACK restaurou o estado anterior: gold.um intacta, sem gold.dois.
    assert _tabelas_gold(copia) == {"um"}


# ---- Critério 4: validação "um SELECT por arquivo" (D20) -------------------


@pytest.mark.parametrize(
    "corpo",
    [
        "SELECT 1 AS x; DROP TABLE gold.teste",  # múltiplos statements
        "CREATE TABLE gold.teste AS SELECT 1 AS x",  # traz CREATE
        "SELECT 1 AS x; SELECT 2 AS y",  # dois SELECTs
        "   ",  # vazio
    ],
)
def test_executor_uma_tabela_por_arquivo(tmp_path, monkeypatch, corpo):
    banco = tmp_path / "snis.duckdb"
    pasta = _escrever(tmp_path / "sql", **{"00_teste.sql": corpo})
    _apontar(monkeypatch, banco, pasta)

    with pytest.raises(SystemExit) as exc:
        gold_mod.main()
    assert exc.value.code == 1
    # Nenhuma tabela parcial: ou schema vazio, ou nem chegou a criar.
    assert _tabelas_gold(banco) == set()


# ---- D20 aceita CTE (WITH ... SELECT): marts 4/10 vão precisar -------------


def test_executor_aceita_with(tmp_path, monkeypatch):
    banco = tmp_path / "snis.duckdb"
    pasta = _escrever(
        tmp_path / "sql",
        **{"00_teste.sql": "WITH c AS (SELECT 1 AS x) SELECT x FROM c"},
    )
    _apontar(monkeypatch, banco, pasta)

    gold_mod.main()

    assert _tabelas_gold(banco) == {"teste"}


# ===========================================================================
# Testes dos MARTS (SQL real de sql/gold/) — pipeline completo numa fixture.
# Estilo dos testes da silver (tests/test_ibge_silver.py): banco temporário,
# monkeypatch de db_mod.CAMINHO_BANCO, expectativas numéricas só aqui.
# ===========================================================================

M1 = "gold.atendimento_uf_ano"

# Expectativas confirmadas no MCP/SELECT (spec-gold.md §2, ficha Mart 1).
M1_LINHAS = 324  # 27 UF × 12 anos (2010–2021, D2)
M1_UFS = 27
M1_ANOS = 12
M1_INFORMANTES_AGUA_2021 = 5_284  # 5.302 − 18 exclusões A2 (D5)
M1_COB_AGUA_BR_2021_MIN = 93.2
M1_COB_AGUA_BR_2021_MAX = 93.5
# Exclusões A2 de água por ano (D5), confirmadas no SELECT.
M1_EXCL_AGUA_POR_ANO = {
    2010: 26, 2011: 35, 2012: 22, 2013: 3, 2014: 3, 2015: 1,
    2016: 43, 2017: 7, 2018: 1, 2019: 7, 2020: 6, 2021: 18,
}


@pytest.fixture(scope="module")
def gold_db(tmp_path_factory):
    """Pipeline completo (SNIS + IBGE + gold) uma vez; devolve o CAMINHO."""
    banco = tmp_path_factory.mktemp("db") / "snis.duckdb"
    original = db_mod.CAMINHO_BANCO
    db_mod.CAMINHO_BANCO = banco
    try:
        ing_snis.main()
        transf_snis.main()
        ing_ibge.main()
        transf_ibge.main()
        gold_mod.main()  # lê sql/gold/*.sql reais
        yield banco
    finally:
        db_mod.CAMINHO_BANCO = original


def test_m1_linhas_e_cobertura(gold_db):
    con = _ro(gold_db)
    try:
        linhas = con.execute(f"SELECT count(*) FROM {M1}").fetchone()[0]
        ufs, anos = con.execute(
            f"SELECT count(DISTINCT sigla_uf), count(DISTINCT ano) FROM {M1}"
        ).fetchone()
        # cada cobertura (quando definida) dentro de [0, 100]
        fora = con.execute(
            f"SELECT count(*) FROM {M1} WHERE "
            "cobertura_urbana_agua NOT BETWEEN 0 AND 100 "
            "OR cobertura_urbana_esgoto NOT BETWEEN 0 AND 100"
        ).fetchone()[0]
    finally:
        con.close()
    assert (linhas, ufs, anos) == (M1_LINHAS, M1_UFS, M1_ANOS)
    assert fora == 0


def test_m1_agua_nacional_2021(gold_db):
    """Água nacional 2021 ≈ 93,33% — reconstruída pela silver (soma sobre soma)."""
    con = _ro(gold_db)
    try:
        cob = con.execute(
            "SELECT 100.0 * sum(s.populacao_urbana_atendida_agua) "
            "/ nullif(sum(s.populacao_urbana), 0) "
            "FROM silver.municipio_agua_esgoto s "
            "JOIN silver.ibge_dtb_municipio d ON d.id_municipio = s.id_municipio "
            "WHERE s.ano = 2021 AND s.populacao_urbana IS NOT NULL "
            "  AND s.populacao_urbana_atendida_agua IS NOT NULL "
            "  AND s.populacao_urbana_atendida_agua <= s.populacao_urbana"
        ).fetchone()[0]
    finally:
        con.close()
    assert M1_COB_AGUA_BR_2021_MIN <= cob <= M1_COB_AGUA_BR_2021_MAX


def test_m1_pk_e_dimensoes(gold_db):
    con = _ro(gold_db)
    try:
        dup = con.execute(
            f"SELECT count(*) FROM (SELECT 1 FROM {M1} "
            "GROUP BY ano, sigla_uf HAVING count(*) > 1)"
        ).fetchone()[0]
        nulos = con.execute(
            f"SELECT count(*) FROM {M1} "
            "WHERE sigla_uf IS NULL OR nome_uf IS NULL OR nome_regiao IS NULL"
        ).fetchone()[0]
    finally:
        con.close()
    assert dup == 0 and nulos == 0


def test_m1_informantes_agua_2021(gold_db):
    con = _ro(gold_db)
    try:
        total = con.execute(
            f"SELECT sum(municipios_informantes_agua) FROM {M1} WHERE ano = 2021"
        ).fetchone()[0]
    finally:
        con.close()
    assert total == M1_INFORMANTES_AGUA_2021


def test_m1_identidade_exclusao_a2(gold_db):
    """D5: informantes + excluídas A2 = municípios com valor não nulo (água e esgoto).

    A reconstrução da silver bate com as colunas do mart grão a grão.
    """
    con = _ro(gold_db)
    try:
        # por (ano, UF): informantes_agua + excluidas_a2_agua deve igualar o total
        # de municípios com água (num e den) não nula; idem esgoto.
        divergentes = con.execute(
            """
            WITH esperado AS (
              SELECT s.ano, d.sigla_uf,
                count(*) FILTER (WHERE s.populacao_urbana_atendida_agua IS NOT NULL
                   AND s.populacao_urbana IS NOT NULL) AS agua_nao_nula,
                count(*) FILTER (WHERE s.populacao_urbana_atendida_esgoto IS NOT NULL
                   AND s.populacao_urbana_residente_esgoto IS NOT NULL) AS esgoto_nao_nula
              FROM silver.municipio_agua_esgoto s
              JOIN silver.ibge_dtb_municipio d ON d.id_municipio = s.id_municipio
              WHERE s.ano BETWEEN 2010 AND 2021
              GROUP BY s.ano, d.sigla_uf
            )
            SELECT count(*) FROM gold.atendimento_uf_ano m
            JOIN esperado e ON e.ano = m.ano AND e.sigla_uf = m.sigla_uf
            WHERE m.municipios_informantes_agua + m.excluidas_a2_agua <> e.agua_nao_nula
               OR m.municipios_informantes_esgoto + m.excluidas_a2_esgoto <> e.esgoto_nao_nula
            """
        ).fetchone()[0]
        # linhas_excluidas_a2 = excluídas por água OU esgoto (>= cada parcial,
        # <= soma das parciais)
        incoerentes = con.execute(
            f"SELECT count(*) FROM {M1} WHERE "
            "linhas_excluidas_a2 < greatest(excluidas_a2_agua, excluidas_a2_esgoto) "
            "OR linhas_excluidas_a2 > excluidas_a2_agua + excluidas_a2_esgoto"
        ).fetchone()[0]
    finally:
        con.close()
    assert divergentes == 0
    assert incoerentes == 0


def test_m1_exclusao_a2_por_ano(gold_db):
    """D5: exclusões A2 de água por ano batem com os valores confirmados."""
    con = _ro(gold_db)
    try:
        por_ano = dict(
            con.execute(
                f"SELECT ano, sum(excluidas_a2_agua) FROM {M1} GROUP BY ano"
            ).fetchall()
        )
    finally:
        con.close()
    assert por_ano == M1_EXCL_AGUA_POR_ANO


# ---------------------------------------------------------------------------
# Mart 2 — gold.esgoto_coleta_tratamento_ano (spec-gold.md §2, D23/D24)
# ---------------------------------------------------------------------------

M2 = "gold.esgoto_coleta_tratamento_ano"

# Expectativas confirmadas no MCP/SELECT (2026-11-08).
M2_LINHAS = 28  # 1995–2022
M2_COLUNAS = 13
M2_PAINEL_COLETA = 1_473  # painel de esgoto-coleta (D24)
M2_PAINEL_TRATAMENTO = 1_440  # painel de esgoto-tratamento (D24)
M2_PRIMEIRO_ANO_ROBUSTO = 2006  # coleta > 1.000 informantes (R3)


def test_m2_linhas_colunas_pk(gold_db):
    """28 linhas (1995–2022) × 13 colunas; PK (ano) única."""
    con = _ro(gold_db)
    try:
        linhas = con.execute(f"SELECT count(*) FROM {M2}").fetchone()[0]
        colunas = con.execute(
            "SELECT count(*) FROM duckdb_columns() "
            "WHERE schema_name = 'gold' AND table_name = 'esgoto_coleta_tratamento_ano'"
        ).fetchone()[0]
        anos = con.execute(
            f"SELECT min(ano), max(ano), count(DISTINCT ano) FROM {M2}"
        ).fetchone()
        dup = con.execute(
            f"SELECT count(*) FROM (SELECT 1 FROM {M2} GROUP BY ano HAVING count(*) > 1)"
        ).fetchone()[0]
    finally:
        con.close()
    assert (linhas, colunas) == (M2_LINHAS, M2_COLUNAS)
    assert anos == (1995, 2022, 28)
    assert dup == 0


def test_m2_identidade_den_zero(gold_db):
    """D23: informantes + excluidas_den_zero = municípios com os dois volumes não nulos.

    Reconstrói o "ambos não nulos" da silver e confere grão a grão (coleta e
    tratamento). Nenhuma linha pode divergir.
    """
    con = _ro(gold_db)
    try:
        divergentes = con.execute(
            f"""
            WITH esperado AS (
              SELECT ano,
                count(*) FILTER (WHERE volume_esgoto_coletado IS NOT NULL
                   AND volume_agua_consumido IS NOT NULL) AS coleta_nao_nula,
                count(*) FILTER (WHERE volume_esgoto_tratado IS NOT NULL
                   AND volume_esgoto_coletado IS NOT NULL) AS trat_nao_nula
              FROM silver.municipio_agua_esgoto GROUP BY ano
            )
            SELECT count(*) FROM {M2} m JOIN esperado e ON e.ano = m.ano
            WHERE m.municipios_informantes_coleta + m.excluidas_den_zero_coleta
                  <> e.coleta_nao_nula
               OR m.municipios_informantes_tratamento + m.excluidas_den_zero_tratamento
                  <> e.trat_nao_nula
            """
        ).fetchone()[0]
    finally:
        con.close()
    assert divergentes == 0


def test_m2_painel_constante_e_null_fora(gold_db):
    """D24: contagens de painel constantes em 2010–2021 e NULL fora."""
    con = _ro(gold_db)
    try:
        # dentro da janela: um único valor distinto, igual ao esperado
        dentro = con.execute(
            f"SELECT count(DISTINCT municipios_painel_coleta), "
            f"min(municipios_painel_coleta), "
            f"count(DISTINCT municipios_painel_tratamento), "
            f"min(municipios_painel_tratamento) "
            f"FROM {M2} WHERE ano BETWEEN 2010 AND 2021"
        ).fetchone()
        # fora da janela: sempre NULL (índices e contagens de painel)
        fora_nao_nulo = con.execute(
            f"SELECT count(*) FROM {M2} WHERE ano NOT BETWEEN 2010 AND 2021 AND ("
            "municipios_painel_coleta IS NOT NULL "
            "OR municipios_painel_tratamento IS NOT NULL "
            "OR indice_coleta_painel IS NOT NULL "
            "OR indice_tratamento_painel IS NOT NULL)"
        ).fetchone()[0]
    finally:
        con.close()
    assert dentro == (1, M2_PAINEL_COLETA, 1, M2_PAINEL_TRATAMENTO)
    assert fora_nao_nulo == 0


def test_m2_serie_robusta(gold_db):
    """serie_robusta verdadeira exatamente de 2006 em diante (coleta > 1.000)."""
    con = _ro(gold_db)
    try:
        incoerentes = con.execute(
            f"SELECT count(*) FROM {M2} WHERE "
            f"serie_robusta <> (ano >= {M2_PRIMEIRO_ANO_ROBUSTO}) "
            "OR serie_robusta <> (municipios_informantes_coleta > 1000)"
        ).fetchone()[0]
    finally:
        con.close()
    assert incoerentes == 0


def test_m2_indices_faixa(gold_db):
    """Índices ∈ [0, 100], exceto onde tratado > coletado admite > 100 (D23).

    - coleta: pode passar de 100 só nos anos frágeis (não robustos), onde uma
      anomalia de dado domina o numerador (Fortaleza/1998, Recife/1999).
    - tratamento: pode passar de 100 só quando há municípios com tratado >
      coletado (esgoto importado); nunca negativo.
    """
    con = _ro(gold_db)
    try:
        # nenhum índice negativo (den > 0 garante sinal do numerador)
        negativos = con.execute(
            f"SELECT count(*) FROM {M2} WHERE indice_coleta_esgoto < 0 "
            "OR indice_tratamento_esgoto < 0"
        ).fetchone()[0]
        # tratamento > 100 só com tratado > coletado documentado
        trat_acima_sem_motivo = con.execute(
            f"SELECT count(*) FROM {M2} WHERE indice_tratamento_esgoto > 100 "
            "AND municipios_tratado_acima_coletado = 0"
        ).fetchone()[0]
        # coleta > 100 só fora da série robusta (anomalia de dado preservada)
        coleta_acima_robusta = con.execute(
            f"SELECT count(*) FROM {M2} WHERE indice_coleta_esgoto > 100 "
            "AND serie_robusta"
        ).fetchone()[0]
    finally:
        con.close()
    assert negativos == 0
    assert trat_acima_sem_motivo == 0
    assert coleta_acima_robusta == 0
