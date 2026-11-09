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


# ===========================================================================
# Mart 6 — gold.atendimento_porte_ano (spec-gold.md §2, ficha Mart 6; D16/D29)
# Expectativas confirmadas no SELECT/MCP (somente leitura, 2026-11-08).
# ===========================================================================

M6 = "gold.atendimento_porte_ano"

M6_LINHAS = 72  # 6 faixas × 12 anos (2010–2021)
M6_COLUNAS = 11
M6_FAIXAS = 6
M6_ANOS = 12
# Faixa fixada pela pop. IBGE 2021 (D16); 5.570 nas faixas + 1 excluído = 5.571 (DTB).
M6_MUNIC_POR_FAIXA = {
    "1_ate_5mil": 1250,
    "2_5a20mil": 2520,
    "3_20a50mil": 1120,
    "4_50a100mil": 354,
    "5_100a500mil": 277,
    "6_acima500mil": 49,
}
M6_MUNIC_FAIXAS = 5570  # soma das 6 faixas
M6_DTB = 5571  # cadastro completo (D12)
M6_POP_FAIXAS_2021 = 213_317_639  # Σ pop_total_ibge das faixas em 2021 (= IBGE Brasil)
# Nacional 2021 por soma sobre soma (NÃO média das faixas), D29.
M6_AGUA_NAC_2021 = 84.20  # IN055 oficial 84,2%
M6_ESGOTO_NAC_2021 = 55.81  # IN056 oficial 55,8%
M6_AUX_NAC_2021 = 66.95  # auxiliar (universo comum do esgoto)
# Porte do mart 6 construído a partir da silver (fonte independente do mart).
_PORTE = """
WITH porte AS (
  SELECT d.id_municipio,
    CASE WHEN p.populacao_total_ibge IS NULL THEN NULL
      WHEN p.populacao_total_ibge <   5000 THEN '1_ate_5mil'
      WHEN p.populacao_total_ibge <  20000 THEN '2_5a20mil'
      WHEN p.populacao_total_ibge <  50000 THEN '3_20a50mil'
      WHEN p.populacao_total_ibge < 100000 THEN '4_50a100mil'
      WHEN p.populacao_total_ibge < 500000 THEN '5_100a500mil'
      ELSE '6_acima500mil' END AS faixa_porte
  FROM silver.ibge_dtb_municipio d
  LEFT JOIN silver.ibge_populacao_municipio p
    ON p.id_municipio = d.id_municipio AND p.ano = 2021
)
"""


def test_m6_linhas_pk_colunas(gold_db):
    """72 linhas × 11 colunas; PK (faixa_porte, ano) única; 6 faixas × 12 anos."""
    con = _ro(gold_db)
    try:
        linhas, faixas, anos = con.execute(
            f"SELECT count(*), count(DISTINCT faixa_porte), count(DISTINCT ano) "
            f"FROM {M6}"
        ).fetchone()
        colunas = con.execute(
            "SELECT count(*) FROM duckdb_columns() WHERE schema_name = 'gold' "
            "AND table_name = 'atendimento_porte_ano'"
        ).fetchone()[0]
        dup = con.execute(
            f"SELECT count(*) FROM (SELECT 1 FROM {M6} "
            "GROUP BY faixa_porte, ano HAVING count(*) > 1)"
        ).fetchone()[0]
    finally:
        con.close()
    assert (linhas, colunas) == (M6_LINHAS, M6_COLUNAS)
    assert (faixas, anos) == (M6_FAIXAS, M6_ANOS)
    assert dup == 0


def test_m6_faixa_fixa_nos_12_anos(gold_db):
    """D16: municipios_faixa é constante nos 12 anos e bate com os valores fixos."""
    con = _ro(gold_db)
    try:
        # para cada faixa: um único valor de municipios_faixa em todos os anos
        por_faixa = con.execute(
            f"SELECT faixa_porte, count(DISTINCT municipios_faixa), min(municipios_faixa) "
            f"FROM {M6} GROUP BY faixa_porte"
        ).fetchall()
    finally:
        con.close()
    distintos = {f: (n, v) for f, n, v in por_faixa}
    for faixa, esperado in M6_MUNIC_POR_FAIXA.items():
        n_valores, valor = distintos[faixa]
        assert n_valores == 1, f"{faixa}: municipios_faixa varia entre anos"
        assert valor == esperado, f"{faixa}: {valor} != {esperado}"


def test_m6_universo_5570_mais_1(gold_db):
    """5.570 nas faixas + 1 excluído (sem pop IBGE 2021) = 5.571 (DTB, D12)."""
    con = _ro(gold_db)
    try:
        # soma das faixas no mart (em qualquer ano; é fixo)
        soma_faixas = con.execute(
            f"SELECT sum(municipios_faixa) FROM {M6} WHERE ano = 2021"
        ).fetchone()[0]
        # universo DTB e excluídos reconstruídos da silver (independente do mart)
        dtb, sem_pop21 = con.execute(
            _PORTE + "SELECT (SELECT count(*) FROM silver.ibge_dtb_municipio), "
            "count(*) FILTER (WHERE faixa_porte IS NULL) FROM porte"
        ).fetchone()
    finally:
        con.close()
    assert soma_faixas == M6_MUNIC_FAIXAS
    assert dtb == M6_DTB
    assert sem_pop21 == M6_DTB - M6_MUNIC_FAIXAS  # exatamente 1 excluído
    assert soma_faixas + sem_pop21 == dtb


def test_m6_pop_total_ibge_2021(gold_db):
    """Σ pop_total_ibge das faixas em 2021 = 213.317.639 (= estimativa IBGE Brasil)."""
    con = _ro(gold_db)
    try:
        total = con.execute(
            f"SELECT sum(pop_total_ibge) FROM {M6} WHERE ano = 2021"
        ).fetchone()[0]
    finally:
        con.close()
    assert total == M6_POP_FAIXAS_2021


def test_m6_identidade_informantes_faixa(gold_db):
    """Identidade: informantes + não-informantes = municipios_faixa (água e esgoto).

    Como municipios_faixa é o universo fixo da faixa, informantes nunca o excedem
    e o complemento é o nº de não-informantes. Vale em todos os 72 grãos.
    """
    con = _ro(gold_db)
    try:
        viola = con.execute(
            f"SELECT count(*) FROM {M6} WHERE "
            "municipios_informantes_agua > municipios_faixa "
            "OR municipios_informantes_esgoto > municipios_faixa "
            "OR municipios_informantes_agua < 0 "
            "OR municipios_informantes_esgoto < 0"
        ).fetchone()[0]
    finally:
        con.close()
    assert viola == 0


