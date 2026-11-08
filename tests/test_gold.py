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
        return (
            con.execute(
                "SELECT count(*) FROM duckdb_schemas() WHERE schema_name = 'gold'"
            ).fetchone()[0]
            > 0
        )
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
    2010: 26,
    2011: 35,
    2012: 22,
    2013: 3,
    2014: 3,
    2015: 1,
    2016: 43,
    2017: 7,
    2018: 1,
    2019: 7,
    2020: 6,
    2021: 18,
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


# ---------------------------------------------------------------------------
# Mart 3 — gold.perdas_consumo_uf_ano (spec-gold.md §2, D3/D25)
# ---------------------------------------------------------------------------

M3 = "gold.perdas_consumo_uf_ano"

# Expectativas confirmadas no MCP/SELECT (2026-11-08).
M3_LINHAS = 754  # 27×28 = 756 menos 2 pares ausentes em anos iniciais
M3_PERDA_MAX = 94.48  # máximo observado de indice_perdas_in049
M3_PC_NAC_2021_MIN = 150.0  # consumo per capita nacional 2021 (IN022, D25) ≈ 151,3
M3_PC_NAC_2021_MAX = 153.0
M3_EXTREMO_MUN = "1100114"  # Vilhena/RO
M3_EXTREMO_ANO = 1997  # único per capita absurdo, preservado sem correção


def test_m3_linhas_e_pk(gold_db):
    """754 linhas; PK (ano, sigla_uf) única; dimensões DTB não nulas."""
    con = _ro(gold_db)
    try:
        linhas = con.execute(f"SELECT count(*) FROM {M3}").fetchone()[0]
        dup = con.execute(
            f"SELECT count(*) FROM (SELECT 1 FROM {M3} "
            "GROUP BY ano, sigla_uf HAVING count(*) > 1)"
        ).fetchone()[0]
        nulos = con.execute(
            f"SELECT count(*) FROM {M3} "
            "WHERE sigla_uf IS NULL OR nome_uf IS NULL OR nome_regiao IS NULL"
        ).fetchone()[0]
    finally:
        con.close()
    assert linhas == M3_LINHAS
    assert dup == 0 and nulos == 0


def test_m3_perdas_faixa(gold_db):
    """indice_perdas_in049 ∈ [0, 100] (D3, soma sobre soma sem inconsistentes)."""
    con = _ro(gold_db)
    try:
        fora = con.execute(
            f"SELECT count(*) FROM {M3} WHERE indice_perdas_in049 NOT BETWEEN 0 AND 100"
        ).fetchone()[0]
        maxp = con.execute(f"SELECT max(indice_perdas_in049) FROM {M3}").fetchone()[0]
    finally:
        con.close()
    assert fora == 0
    assert maxp == pytest.approx(M3_PERDA_MAX, abs=0.01)


def test_m3_identidade_informantes_inconsistentes(gold_db):
    """D3: informantes_perdas + inconsistentes = municípios com AG006 e AG010 não nulos."""
    con = _ro(gold_db)
    try:
        divergentes = con.execute(
            """
            WITH esperado AS (
              SELECT s.ano, d.sigla_uf,
                count(*) FILTER (WHERE s.volume_agua_produzido IS NOT NULL
                   AND s.volume_agua_consumido IS NOT NULL) AS perdas_nao_nula
              FROM silver.municipio_agua_esgoto s
              JOIN silver.ibge_dtb_municipio d ON d.id_municipio = s.id_municipio
              GROUP BY s.ano, d.sigla_uf
            )
            SELECT count(*) FROM gold.perdas_consumo_uf_ano m
            JOIN esperado e ON e.ano = m.ano AND e.sigla_uf = m.sigla_uf
            WHERE m.municipios_informantes_perdas + m.linhas_inconsistentes_in049
                  <> e.perdas_nao_nula
            """
        ).fetchone()[0]
    finally:
        con.close()
    assert divergentes == 0


def test_m3_componentes_somam_inconsistentes(gold_db):
    """D3: excluidas_den_nao_positivo + excluidas_consumo_acima = linhas_inconsistentes_in049."""
    con = _ro(gold_db)
    try:
        incoerentes = con.execute(
            f"SELECT count(*) FROM {M3} WHERE "
            "excluidas_den_nao_positivo + excluidas_consumo_acima "
            "<> linhas_inconsistentes_in049"
        ).fetchone()[0]
    finally:
        con.close()
    assert incoerentes == 0