def test_m6_nacional_2021_soma_sobre_soma(gold_db):
    """Água 84,20% / esgoto 55,81% / auxiliar 66,95% nacionais 2021.

    Reconstruídos da silver por SOMA SOBRE SOMA (não média das faixas do mart),
    com a mesma faixa/universo. Água e esgoto dividem pela pop. dos informantes
    de ÁGUA (D29); o auxiliar divide pela pop. dos informantes de esgoto.
    """
    con = _ro(gold_db)
    try:
        agua, esgoto, aux = con.execute(
            _PORTE
            + """
            , base AS (
              SELECT pt.faixa_porte, pop.populacao_total_ibge AS pop_ibge,
                s.populacao_atendida_agua AS at_agua,
                s.populacao_atendida_esgoto AS at_esg
              FROM porte pt
              LEFT JOIN silver.ibge_populacao_municipio pop
                ON pop.id_municipio = pt.id_municipio AND pop.ano = 2021
              LEFT JOIN silver.municipio_agua_esgoto s
                ON s.id_municipio = pt.id_municipio AND s.ano = 2021
              WHERE pt.faixa_porte IS NOT NULL
            )
            SELECT
              100.0 * sum(at_agua) / nullif(sum(pop_ibge) FILTER (WHERE at_agua IS NOT NULL), 0),
              100.0 * sum(at_esg)  / nullif(sum(pop_ibge) FILTER (WHERE at_agua IS NOT NULL), 0),
              100.0 * sum(at_esg)  / nullif(sum(pop_ibge) FILTER (WHERE at_esg  IS NOT NULL), 0)
            FROM base
            """
        ).fetchone()
    finally:
        con.close()
    assert round(float(agua), 2) == M6_AGUA_NAC_2021
    assert round(float(esgoto), 2) == M6_ESGOTO_NAC_2021
    assert round(float(aux), 2) == M6_AUX_NAC_2021


def test_m6_esgoto_usa_denominador_agua(gold_db):
    """D29: o denominador do esgoto é pop_informante_agua, NÃO pop_informante_esgoto.

    Reconstrói o numerador (Σ atendido esgoto) da silver e confere, grão a grão,
    que cobertura_esgoto = 100 × num / pop_informante_agua. Este teste FALHA se
    alguém trocar o denominador por pop_informante_esgoto (o auxiliar), porque os
    dois denominadores diferem na maioria dos grãos.
    """
    con = _ro(gold_db)
    try:
        # confirma que há grãos onde os dois denominadores diferem (teste não é vazio)
        diferem = con.execute(
            f"SELECT count(*) FROM {M6} WHERE pop_informante_agua <> pop_informante_esgoto"
        ).fetchone()[0]
        # numerador do esgoto reconstruído da silver, por (faixa, ano)
        divergentes = con.execute(
            _PORTE
            + f"""
            , num AS (
              SELECT pt.faixa_porte, s.ano, sum(s.populacao_atendida_esgoto) AS n_esg
              FROM porte pt
              JOIN silver.municipio_agua_esgoto s ON s.id_municipio = pt.id_municipio
              WHERE pt.faixa_porte IS NOT NULL AND s.ano BETWEEN 2010 AND 2021
              GROUP BY pt.faixa_porte, s.ano
            )
            SELECT count(*) FROM {M6} m JOIN num n
              ON n.faixa_porte = m.faixa_porte AND n.ano = m.ano
            WHERE abs(m.cobertura_esgoto
                      - 100.0 * n.n_esg / nullif(m.pop_informante_agua, 0)) > 1e-6
            """
        ).fetchone()[0]
        # e que usar o denominador de esgoto daria resultado DIFERENTE (prova do swap)
        trocado_bateria = con.execute(
            _PORTE
            + f"""
            , num AS (
              SELECT pt.faixa_porte, s.ano, sum(s.populacao_atendida_esgoto) AS n_esg
              FROM porte pt
              JOIN silver.municipio_agua_esgoto s ON s.id_municipio = pt.id_municipio
              WHERE pt.faixa_porte IS NOT NULL AND s.ano BETWEEN 2010 AND 2021
              GROUP BY pt.faixa_porte, s.ano
            )
            SELECT count(*) FROM {M6} m JOIN num n
              ON n.faixa_porte = m.faixa_porte AND n.ano = m.ano
            WHERE m.pop_informante_agua <> m.pop_informante_esgoto
              AND abs(m.cobertura_esgoto
                      - 100.0 * n.n_esg / nullif(m.pop_informante_esgoto, 0)) <= 1e-6
            """
        ).fetchone()[0]
    finally:
        con.close()
    assert diferem > 0  # existem grãos com denominadores distintos
    assert divergentes == 0  # cobertura_esgoto usa pop_informante_agua
    assert trocado_bateria == 0  # e NÃO coincide com o denominador de esgoto


def test_m6_cobertura_esgoto_auxiliar_relacao(gold_db):
    """D29: cobertura_esgoto (denom. água) ≤ auxiliar (denom. esgoto) — mesmo numerador.

    O auxiliar usa um denominador menor (só informantes de esgoto), então nunca é
    menor que cobertura_esgoto. Confirma também que os numeradores coincidem:
    cobertura_esgoto × pop_informante_agua = auxiliar × pop_informante_esgoto.
    """
    con = _ro(gold_db)
    try:
        viola_ordem = con.execute(
            f"SELECT count(*) FROM {M6} "
            "WHERE cobertura_esgoto > cobertura_esgoto_entre_informantes + 1e-9"
        ).fetchone()[0]
        num_incoerente = con.execute(
            f"SELECT count(*) FROM {M6} WHERE abs("
            "cobertura_esgoto * pop_informante_agua "
            "- cobertura_esgoto_entre_informantes * pop_informante_esgoto) > 1e-3"
        ).fetchone()[0]
    finally:
        con.close()
    assert viola_ordem == 0
    assert num_incoerente == 0


def test_m6_monotonicidade_2021(gold_db):
    """Perfil por faixa em 2021 (D29):

    - esgoto (IN056): monótono crescente nas 6 faixas;
    - água (IN055): crescente a partir da faixa 2 (faixa 1 > faixa 2, fato sem causa);
    - auxiliar: sem assumir monotonicidade (só verificamos que está em [0, 100]);
    - água > esgoto em todas as faixas.
    """
    con = _ro(gold_db)
    try:
        linhas = con.execute(
            f"SELECT faixa_porte, cobertura_agua, cobertura_esgoto, "
            f"cobertura_esgoto_entre_informantes "
            f"FROM {M6} WHERE ano = 2021 ORDER BY faixa_porte"
        ).fetchall()
    finally:
        con.close()
    # ordem das faixas é o prefixo numérico (1_..6_), já crescente por porte
    agua = [r[1] for r in linhas]
    esgoto = [r[2] for r in linhas]
    aux = [r[3] for r in linhas]
    # esgoto IN056 monótono crescente nas 6 faixas
    assert all(esgoto[i] < esgoto[i + 1] for i in range(len(esgoto) - 1))
    # água crescente a partir da faixa 2 (índices 1..5)
    assert all(agua[i] < agua[i + 1] for i in range(1, len(agua) - 1))
    # faixa 1 > faixa 2 (fato documentado, sem causa)
    assert agua[0] > agua[1]
    # água > esgoto em todas as faixas
    assert all(a > e for a, e in zip(agua, esgoto))
    # auxiliar só precisa estar em [0, 100] (não assumimos monotonicidade)
    assert all(0 <= x <= 100 for x in aux)


# ===========================================================================
# Mart 7 — gold.populacao_sem_servico_uf_ano (spec-gold.md §2, ficha Mart 7; D30/D29)
# Expectativas confirmadas no SELECT/MCP (somente leitura, 2026-11-08).
# ===========================================================================

M7 = "gold.populacao_sem_servico_uf_ano"

M7_LINHAS = 324  # 27 UF × 12 anos (2010–2021)
M7_COLUNAS = 14
M7_UFS = 27
M7_ANOS = 12
M7_SEM_AGUA_2021 = 33_285_121  # Σ pop_sem_agua nacional 2021 (greatest por município)
M7_SEM_ESGOTO_2021 = 92_879_110  # Σ pop_sem_esgoto nacional 2021 (IN056/D30)
M7_PCT_AGUA_2021 = 15.8  # 100 − IN055 (84,2)
M7_PCT_ESGOTO_2021 = 44.19  # 100 − IN056 (55,81)
M7_POP_BR_2021 = 213_317_639  # Σ pop_total_ibge 2021 = estimativa IBGE Brasil
# Topo do pct_sem_esgoto 2021: Norte (D29/D30).
M7_TOPO_ESGOTO_2021 = ["RO", "AP", "PA"]


def test_m7_linhas_pk_colunas(gold_db):
    """324 linhas × 14 colunas; PK (ano, sigla_uf) única; dims DTB não nulas."""
    con = _ro(gold_db)
    try:
        linhas, ufs, anos = con.execute(
            f"SELECT count(*), count(DISTINCT sigla_uf), count(DISTINCT ano) FROM {M7}"
        ).fetchone()
        colunas = con.execute(
            "SELECT count(*) FROM duckdb_columns() WHERE schema_name = 'gold' "
            "AND table_name = 'populacao_sem_servico_uf_ano'"
        ).fetchone()[0]
        dup = con.execute(
            f"SELECT count(*) FROM (SELECT 1 FROM {M7} "
            "GROUP BY ano, sigla_uf HAVING count(*) > 1)"
        ).fetchone()[0]
        nulos = con.execute(
            f"SELECT count(*) FROM {M7} "
            "WHERE sigla_uf IS NULL OR nome_uf IS NULL OR nome_regiao IS NULL"
        ).fetchone()[0]
    finally:
        con.close()
    assert (linhas, colunas) == (M7_LINHAS, M7_COLUNAS)
    assert (ufs, anos) == (M7_UFS, M7_ANOS)
    assert dup == 0 and nulos == 0


def test_m7_identidade_informantes_sem_informacao(gold_db):
    """Identidade: informantes_agua + sem_informacao_agua = municípios da UF no ano.

    O total de municípios por (ano, UF) é reconstruído da silver (universo =
    populacao × DTB na janela), independente do mart. Vale nos 324 grãos.
    """
    con = _ro(gold_db)
    try:
        divergentes = con.execute(
            f"""
            WITH esperado AS (
              SELECT p.ano, d.sigla_uf, count(*) AS munic
              FROM silver.ibge_populacao_municipio p
              JOIN silver.ibge_dtb_municipio d ON d.id_municipio = p.id_municipio
              WHERE p.ano BETWEEN 2010 AND 2021
              GROUP BY p.ano, d.sigla_uf
            )
            SELECT count(*) FROM {M7} m JOIN esperado e
              ON e.ano = m.ano AND e.sigla_uf = m.sigla_uf
            WHERE m.municipios_informantes_agua + m.municipios_sem_informacao_agua
                  <> e.munic
            """
        ).fetchone()[0]
    finally:
        con.close()
    assert divergentes == 0


def test_m7_pop_por_ano_igual_ibge(gold_db):
    """Σ pop_total_ibge por ano = estimativa IBGE Brasil (soma sobre as UFs)."""
    con = _ro(gold_db)
    try:
        divergentes = con.execute(
            f"""
            WITH ibge AS (
              SELECT ano, sum(populacao_total_ibge) AS pop
              FROM silver.ibge_populacao_municipio
              WHERE ano BETWEEN 2010 AND 2021 GROUP BY ano
            ),
            mart AS (SELECT ano, sum(pop_total_ibge) AS pop FROM {M7} GROUP BY ano)
            SELECT count(*) FROM mart m JOIN ibge i ON i.ano = m.ano
            WHERE m.pop <> i.pop
            """
        ).fetchone()[0]
        pop_2021 = con.execute(
            f"SELECT sum(pop_total_ibge) FROM {M7} WHERE ano = 2021"
        ).fetchone()[0]
    finally:
        con.close()
    assert divergentes == 0
    assert pop_2021 == M7_POP_BR_2021


def test_m7_nacional_2021(gold_db):
    """Nacional 2021: sem água 33,29 mi (15,8%); sem esgoto 92,88 mi (44,19%)."""
    con = _ro(gold_db)
    try:
        sem_agua, sem_esg, pop_inf = con.execute(
            f"SELECT sum(pop_sem_agua), sum(pop_sem_esgoto), sum(pop_informante_agua) "
            f"FROM {M7} WHERE ano = 2021"
        ).fetchone()
    finally:
        con.close()
    assert sem_agua == M7_SEM_AGUA_2021
    assert sem_esg == M7_SEM_ESGOTO_2021
    assert round(100.0 * float(sem_agua) / float(pop_inf), 1) == M7_PCT_AGUA_2021
    assert round(100.0 * float(sem_esg) / float(pop_inf), 2) == M7_PCT_ESGOTO_2021


def test_m7_sem_negativos(gold_db):
    """greatest(…,0) por município: pop_sem_* nunca negativo; piso ≥ 0."""
    con = _ro(gold_db)
    try:
        negativos = con.execute(
            f"SELECT count(*) FROM {M7} WHERE pop_sem_agua < 0 OR pop_sem_esgoto < 0 "
            "OR pop_sem_informacao_agua < 0"
        ).fetchone()[0]
    finally:
        con.close()
    assert negativos == 0


def test_m7_esgoto_usa_informantes_agua(gold_db):
    """D30: pop_sem_esgoto usa os informantes de ÁGUA, NÃO os de esgoto.

    Reconstrói as duas convenções da silver, por (ano, UF): a do mart tem de
    bater com a dos informantes de ÁGUA e NÃO com a dos informantes de esgoto
    (a convenção antiga, revogada). Este teste FALHA se alguém trocar a base,
    como no mart 6.
    """
    con = _ro(gold_db)
    try:
        bate_agua, bate_esgoto, difere = con.execute(
            f"""
            WITH recon AS (
              SELECT p.ano, d.sigla_uf,
                sum(greatest(p.populacao_total_ibge
                    - coalesce(s.populacao_atendida_esgoto, 0), 0))
                  FILTER (WHERE s.populacao_atendida_agua IS NOT NULL) AS sem_esg_agua,
                sum(greatest(p.populacao_total_ibge
                    - coalesce(s.populacao_atendida_esgoto, 0), 0))
                  FILTER (WHERE s.populacao_atendida_esgoto IS NOT NULL) AS sem_esg_esg
              FROM silver.ibge_populacao_municipio p
              JOIN silver.ibge_dtb_municipio d ON d.id_municipio = p.id_municipio
              LEFT JOIN silver.municipio_agua_esgoto s
                ON s.id_municipio = p.id_municipio AND s.ano = p.ano
              WHERE p.ano BETWEEN 2010 AND 2021
              GROUP BY p.ano, d.sigla_uf
            )
            SELECT
              count(*) FILTER (WHERE m.pop_sem_esgoto = r.sem_esg_agua),
              count(*) FILTER (WHERE m.pop_sem_esgoto = r.sem_esg_esg),
              count(*) FILTER (WHERE r.sem_esg_agua <> r.sem_esg_esg)
            FROM {M7} m JOIN recon r ON r.ano = m.ano AND r.sigla_uf = m.sigla_uf
            """
        ).fetchone()
    finally:
        con.close()
    assert bate_agua == M7_LINHAS  # todos os grãos usam informantes de água
    assert difere > 0  # as duas convenções diferem na maioria dos grãos
    assert bate_esgoto < M7_LINHAS  # NÃO é a convenção de informantes de esgoto


def test_m7_topo_esgoto_2021_norte(gold_db):
    """Ranking 2021: RO, AP, PA no topo do pct_sem_esgoto (Norte, D29/D30)."""
    con = _ro(gold_db)
    try:
        topo = [
            r[0]
            for r in con.execute(
                f"SELECT sigla_uf FROM {M7} WHERE ano = 2021 "
                "ORDER BY pct_sem_esgoto DESC LIMIT 3"
            ).fetchall()
        ]
    finally:
        con.close()
    assert topo == M7_TOPO_ESGOTO_2021