def test_m3_consumo_per_capita_nacional_2021(gold_db):
    """IN022 (D25): consumo per capita nacional 2021 ∈ [150, 153] L/hab·dia.

    Reconstruído da silver (soma sobre soma) com a fórmula cB: (AG010 − AG019)
    sobre a média da população atendida do ano e do ano anterior exato.
    """
    con = _ro(gold_db)
    try:
        pc = con.execute(
            """
            WITH s AS (
              SELECT ano, volume_agua_consumido AS ag010,
                coalesce(volume_agua_tratada_exportado, 0) AS ag019,
                populacao_atendida_agua AS pop,
                lag(populacao_atendida_agua) OVER (
                  PARTITION BY id_municipio ORDER BY ano) AS lag_pop,
                lag(ano) OVER (PARTITION BY id_municipio ORDER BY ano) AS lag_ano
              FROM silver.municipio_agua_esgoto
            )
            SELECT sum((ag010 - ag019) * 1000000.0)
                   / nullif(sum(((pop + coalesce(
                        CASE WHEN lag_ano = ano - 1 THEN lag_pop END, pop)) / 2.0)
                        * 365.0), 0)
            FROM s
            WHERE ano = 2021 AND ag010 IS NOT NULL AND pop > 0
            """
        ).fetchone()[0]
    finally:
        con.close()
    assert M3_PC_NAC_2021_MIN <= pc <= M3_PC_NAC_2021_MAX


def test_m3_lag_usa_ano_anterior_exato(gold_db):
    """D25: a média de população ignora o lag quando não é o ano-1 exato.

    Monta um município sintético com um buraco na série (2015 ausente): a média
    de 2016 tem de cair no fallback (= pop de 2016), não usar a pop de 2014.
    """
    con = duckdb.connect(":memory:")
    try:
        con.execute(
            """
            CREATE TABLE s(id_municipio VARCHAR, ano INT, pop INT);
            INSERT INTO s VALUES ('X', 2014, 1000), ('X', 2016, 3000);
            """
        )
        pop_med_2016 = con.execute(
            """
            WITH m AS (
              SELECT ano, pop,
                lag(pop) OVER (PARTITION BY id_municipio ORDER BY ano) AS lag_pop,
                lag(ano) OVER (PARTITION BY id_municipio ORDER BY ano) AS lag_ano
              FROM s
            )
            SELECT (pop + coalesce(
                      CASE WHEN lag_ano = ano - 1 THEN lag_pop END, pop)) / 2.0
            FROM m WHERE ano = 2016
            """
        ).fetchone()[0]
    finally:
        con.close()
    # 2014 não é 2015; fallback -> média = pop de 2016 (3000), não (1000+3000)/2.
    assert pop_med_2016 == 3000.0


def test_m3_extremo_vilhena_1997_preservado(gold_db):
    """D25: Vilhena/RO 1997 é o único per capita absurdo, preservado sem correção.

    O erro de escala no bruto (volume_agua_consumido) permanece na silver e
    domina o per capita de RO em 1997 (> 1.000 L/hab·dia), fora da janela robusta.
    """
    con = _ro(gold_db)
    try:
        # o município extremo segue na silver, intacto (consumo >> população)
        consumo, pop = con.execute(
            "SELECT volume_agua_consumido, populacao_atendida_agua "
            "FROM silver.municipio_agua_esgoto "
            f"WHERE id_municipio = '{M3_EXTREMO_MUN}' AND ano = {M3_EXTREMO_ANO}"
        ).fetchone()
        # per capita de RO em 1997 é absurdo (> 1.000 L/hab·dia) por causa dele
        pc_ro_1997 = con.execute(
            f"SELECT consumo_per_capita FROM {M3} "
            f"WHERE ano = {M3_EXTREMO_ANO} AND sigla_uf = 'RO'"
        ).fetchone()[0]
        # e esse é o único grão com per capita absurdo em todo o mart
        absurdos = con.execute(
            f"SELECT count(*) FROM {M3} "
            "WHERE consumo_per_capita > 1000 OR consumo_per_capita < 20"
        ).fetchone()[0]
    finally:
        con.close()
    assert consumo is not None and pop is not None and consumo > pop
    assert pc_ro_1997 > 1000
    assert absurdos == 1