def test_m7_sql_sem_rascunho():
    """O SQL do mart 7 não traz marcadores de rascunho (TODO/FIXME/XXX/rascunho)."""
    import pathlib

    sql = (
        pathlib.Path(gold_mod.__file__).resolve().parent.parent
        / "sql"
        / "gold"
        / "07_populacao_sem_servico_uf_ano.sql"
    ).read_text(encoding="utf-8")
    for marcador in ("TODO", "FIXME", "XXX", "rascunho", "placeholder"):
        assert marcador.lower() not in sql.lower()


# ===========================================================================
# Mart 8 — gold.investimento_per_capita_uf_ano (spec-gold.md §2, ficha Mart 8)
# D31 (denominador universo comum) + D4/D28 (atípico, regra do mart 5 verbatim).
# Expectativas confirmadas no SELECT/MCP (somente leitura, 2026-11-08).
# ===========================================================================

M8 = "gold.investimento_per_capita_uf_ano"

M8_LINHAS = 324  # 27 UF × 12 anos (2010–2021)
M8_COLUNAS = 12
M8_UFS = 27
M8_ANOS = 12
# Universo de municípios (DTB ∩ pop IBGE) por ano: 5.570, salvo 2010/2011 (5.565).
M8_UNIVERSO = {
    ano: (5565 if ano in (2010, 2011) else 5570) for ano in range(2010, 2022)
}
# Atípicos por ano (D4/D28, R$ 1.000/hab) — idênticos ao mart 5.
M8_ATIPICOS_POR_ANO = {
    2010: 6,
    2011: 2,
    2012: 10,
    2013: 5,
    2014: 11,
    2015: 5,
    2016: 4,
    2017: 11,
    2018: 10,
    2019: 48,
    2020: 3,
    2021: 5,
}
M8_ATIPICOS_TOTAL = 120
# Per capita nacional (soma sobre soma), R$/hab.
M8_PC_COM = {2010: 44.26, 2019: 72.17, 2021: 75.82}
M8_PC_SEM = {2010: 42.88, 2019: 61.36, 2021: 75.56}
# RN 2019: com → sem atípicos (coluna do mart, por UF).
M8_RN_2019_COM, M8_RN_2019_SEM = 443.38, 218.91
# Denominador D31 (universo comum, 2021): pop informante < pop de todos os 5.570.
M8_POP_INFORMANTE_2021 = 201_771_427
M8_POP_TODOS_2021 = 213_317_639


def test_m8_linhas_pk_colunas(gold_db):
    """324 linhas; 12 colunas; PK (ano, sigla_uf) única; dims DTB não nulas."""
    con = _ro(gold_db)
    try:
        linhas, ufs, anos, colunas = con.execute(
            f"SELECT count(*), count(DISTINCT sigla_uf), count(DISTINCT ano), "
            "(SELECT count(*) FROM duckdb_columns() WHERE schema_name='gold' "
            "AND table_name='investimento_per_capita_uf_ano') "
            f"FROM {M8}"
        ).fetchone()
        dups = con.execute(
            f"SELECT count(*) FROM (SELECT ano, sigla_uf FROM {M8} "
            "GROUP BY ano, sigla_uf HAVING count(*) > 1)"
        ).fetchone()[0]
        nulos = con.execute(
            f"SELECT count(*) FROM {M8} WHERE ano IS NULL OR sigla_uf IS NULL "
            "OR nome_uf IS NULL OR nome_regiao IS NULL OR valor_nominal IS NOT TRUE"
        ).fetchone()[0]
        fora_janela = con.execute(
            f"SELECT count(*) FROM {M8} WHERE ano NOT BETWEEN 2010 AND 2021"
        ).fetchone()[0]
    finally:
        con.close()
    assert (linhas, ufs, anos, colunas) == (M8_LINHAS, M8_UFS, M8_ANOS, M8_COLUNAS)
    assert dups == 0
    assert nulos == 0
    assert fora_janela == 0


def test_m8_universo_e_identidade(gold_db):
    """Identidade informantes + não-informantes = municípios da UF-ano (DTB∩pop).

    O universo (5.570/ano; 5.565 em 2010/2011) é reconstruído da silver; o mart
    conta `municipios_informantes` e o resto são os não-informantes.
    """
    con = _ro(gold_db)
    try:
        # municípios da UF-ano = DTB ∩ pop IBGE (fonte independente do mart)
        universo = con.execute(
            """
            SELECT p.ano, d.sigla_uf, count(*)
            FROM silver.ibge_dtb_municipio d
            JOIN silver.ibge_populacao_municipio p ON p.id_municipio = d.id_municipio
            WHERE p.ano BETWEEN 2010 AND 2021
            GROUP BY p.ano, d.sigla_uf
            """
        ).fetchall()
        # informantes de investimento por UF-ano, direto da silver
        inform = con.execute(
            """
            SELECT s.ano, d.sigla_uf, count(*)
            FROM silver.municipio_agua_esgoto s
            JOIN silver.ibge_dtb_municipio d ON d.id_municipio = s.id_municipio
            JOIN silver.ibge_populacao_municipio p
              ON p.id_municipio = s.id_municipio AND p.ano = s.ano
            WHERE s.ano BETWEEN 2010 AND 2021
              AND s.investimento_total_prestador IS NOT NULL AND p.populacao_total_ibge > 0
            GROUP BY s.ano, d.sigla_uf
            """
        ).fetchall()
        mart = con.execute(
            f"SELECT ano, sigla_uf, municipios_informantes FROM {M8}"
        ).fetchall()
        # total nacional por ano (confere 5.570/5.565)
        nacional = con.execute(
            """
            SELECT p.ano, count(*)
            FROM silver.ibge_dtb_municipio d
            JOIN silver.ibge_populacao_municipio p ON p.id_municipio = d.id_municipio
            WHERE p.ano BETWEEN 2010 AND 2021
            GROUP BY p.ano
            """
        ).fetchall()
    finally:
        con.close()
    universo = {(a, u): n for a, u, n in universo}
    inform = {(a, u): n for a, u, n in inform}
    mart = {(a, u): n for a, u, n in mart}
    # o mart conta exatamente os informantes da silver
    assert mart == inform
    # identidade: informantes + não-informantes = universo da UF-ano
    for chave, total in universo.items():
        inf = mart.get(chave, 0)
        nao_inf = total - inf
        assert inf + nao_inf == total
        assert nao_inf >= 0
    assert {a: n for a, n in nacional} == M8_UNIVERSO


def test_m8_serie_atipicos(gold_db):
    """Série de atípicos por ano = 6,2,10,5,11,5,4,11,10,48,3,5 (total 120)."""
    con = _ro(gold_db)
    try:
        por_ano = con.execute(
            f"SELECT ano, sum(municipios_investimento_atipico) FROM {M8} "
            "GROUP BY ano ORDER BY ano"
        ).fetchall()
    finally:
        con.close()
    obtido = {ano: int(n) for ano, n in por_ano}
    assert obtido == M8_ATIPICOS_POR_ANO
    assert sum(obtido.values()) == M8_ATIPICOS_TOTAL


def test_m8_per_capita_nacional(gold_db):
    """Per capita nacional com/sem atípicos (soma sobre soma), R$/hab.

    `com` vem das colunas do próprio mart (investimento_total / pop_informante);
    `sem` é reconstruído da silver (não há coluna de pop sem atípicos no mart),
    com o predicado de atípico replicado verbatim do mart 5 (D4/D28).
    """
    con = _ro(gold_db)
    try:
        # com atípicos, a partir das colunas do mart
        com = con.execute(
            f"SELECT ano, sum(investimento_total) / nullif(sum(pop_informante_investimento), 0) "
            f"FROM {M8} GROUP BY ano"
        ).fetchall()
        # sem atípicos, reconstruído da silver (fonte independente)
        sem = con.execute(
            """
            WITH m AS (
              SELECT s.ano, s.investimento_total_prestador AS inv, p.populacao_total_ibge AS pop
              FROM silver.municipio_agua_esgoto s
              JOIN silver.ibge_populacao_municipio p
                ON p.id_municipio = s.id_municipio AND p.ano = s.ano
              WHERE s.ano BETWEEN 2010 AND 2021
                AND s.investimento_total_prestador IS NOT NULL AND p.populacao_total_ibge > 0
            )
            SELECT ano, sum(inv) FILTER (WHERE NOT (inv / pop > 1000.0))
              / nullif(sum(pop) FILTER (WHERE NOT (inv / pop > 1000.0)), 0)
            FROM m GROUP BY ano
            """
        ).fetchall()
    finally:
        con.close()
    com = {ano: round(float(v), 2) for ano, v in com}
    sem = {ano: round(float(v), 2) for ano, v in sem}
    for ano, esperado in M8_PC_COM.items():
        assert com[ano] == esperado
    for ano, esperado in M8_PC_SEM.items():
        assert sem[ano] == esperado


def test_m8_rn_2019(gold_db):
    """RN 2019: 443,38 (com) → 218,91 (sem) R$/hab; o atípico derruba o outlier."""
    con = _ro(gold_db)
    try:
        com, sem, atip = con.execute(
            "SELECT investimento_per_capita_com_atipicos, "
            "investimento_per_capita_sem_atipicos, municipios_investimento_atipico "
            f"FROM {M8} WHERE ano = 2019 AND sigla_uf = 'RN'"
        ).fetchone()
    finally:
        con.close()
    assert round(float(com), 2) == M8_RN_2019_COM
    assert round(float(sem), 2) == M8_RN_2019_SEM
    assert float(sem) < float(com)
    assert int(atip) == 45


def test_m8_cross_mart5(gold_db):
    """Consistência interna (mesma silver): mart 8 = mart 5 por (ano, sigla_uf).

    Trava a regra do atípico (D4/D28) contra deriva — não é validação externa.
    Σinv, investimento_total_sem_atipicos e municipios_investimento_atipico
    devem bater exatamente com o mart 5 na janela 2010–2021.
    """
    con = _ro(gold_db)
    try:
        divergentes = con.execute(
            f"""
            SELECT count(*)
            FROM {M8} a
            JOIN {M5} f USING (ano, sigla_uf)
            WHERE f.ano BETWEEN 2010 AND 2021
              AND (a.investimento_total IS DISTINCT FROM f.investimento_total
                OR a.investimento_total_sem_atipicos
                     IS DISTINCT FROM f.investimento_total_sem_atipicos
                OR a.municipios_investimento_atipico
                     <> f.municipios_investimento_atipico)
            """
        ).fetchone()[0]
        pares = con.execute(
            f"SELECT count(*) FROM {M8} a JOIN {M5} f USING (ano, sigla_uf) "
            "WHERE f.ano BETWEEN 2010 AND 2021"
        ).fetchone()[0]
    finally:
        con.close()
    assert divergentes == 0
    assert pares == M8_LINHAS


def test_m8_denominador_universo_comum(gold_db):
    """D31: o denominador é a pop dos INFORMANTES, não a de todos os municípios.

    Falha se o denominador passar a incluir os não-informantes (a pop informante
    se aproximaria dos 5.570 e o per capita 2021 cairia de 75,82 para 71,71).
    """
    con = _ro(gold_db)
    try:
        pop_inf_2021 = con.execute(
            f"SELECT sum(pop_informante_investimento) FROM {M8} WHERE ano = 2021"
        ).fetchone()[0]
        # pop de TODOS os municípios (DTB ∩ pop) em 2021 — fonte independente
        pop_todos_2021 = con.execute(
            """
            SELECT sum(p.populacao_total_ibge)
            FROM silver.ibge_dtb_municipio d
            JOIN silver.ibge_populacao_municipio p ON p.id_municipio = d.id_municipio
            WHERE p.ano = 2021
            """
        ).fetchone()[0]
        # o per capita do mart usa a pop informante (universo comum)
        pc_2021 = con.execute(
            f"SELECT sum(investimento_total) / nullif(sum(pop_informante_investimento), 0) "
            f"FROM {M8} WHERE ano = 2021"
        ).fetchone()[0]
        # o que daria se o denominador fosse a pop de TODOS (contrafactual)
        inv_2021 = con.execute(
            f"SELECT sum(investimento_total) FROM {M8} WHERE ano = 2021"
        ).fetchone()[0]
    finally:
        con.close()
    assert int(pop_inf_2021) == M8_POP_INFORMANTE_2021
    assert int(pop_todos_2021) == M8_POP_TODOS_2021
    # o denominador do mart é estritamente menor que a pop total
    assert pop_inf_2021 < pop_todos_2021
    # per capita com universo comum = 75,82 (não 71,71 de todos)
    assert round(float(pc_2021), 2) == 75.82
    assert round(float(inv_2021) / float(pop_todos_2021), 2) == 71.71


def test_m8_sql_sem_rascunho():
    """O SQL do mart 8 não traz marcadores de rascunho (TODO/FIXME/XXX/rascunho)."""
    import pathlib

    sql = (
        pathlib.Path(gold_mod.__file__).resolve().parent.parent
        / "sql"
        / "gold"
        / "08_investimento_per_capita_uf_ano.sql"
    ).read_text(encoding="utf-8")
    for marcador in ("TODO", "FIXME", "XXX", "rascunho", "placeholder"):
        assert marcador.lower() not in sql.lower()


# ===========================================================================
# Mart 9 — gold.atendimento_vs_pib_2021 (spec-gold.md §2, ficha Mart 9)
# D2/D15/D17/D28/D32. Grão: município, 2021. Universo: SNIS água urbana +
# PIB + pop = 5.302. Expectativas confirmadas no MCP/SELECT (2026-11-08).
# ===========================================================================

M9 = "gold.atendimento_vs_pib_2021"

M9_LINHAS = 5_302
M9_INFORMANTES_ESGOTO = 2_771
M9_SIGMA_POP_5570 = 213_317_639  # Σ pop IBGE 2021 (todos os 5.570)
M9_PPC_NACIONAL = 42_247.52  # Σ PIB × 1000 / Σ pop (5.570), R$/hab
M9_AGUA_NAC_2021 = 93.4469  # raw (inclui >100%); bate com o mart 1 (93,4%)
M9_ESGOTO_INFORMANTES_2021 = 72.4695  # raw, entre informantes (num E den)
M9_A100_AGUA = 18  # cobertura água > 100% (= exclusões A2 do mart 1 em 2021)
M9_A100_ESGOTO = 7  # cobertura esgoto > 100%
M9_ATIPICOS_2021 = 5  # investimento_atipico (= mart 5, ano 2021)
M9_FORA_UNIVERSO = 268  # municípios com pop+PIB sem água urbana informada
M9_FORA_POP = 3_304_102  # população desses 268 (Σ pop 5570 − Σ pop 5302)