# ---------------------------------------------------------------------------
# Mart 4 — gold.ranking_atendimento_variacao (spec-gold.md §2, D19/D5/D21/D26)
# ---------------------------------------------------------------------------

M4 = "gold.ranking_atendimento_variacao"

# Expectativas confirmadas no MCP/SELECT (2026-11-08).
M4_PAINEL = 4_472  # painel fixo único (D19), 12 anos não nulos
M4_EXCLUIDOS_A2 = 41  # A2 em 2010 ou 2021 entre membros do painel (D5)
M4_LINHAS = M4_PAINEL - M4_EXCLUIDOS_A2  # 4.431 ranqueados
M4_COLUNAS = 10
M4_EXTREMAS = 12  # |variacao_pp| > 80 pp


def test_m4_linhas_pk_identidade(gold_db):
    """4.431 linhas × 10 colunas; PK (id_municipio) única; identidade D5.

    Painel fixo único (4.472) = ranqueados (4.431) + excluídos por A2 (41).
    O painel e as exclusões são reconstruídos da silver, independentes do mart.
    """
    con = _ro(gold_db)
    try:
        linhas = con.execute(f"SELECT count(*) FROM {M4}").fetchone()[0]
        colunas = con.execute(
            "SELECT count(*) FROM duckdb_columns() WHERE schema_name = 'gold' "
            "AND table_name = 'ranking_atendimento_variacao'"
        ).fetchone()[0]
        dup = con.execute(
            f"SELECT count(*) FROM (SELECT 1 FROM {M4} "
            "GROUP BY id_municipio HAVING count(*) > 1)"
        ).fetchone()[0]
        # painel e A2 reconstruídos da silver (fonte independente do mart)
        painel, a2 = con.execute(
            """
            WITH painel AS (
              SELECT id_municipio FROM silver.municipio_agua_esgoto
              WHERE ano BETWEEN 2010 AND 2021
                AND populacao_urbana_atendida_agua IS NOT NULL
                AND populacao_urbana IS NOT NULL
              GROUP BY id_municipio HAVING count(DISTINCT ano) = 12
            ),
            a2 AS (
              SELECT DISTINCT s.id_municipio
              FROM silver.municipio_agua_esgoto s
              JOIN painel p ON p.id_municipio = s.id_municipio
              WHERE s.ano IN (2010, 2021)
                AND s.populacao_urbana_atendida_agua > s.populacao_urbana
            )
            SELECT (SELECT count(*) FROM painel), (SELECT count(*) FROM a2)
            """
        ).fetchone()
    finally:
        con.close()
    assert (linhas, colunas) == (M4_LINHAS, M4_COLUNAS)
    assert dup == 0
    assert (painel, a2) == (M4_PAINEL, M4_EXCLUIDOS_A2)
    assert painel == linhas + a2  # 4.472 = 4.431 + 41


def test_m4_posicao_sem_buracos(gold_db):
    """D26: posicao 1..N única e sem buracos (row_number)."""
    con = _ro(gold_db)
    try:
        pmin, pmax, distintas, n = con.execute(
            f"SELECT min(posicao), max(posicao), count(DISTINCT posicao), count(*) "
            f"FROM {M4}"
        ).fetchone()
    finally:
        con.close()
    assert pmin == 1
    assert pmax == M4_LINHAS
    assert distintas == M4_LINHAS
    assert n == M4_LINHAS


def test_m4_posicao_empate_coerente(gold_db):
    """D26: posicao_empate (rank) — empates compartilham o valor; mínimo 1.

    Onde variacao_pp é igual, posicao_empate é igual; o mínimo é 1 e há menos
    valores distintos que linhas (há empates reais).
    """
    con = _ro(gold_db)
    try:
        pe_min = con.execute(f"SELECT min(posicao_empate) FROM {M4}").fetchone()[0]
        # dentro de cada valor de variacao_pp, posicao_empate é único
        incoerentes = con.execute(
            f"SELECT count(*) FROM (SELECT 1 FROM {M4} "
            "GROUP BY variacao_pp HAVING count(DISTINCT posicao_empate) > 1)"
        ).fetchone()[0]
        distintas, n = con.execute(
            f"SELECT count(DISTINCT posicao_empate), count(*) FROM {M4}"
        ).fetchone()
    finally:
        con.close()
    assert pe_min == 1
    assert incoerentes == 0
    assert distintas < n  # há empates reais (ex.: muitos a +0 e a +100 pp)