def test_m9_linhas_pk_colunas(gold_db):
    """5.302 linhas, PK id_municipio única, 13 colunas."""
    con = _ro(gold_db)
    try:
        linhas, pk = con.execute(
            f"SELECT count(*), count(DISTINCT id_municipio) FROM {M9}"
        ).fetchone()
        cols = con.execute(
            "SELECT count(*) FROM duckdb_columns() "
            "WHERE schema_name = 'gold' AND table_name = 'atendimento_vs_pib_2021'"
        ).fetchone()[0]
    finally:
        con.close()
    assert linhas == M9_LINHAS
    assert pk == M9_LINHAS  # PK única
    assert cols == 13


def test_m9_conversao_pib_per_capita(gold_db):
    """D15: PIB em Mil Reais × 1000; PIB per capita nacional = R$ 42.247,52.

    Reconstruído da silver (Σ PIB × 1000 / Σ pop, 5.570 municípios), fonte
    independente do mart; e Σ pop dos 5.570 = 213.317.639.
    """
    con = _ro(gold_db)
    try:
        sigma_pop, ppc = con.execute(
            """
            SELECT sum(po.populacao_total_ibge),
                   sum(p.pib_municipio) * 1000.0 / sum(po.populacao_total_ibge)
            FROM silver.ibge_pib_municipio p
            JOIN silver.ibge_populacao_municipio po USING (id_municipio)
            WHERE p.ano = 2021 AND po.ano = 2021
            """
        ).fetchone()
        # sanidade da coluna do mart: PIB per capita de SP (3550308)
        ppc_sp = con.execute(
            f"SELECT pib_per_capita FROM {M9} WHERE id_municipio = '3550308'"
        ).fetchone()[0]
    finally:
        con.close()
    assert int(sigma_pop) == M9_SIGMA_POP_5570
    assert round(float(ppc), 2) == M9_PPC_NACIONAL
    # SP: 828.980.747 Mil Reais × 1000 / pop IBGE -> R$/hab plausível (> 60 mil)
    assert ppc_sp > 60_000


def test_m9_sem_pib_negativo_2021(gold_db):
    """D17: 0 PIB per capita negativo em 2021 (Guamaré voltou a positivo)."""
    con = _ro(gold_db)
    try:
        neg = con.execute(
            f"SELECT count(*) FROM {M9} WHERE pib_per_capita < 0"
        ).fetchone()[0]
    finally:
        con.close()
    assert neg == 0


def test_m9_agua_nacional_2021(gold_db):
    """Água urbana nacional (raw, Σ/Σ sobre os 5.302) = 93,45%; bate com o mart 1.

    Reconstruído da silver (universo do mart 9); inclui as linhas > 100% (D32),
    como o valor do mart é preservado sem clamp.
    """
    con = _ro(gold_db)
    try:
        agua = con.execute(
            """
            SELECT 100.0 * sum(s.populacao_urbana_atendida_agua)
                 / sum(s.populacao_urbana)
            FROM silver.municipio_agua_esgoto s
            JOIN silver.ibge_pib_municipio p
              ON p.id_municipio = s.id_municipio AND p.ano = 2021
            WHERE s.ano = 2021 AND s.populacao_urbana > 0
              AND s.populacao_urbana_atendida_agua IS NOT NULL
            """
        ).fetchone()[0]
    finally:
        con.close()
    assert round(float(agua), 4) == M9_AGUA_NAC_2021
    assert round(float(agua), 1) == 93.4  # mesmo nacional do mart 1


def test_m9_esgoto_entre_informantes_bate_mart1(gold_db):
    """Esgoto urbano é 'entre informantes' (2.771 de 5.302); mesmo viés do mart 1.

    - O nacional raw do mart 9 (inclui >100%) = 72,47%.
    - Na MESMA convenção do mart 1 (exclui atendida > residente), o nacional do
      mart 9 (universo 5.302) e o do mart 1 (universo total) coincidem — a prova
      de que ambos medem só entre informantes de esgoto. PENDÊNCIA registrada na
      ficha: o % de esgoto urbano cobre só os informantes, não toda a população
      urbana (o mart 1 NÃO é reaberto aqui).
    """
    con = _ro(gold_db)
    try:
        informantes = con.execute(
            f"SELECT count(*) FROM {M9} WHERE informou_esgoto"
        ).fetchone()[0]
        # raw, entre informantes (num E den não nulos), reconstruído da silver
        esg_raw = con.execute(
            """
            SELECT 100.0 * sum(num) / sum(den) FROM (
              SELECT s.populacao_urbana_atendida_esgoto AS num,
                     s.populacao_urbana_residente_esgoto AS den
              FROM silver.municipio_agua_esgoto s
              JOIN silver.ibge_pib_municipio p
                ON p.id_municipio = s.id_municipio AND p.ano = 2021
              WHERE s.ano = 2021 AND s.populacao_urbana > 0
                AND s.populacao_urbana_atendida_agua IS NOT NULL
                AND s.populacao_urbana_atendida_esgoto IS NOT NULL
                AND s.populacao_urbana_residente_esgoto IS NOT NULL)
            """
        ).fetchone()[0]
        # convenção do mart 1 (exclui a2) — mart 9 (universo 5.302)
        esg_m9_excl = con.execute(
            """
            SELECT 100.0 * sum(num) / sum(den) FROM (
              SELECT s.populacao_urbana_atendida_esgoto AS num,
                     s.populacao_urbana_residente_esgoto AS den
              FROM silver.municipio_agua_esgoto s
              JOIN silver.ibge_pib_municipio p
                ON p.id_municipio = s.id_municipio AND p.ano = 2021
              WHERE s.ano = 2021 AND s.populacao_urbana > 0
                AND s.populacao_urbana_atendida_agua IS NOT NULL
                AND s.populacao_urbana_atendida_esgoto IS NOT NULL
                AND s.populacao_urbana_residente_esgoto IS NOT NULL
                AND s.populacao_urbana_atendida_esgoto <= s.populacao_urbana_residente_esgoto)
            """
        ).fetchone()[0]
        # convenção do mart 1 — universo total (o próprio mart 1)
        esg_m1_excl = con.execute(
            """
            SELECT 100.0 * sum(num) / sum(den) FROM (
              SELECT s.populacao_urbana_atendida_esgoto AS num,
                     s.populacao_urbana_residente_esgoto AS den
              FROM silver.municipio_agua_esgoto s
              JOIN silver.ibge_dtb_municipio d ON d.id_municipio = s.id_municipio
              WHERE s.ano = 2021
                AND s.populacao_urbana_atendida_esgoto IS NOT NULL
                AND s.populacao_urbana_residente_esgoto IS NOT NULL
                AND s.populacao_urbana_atendida_esgoto <= s.populacao_urbana_residente_esgoto)
            """
        ).fetchone()[0]
    finally:
        con.close()
    assert informantes == M9_INFORMANTES_ESGOTO
    assert round(float(esg_raw), 4) == M9_ESGOTO_INFORMANTES_2021
    # mesmo viés: na convenção do mart 1, mart 9 e mart 1 batem (≤ 0,01 pp)
    assert abs(float(esg_m9_excl) - float(esg_m1_excl)) < 0.01