def test_m4_variacao_faixa(gold_db):
    """variacao_pp ∈ [−100, +100] e = cobertura_2021 − cobertura_2010."""
    con = _ro(gold_db)
    try:
        fora = con.execute(
            f"SELECT count(*) FROM {M4} WHERE variacao_pp NOT BETWEEN -100 AND 100"
        ).fetchone()[0]
        divergentes = con.execute(
            f"SELECT count(*) FROM {M4} "
            "WHERE abs(variacao_pp - (cobertura_2021 - cobertura_2010)) > 1e-6"
        ).fetchone()[0]
    finally:
        con.close()
    assert fora == 0
    assert divergentes == 0


def test_m4_variacao_extrema(gold_db):
    """variacao_extrema verdadeira exatamente onde |variacao_pp| > 80 (12 casos)."""
    con = _ro(gold_db)
    try:
        n_extrema = con.execute(
            f"SELECT count(*) FROM {M4} WHERE variacao_extrema"
        ).fetchone()[0]
        incoerentes = con.execute(
            f"SELECT count(*) FROM {M4} "
            "WHERE variacao_extrema <> (abs(variacao_pp) > 80)"
        ).fetchone()[0]
    finally:
        con.close()
    assert n_extrema == M4_EXTREMAS
    assert incoerentes == 0


def test_m4_anos_fixos_nunca_2022(gold_db):
    """D2/D19: cobertura reconstruída usa só 2010 e 2021; 2022 nunca entra.

    O mart não traz coluna de ano (grão = município), então a prova é que as
    coberturas batem com a silver de 2010/2021 e que nenhum membro do painel
    depende de 2022 (o painel exige os 12 anos 2010–2021).
    """
    con = _ro(gold_db)
    try:
        # cobertura_2010 e cobertura_2021 do mart batem com a silver desses anos
        divergentes = con.execute(
            """
            WITH esperado AS (
              SELECT id_municipio,
                100.0 * max(CASE WHEN ano = 2010 THEN populacao_urbana_atendida_agua END)
                  / nullif(max(CASE WHEN ano = 2010 THEN populacao_urbana END), 0) AS c10,
                100.0 * max(CASE WHEN ano = 2021 THEN populacao_urbana_atendida_agua END)
                  / nullif(max(CASE WHEN ano = 2021 THEN populacao_urbana END), 0) AS c21
              FROM silver.municipio_agua_esgoto
              WHERE ano IN (2010, 2021)
              GROUP BY id_municipio
            )
            SELECT count(*) FROM gold.ranking_atendimento_variacao m
            JOIN esperado e ON e.id_municipio = m.id_municipio
            WHERE abs(m.cobertura_2010 - e.c10) > 1e-6
               OR abs(m.cobertura_2021 - e.c21) > 1e-6
            """
        ).fetchone()[0]
    finally:
        con.close()
    assert divergentes == 0


# ===========================================================================
# Mart 5 — gold.financeiro_uf_ano (spec-gold.md §2, ficha Mart 5; D22/D27/D28)
# Expectativas confirmadas no SELECT/MCP (somente leitura, 2026-11-08).
# ===========================================================================

M5 = "gold.financeiro_uf_ano"

M5_LINHAS = 754  # 27 UF × 28 anos − 2 (sem informante em 1996-AC e 1996-PI)
M5_COLUNAS = 16
M5_UFS = 27
M5_ANOS = 28
# Investimento total do Brasil por ano (R$ nominal) — conferência cruzada mart 8.
M5_INV_BR_POR_ANO = {
    2010: 7_672_158_349.94,
    2011: 7_085_417_183.19,
    2012: 8_122_015_347.98,
    2013: 9_052_433_064.27,
    2014: 10_672_877_749.33,
    2015: 10_333_746_833.61,
    2016: 10_330_283_909.77,
    2017: 9_726_560_670.98,
    2018: 10_959_142_821.54,
    2019: 14_245_200_322.09,
    2020: 12_195_430_301.88,
    2021: 15_297_535_452.19,
}
M5_INV_BR_2021 = 15_297_535_452.19
# Série nacional ponderada (soma sobre soma), R$/m³ (D22/D27).
M5_TARIFA_2010, M5_TARIFA_2021 = 2.18, 4.12
M5_DESP_UNIT_2010, M5_DESP_UNIT_2021 = 2.06, 3.87  # DTS/FN017 (IN003), não DEX
# Investimento atípico (D4/D28): limiar R$ 1.000/hab, janela 2010–2021.
M5_ATIPICOS_TOTAL = 120
M5_RN_QUEDA_PCT = 29.0  # −29% do total de RN se os atípicos saíssem


def test_m5_linhas_pk_e_total_br(gold_db):
    """754 linhas (756 − 2); PK única; dims DTB não nulas; invest. BR 2021."""
    con = _ro(gold_db)
    try:
        linhas, ufs, anos, colunas = con.execute(
            f"SELECT count(*), count(DISTINCT sigla_uf), count(DISTINCT ano), "
            "(SELECT count(*) FROM duckdb_columns() WHERE schema_name='gold' "
            "AND table_name='financeiro_uf_ano') "
            f"FROM {M5}"
        ).fetchone()
        dups = con.execute(
            f"SELECT count(*) FROM (SELECT ano, sigla_uf FROM {M5} "
            "GROUP BY ano, sigla_uf HAVING count(*) > 1)"
        ).fetchone()[0]
        nulos = con.execute(
            f"SELECT count(*) FROM {M5} WHERE ano IS NULL OR sigla_uf IS NULL "
            "OR nome_uf IS NULL OR nome_regiao IS NULL"
        ).fetchone()[0]
        inv_2021 = con.execute(
            f"SELECT sum(investimento_total) FROM {M5} WHERE ano = 2021"
        ).fetchone()[0]
    finally:
        con.close()
    assert (linhas, ufs, anos, colunas) == (M5_LINHAS, M5_UFS, M5_ANOS, M5_COLUNAS)
    assert dups == 0
    assert nulos == 0
    assert round(float(inv_2021), 2) == M5_INV_BR_2021


def test_m5_total_br_por_ano(gold_db):
    """Investimento total do Brasil por ano 2010–2021 (conferência mart 8)."""
    con = _ro(gold_db)
    try:
        linhas = con.execute(
            f"SELECT ano, sum(investimento_total) FROM {M5} "
            "WHERE ano BETWEEN 2010 AND 2021 GROUP BY ano ORDER BY ano"
        ).fetchall()
    finally:
        con.close()
    obtido = {ano: round(float(tot), 2) for ano, tot in linhas}
    assert obtido == M5_INV_BR_POR_ANO


def test_m5_tarifa_despesa_unitaria(gold_db):
    """Tarifa (FN001) e despesa unitária (FN017/DTS) nacionais, R$/m³.

    Soma sobre soma com a conversão de unidade (volume em 1.000 m³/ano -> ÷1.000).
    Reconstrói o nacional pela silver e compara com a série da ficha (D22/D27).
    """
    con = _ro(gold_db)
    try:
        tarifa_2010, desp_2010 = con.execute(
            """
            SELECT
              sum(receita_operacional_direta) FILTER (WHERE vf > 0)
                / (nullif(sum(vf) FILTER (WHERE receita_operacional_direta IS NOT NULL), 0) * 1000.0),
              sum(despesa_total_servico) FILTER (WHERE vf > 0)
                / (nullif(sum(vf) FILTER (WHERE despesa_total_servico IS NOT NULL), 0) * 1000.0)
            FROM (SELECT *, coalesce(volume_agua_faturado,0)+coalesce(volume_esgoto_faturado,0) AS vf
                  FROM silver.municipio_agua_esgoto WHERE ano = 2010)
            """
        ).fetchone()
        tarifa_2021, desp_2021 = con.execute(
            """
            SELECT
              sum(receita_operacional_direta) FILTER (WHERE vf > 0)
                / (nullif(sum(vf) FILTER (WHERE receita_operacional_direta IS NOT NULL), 0) * 1000.0),
              sum(despesa_total_servico) FILTER (WHERE vf > 0)
                / (nullif(sum(vf) FILTER (WHERE despesa_total_servico IS NOT NULL), 0) * 1000.0)
            FROM (SELECT *, coalesce(volume_agua_faturado,0)+coalesce(volume_esgoto_faturado,0) AS vf
                  FROM silver.municipio_agua_esgoto WHERE ano = 2021)
            """
        ).fetchone()
        negativos = con.execute(
            f"SELECT count(*) FROM {M5} WHERE tarifa_media < 0 OR despesa_unitaria < 0"
        ).fetchone()[0]
    finally:
        con.close()
    assert round(float(tarifa_2010), 2) == M5_TARIFA_2010
    assert round(float(tarifa_2021), 2) == M5_TARIFA_2021
    assert round(float(desp_2010), 2) == M5_DESP_UNIT_2010
    assert round(float(desp_2021), 2) == M5_DESP_UNIT_2021
    # despesa unitária (DTS) fica abaixo da tarifa — confirma o FN017 (operação ~equilíbrio)
    assert M5_DESP_UNIT_2021 < M5_TARIFA_2021
    assert negativos == 0