def test_m9_cobertura_acima_100_sinalizada(gold_db):
    """D32: cobertura > 100% preservada no valor e sinalizada (18 água, 7 esgoto).

    A flag casa exatamente com o valor bruto (> 100 <=> flag verdadeira).
    """
    con = _ro(gold_db)
    try:
        a100_agua, a100_esg = con.execute(
            f"""
            SELECT count(*) FILTER (WHERE cobertura_urbana_agua_acima_100),
                   count(*) FILTER (WHERE cobertura_urbana_esgoto_acima_100)
            FROM {M9}
            """
        ).fetchone()
        # identidade flag <=> valor > 100 (valor preservado, sem clamp)
        incoerentes = con.execute(
            f"""
            SELECT count(*) FROM {M9}
            WHERE cobertura_urbana_agua_acima_100 <> (cobertura_urbana_agua > 100.0)
               OR coalesce(cobertura_urbana_esgoto_acima_100
                           <> (cobertura_urbana_esgoto > 100.0), false)
            """
        ).fetchone()[0]
        maior_agua = con.execute(
            f"SELECT max(cobertura_urbana_agua) FROM {M9}"
        ).fetchone()[0]
    finally:
        con.close()
    assert a100_agua == M9_A100_AGUA
    assert a100_esg == M9_A100_ESGOTO
    assert incoerentes == 0
    assert maior_agua > 100.0  # valor original mantido (sem clamp)


def test_m9_esgoto_nulo_para_nao_informante(gold_db):
    """Esgoto nulo (não zero) para quem não informa; informou_esgoto coerente."""
    con = _ro(gold_db)
    try:
        incoerentes = con.execute(
            f"""
            SELECT count(*) FROM {M9}
            WHERE informou_esgoto <> (cobertura_urbana_esgoto IS NOT NULL)
            """
        ).fetchone()[0]
        nulos = con.execute(
            f"SELECT count(*) FROM {M9} WHERE cobertura_urbana_esgoto IS NULL"
        ).fetchone()[0]
    finally:
        con.close()
    assert incoerentes == 0
    assert nulos == M9_LINHAS - M9_INFORMANTES_ESGOTO


def test_m9_investimento_atipico_igual_mart5(gold_db):
    """D28: investimento_atipico com o predicado exato do mart 5; 2021 = 5 casos."""
    con = _ro(gold_db)
    try:
        m9 = con.execute(
            f"SELECT count(*) FILTER (WHERE investimento_atipico) FROM {M9}"
        ).fetchone()[0]
        m5 = con.execute(
            "SELECT sum(municipios_investimento_atipico) "
            "FROM gold.financeiro_uf_ano WHERE ano = 2021"
        ).fetchone()[0]
    finally:
        con.close()
    assert m9 == M9_ATIPICOS_2021
    assert int(m5) == M9_ATIPICOS_2021  # mesmo número do mart 5 em 2021


def test_m9_fora_do_universo(gold_db):
    """268 municípios com pop+PIB mas sem água urbana informada = 3.304.102 hab."""
    con = _ro(gold_db)
    try:
        munis, pop = con.execute(
            """
            WITH snis AS (
              SELECT DISTINCT id_municipio FROM silver.municipio_agua_esgoto
              WHERE ano = 2021 AND populacao_urbana > 0
                AND populacao_urbana_atendida_agua IS NOT NULL)
            SELECT count(*), sum(po.populacao_total_ibge)
            FROM silver.ibge_populacao_municipio po
            JOIN silver.ibge_pib_municipio p
              ON p.id_municipio = po.id_municipio AND p.ano = 2021
            WHERE po.ano = 2021
              AND po.id_municipio NOT IN (SELECT id_municipio FROM snis)
            """
        ).fetchone()
    finally:
        con.close()
    assert munis == M9_FORA_UNIVERSO
    assert int(pop) == M9_FORA_POP


def test_m9_sql_sem_rascunho():
    """O SQL do mart 9 não traz marcadores de rascunho (TODO/FIXME/XXX/rascunho)."""
    import pathlib

    sql = (
        pathlib.Path(gold_mod.__file__).resolve().parent.parent
        / "sql"
        / "gold"
        / "09_atendimento_vs_pib_2021.sql"
    ).read_text(encoding="utf-8")
    for marcador in ("TODO", "FIXME", "XXX", "rascunho", "placeholder"):
        assert marcador.lower() not in sql.lower()


# ===========================================================================
# Mart 10 — gold.avanco_por_renda_painel (spec-gold.md §2, ficha Mart 10)
# D33 (água-only + medida principal), D19/D24 (painel 4.472), D15/D17.
# Grão: (quartil_pib, ano), ano ∈ {2010, 2021} = 8 linhas. Painel urbano de água
# fixo = 4.472; quartil ntile(4) nacional base 2021, fixo. Valores confirmados
# no MCP/SELECT (2026-11-08).
# ===========================================================================

M10 = "gold.avanco_por_renda_painel"

M10_LINHAS = 8
M10_PAINEL = 4_472
M10_FORA = 1_098
M10_POR_QUARTIL = 1_118
M10_PAINEL_SEM_A2 = 4_431  # = mart 4 (4.472 − 41 violações A2)
M10_SIGMA_POP_5570 = 213_317_639  # Σ pop IBGE 2021 (nacional)

# CTE do painel + quartil, reconstruído da silver (fonte independente do mart).
_M10_BASE = """
WITH painel AS (
  SELECT id_municipio FROM silver.municipio_agua_esgoto
  WHERE ano BETWEEN 2010 AND 2021
    AND populacao_urbana_atendida_agua IS NOT NULL
    AND populacao_urbana IS NOT NULL
  GROUP BY id_municipio HAVING count(DISTINCT ano) = 12
),
per_capita AS (
  SELECT p.id_municipio,
         pib.pib_municipio * 1000.0 / nullif(po.populacao_total_ibge, 0) AS ppc
  FROM painel p
  JOIN silver.ibge_pib_municipio pib ON pib.id_municipio = p.id_municipio AND pib.ano = 2021
  JOIN silver.ibge_populacao_municipio po ON po.id_municipio = p.id_municipio AND po.ano = 2021
),
quartis AS (
  SELECT id_municipio, ppc, ntile(4) OVER (ORDER BY ppc) AS quartil_pib FROM per_capita
)
"""

# cobertura (2010, 2021) e cortes ppc (min, max) confirmados, por quartil.
M10_COB = {
    1: (80.0312, 82.6306),
    2: (86.3666, 87.1560),
    3: (91.1842, 92.8405),
    4: (96.7898, 97.8490),
}
M10_VAR_PP = {1: 2.5994, 2: 0.7894, 3: 1.6563, 4: 1.0592}
M10_RED_DEF = {1: 13.0174, 2: 5.7900, 3: 18.7883, 4: 32.9942}
M10_PPC_CORTES = {
    1: (5_731, 13_140),
    2: (13_144, 23_850),
    3: (23_863, 40_996),
    4: (41_005, 920_828),
}
M10_PAINEL_COB = (92.1737, 93.5229)  # cobertura do painel inteiro (2010, 2021)


def test_m10_linhas_pk_colunas(gold_db):
    """8 linhas, PK (quartil_pib, ano) única, 6 colunas."""
    con = _ro(gold_db)
    try:
        linhas, pk = con.execute(
            f"SELECT count(*), count(DISTINCT (quartil_pib, ano)) FROM {M10}"
        ).fetchone()
        cols = con.execute(
            "SELECT count(*) FROM duckdb_columns() "
            "WHERE schema_name = 'gold' AND table_name = 'avanco_por_renda_painel'"
        ).fetchone()[0]
        anos = con.execute(f"SELECT DISTINCT ano FROM {M10} ORDER BY ano").fetchall()
    finally:
        con.close()
    assert linhas == M10_LINHAS
    assert pk == M10_LINHAS  # PK (quartil_pib, ano) única
    assert cols == 6
    assert [a[0] for a in anos] == [2010, 2021]