def test_m5_identidades_informantes(gold_db):
    """Identidade informantes + excluídos (den ≤ 0) = total com valor não nulo.

    Para tarifa, despesa e índice, por (ano, UF): a contagem de informantes do
    mart iguala a reconstrução pela silver (num e den não nulos e den > 0), e
    nunca excede o total de linhas com o valor obrigatório não nulo.
    """
    con = _ro(gold_db)
    try:
        divergentes = con.execute(
            f"""
            WITH s AS (
              SELECT ano, sigla_uf,
                receita_operacional_direta AS fn001,
                despesa_total_servico AS dts,
                coalesce(volume_agua_faturado,0)+coalesce(volume_esgoto_faturado,0) AS vf
              FROM silver.municipio_agua_esgoto
            ),
            esperado AS (
              SELECT ano, sigla_uf,
                count(*) FILTER (WHERE fn001 IS NOT NULL AND vf > 0) AS inf_tarifa,
                count(*) FILTER (WHERE dts   IS NOT NULL AND vf > 0) AS inf_despesa,
                count(*) FILTER (WHERE fn001 IS NOT NULL) AS fn001_nn,
                count(*) FILTER (WHERE dts   IS NOT NULL) AS dts_nn
              FROM s GROUP BY ano, sigla_uf
            )
            SELECT count(*)
            FROM {M5} m JOIN esperado e ON e.ano = m.ano AND e.sigla_uf = m.sigla_uf
            WHERE m.municipios_informantes_tarifa  <> e.inf_tarifa
               OR m.municipios_informantes_despesa <> e.inf_despesa
               OR m.municipios_informantes_tarifa  > e.fn001_nn
               OR m.municipios_informantes_despesa > e.dts_nn
            """
        ).fetchone()[0]
        obrig_nulos = con.execute(
            f"SELECT count(*) FROM {M5} WHERE "
            "(municipios_informantes_tarifa > 0 AND (tarifa_media IS NULL OR receita_operacional_direta IS NULL)) "
            "OR (municipios_informantes_despesa > 0 AND (despesa_unitaria IS NULL OR despesa_total_servicos IS NULL))"
        ).fetchone()[0]
    finally:
        con.close()
    assert divergentes == 0
    assert obrig_nulos == 0


def test_m5_investimento_atipico(gold_db):
    """D4/D28: 120 atípicos na janela; RN −29%; sem_atipicos ≤ total."""
    con = _ro(gold_db)
    try:
        atipicos = con.execute(
            f"SELECT sum(municipios_investimento_atipico) FROM {M5} "
            "WHERE ano BETWEEN 2010 AND 2021"
        ).fetchone()[0]
        fora_janela = con.execute(
            f"SELECT coalesce(sum(municipios_investimento_atipico), 0) FROM {M5} "
            "WHERE ano NOT BETWEEN 2010 AND 2021"
        ).fetchone()[0]
        viola = con.execute(
            f"SELECT count(*) FROM {M5} "
            "WHERE investimento_total_sem_atipicos > investimento_total"
        ).fetchone()[0]
        rn_com, rn_sem = con.execute(
            f"SELECT sum(investimento_total), sum(investimento_total_sem_atipicos) "
            f"FROM {M5} WHERE sigla_uf = 'RN' AND ano BETWEEN 2010 AND 2021"
        ).fetchone()
    finally:
        con.close()
    assert atipicos == M5_ATIPICOS_TOTAL
    assert fora_janela == 0
    assert viola == 0
    queda = 100.0 * (1 - float(rn_sem) / float(rn_com))
    assert round(queda, 1) == M5_RN_QUEDA_PCT