def test_m10_painel_4472_e_fora(gold_db):
    """Σ municipios_painel por ano = 4.472; 1.098 fora; Σ pop = 213.317.639."""
    con = _ro(gold_db)
    try:
        por_ano = con.execute(
            f"SELECT ano, sum(municipios_painel) FROM {M10} GROUP BY ano ORDER BY ano"
        ).fetchall()
        n_painel = con.execute(_M10_BASE + "SELECT count(*) FROM painel").fetchone()[0]
        sigma_pop, fora = con.execute(
            _M10_BASE
            + """
            SELECT sum(po.populacao_total_ibge),
                   count(*) FILTER (WHERE po.id_municipio NOT IN (SELECT id_municipio FROM painel))
            FROM silver.ibge_populacao_municipio po WHERE po.ano = 2021
            """
        ).fetchone()
    finally:
        con.close()
    assert [v for _, v in por_ano] == [M10_PAINEL, M10_PAINEL]
    assert n_painel == M10_PAINEL
    assert int(sigma_pop) == M10_SIGMA_POP_5570
    assert fora == M10_FORA


def test_m10_quartis_1118_e_cortes(gold_db):
    """Cada quartil = 1.118 municípios; cortes do PIB per capita confirmados."""
    con = _ro(gold_db)
    try:
        por_ano = con.execute(
            f"SELECT quartil_pib, ano, municipios_painel FROM {M10} ORDER BY 1, 2"
        ).fetchall()
        cortes = con.execute(
            _M10_BASE + "SELECT quartil_pib, count(*), min(ppc), max(ppc) "
            "FROM quartis GROUP BY quartil_pib ORDER BY quartil_pib"
        ).fetchall()
    finally:
        con.close()
    # municipios_painel = 1.118 em toda linha (nos dois anos)
    for _, _, muni in por_ano:
        assert muni == M10_POR_QUARTIL
    for q, n, pmin, pmax in cortes:
        assert n == M10_POR_QUARTIL
        assert round(pmin) == M10_PPC_CORTES[q][0]
        assert round(pmax) == M10_PPC_CORTES[q][1]


def test_m10_cobertura_por_quartil(gold_db):
    """Cobertura urbana de água por quartil nos dois anos (soma/soma)."""
    con = _ro(gold_db)
    try:
        linhas = con.execute(
            f"SELECT quartil_pib, ano, cobertura_urbana_agua FROM {M10} ORDER BY 1, 2"
        ).fetchall()
    finally:
        con.close()
    for q, ano, cob in linhas:
        esperado = M10_COB[q][0] if ano == 2010 else M10_COB[q][1]
        assert cob == pytest.approx(esperado, abs=0.01)


def test_m10_avanco_pp_e_reducao_deficit(gold_db):
    """Medida principal (variacao_pp) e apoio (reducao_relativa_deficit) por quartil.

    Ambas são atributos do quartil: repetem-se idênticas nas duas linhas de ano
    (prova o quartil fixo — mesma composição em 2010 e 2021).
    """
    con = _ro(gold_db)
    try:
        linhas = con.execute(
            f"SELECT quartil_pib, ano, variacao_pp, reducao_relativa_deficit "
            f"FROM {M10} ORDER BY 1, 2"
        ).fetchall()
    finally:
        con.close()
    por_q = {}
    for q, ano, var, red in linhas:
        assert var == pytest.approx(M10_VAR_PP[q], abs=0.01)
        assert red == pytest.approx(M10_RED_DEF[q], abs=0.01)
        por_q.setdefault(q, []).append((var, red))
    # mesma medida nas duas linhas de ano de cada quartil (repetição = quartil fixo)
    for q, vals in por_q.items():
        assert len(vals) == 2
        assert vals[0] == vals[1]


def test_m10_painel_nacional_e_consistencia_var(gold_db):
    """Cobertura do painel inteiro (2010/2021) e variacao_pp = 2021 − 2010."""
    con = _ro(gold_db)
    try:
        cob10, cob21 = con.execute(
            _M10_BASE
            + """
            SELECT 100.0 * sum(CASE WHEN s.ano = 2010 THEN s.populacao_urbana_atendida_agua END)
                         / sum(CASE WHEN s.ano = 2010 THEN s.populacao_urbana END),
                   100.0 * sum(CASE WHEN s.ano = 2021 THEN s.populacao_urbana_atendida_agua END)
                         / sum(CASE WHEN s.ano = 2021 THEN s.populacao_urbana END)
            FROM quartis q
            JOIN silver.municipio_agua_esgoto s ON s.id_municipio = q.id_municipio
            WHERE s.ano IN (2010, 2021)
            """
        ).fetchone()
        linhas = con.execute(
            f"SELECT quartil_pib, "
            f"max(CASE WHEN ano=2021 THEN cobertura_urbana_agua END) "
            f"- max(CASE WHEN ano=2010 THEN cobertura_urbana_agua END), "
            f"max(variacao_pp) FROM {M10} GROUP BY quartil_pib"
        ).fetchall()
    finally:
        con.close()
    assert cob10 == pytest.approx(M10_PAINEL_COB[0], abs=0.01)
    assert cob21 == pytest.approx(M10_PAINEL_COB[1], abs=0.01)
    # a variacao_pp da tabela = diferença das coberturas das duas linhas
    for _, dif, var in linhas:
        assert var == pytest.approx(dif, abs=1e-9)


def test_m10_pib_negativo_quartil1_zero_2021(gold_db):
    """D17: 0 PIB per capita negativo no Q1 em base 2021 (regra registrada)."""
    con = _ro(gold_db)
    try:
        negativos = con.execute(
            _M10_BASE + "SELECT count(*) FROM quartis WHERE quartil_pib = 1 AND ppc < 0"
        ).fetchone()[0]
    finally:
        con.close()
    assert negativos == 0


def test_m10_painel_sem_a2_igual_mart4(gold_db):
    """Painel menos as violações A2 = 4.431 = linhas do mart 4 (sensibilidade)."""
    con = _ro(gold_db)
    try:
        sem_a2 = con.execute(
            _M10_BASE
            + """
            , a2 AS (
              SELECT s.id_municipio,
                bool_or(s.ano IN (2010, 2021)
                        AND s.populacao_urbana_atendida_agua > s.populacao_urbana) AS viola
              FROM silver.municipio_agua_esgoto s
              JOIN painel p ON p.id_municipio = s.id_municipio
              WHERE s.ano IN (2010, 2021) GROUP BY s.id_municipio
            )
            SELECT count(*) FROM a2 WHERE NOT viola
            """
        ).fetchone()[0]
        mart4 = con.execute(
            "SELECT count(*) FROM gold.ranking_atendimento_variacao"
        ).fetchone()[0]
    finally:
        con.close()
    assert sem_a2 == M10_PAINEL_SEM_A2
    assert mart4 == M10_PAINEL_SEM_A2


def test_m10_sql_sem_rascunho():
    """O SQL do mart 10 não traz marcadores de rascunho (TODO/FIXME/XXX/rascunho)."""
    import pathlib

    sql = (
        pathlib.Path(gold_mod.__file__).resolve().parent.parent
        / "sql"
        / "gold"
        / "10_avanco_por_renda_painel.sql"
    ).read_text(encoding="utf-8")
    for marcador in ("TODO", "FIXME", "XXX", "rascunho", "placeholder"):
        assert marcador.lower() not in sql.lower()
