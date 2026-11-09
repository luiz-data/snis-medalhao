"""Testes do app Streamlit via streamlit.testing.v1.AppTest (sem navegador).

AppTest não renderiza o Altair; testamos valores/notas dos cartões (st.metric,
st.caption via markdown), o domínio do seletor de ano, o erro sem banco, o filtro
de Região (só no Detalhe) e a contagem de elementos. Banco sintético em tmp_path;
nunca toca no snis.duckdb do projeto.
"""

import re
from pathlib import Path

import duckdb
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _gold_sintetica(tmp_path):
    """snis.duckdb temporário com os 7 marts que o app lê (poucas linhas)."""
    banco = tmp_path / "snis.duckdb"
    con = duckdb.connect(str(banco))
    con.execute("CREATE SCHEMA gold")
    con.execute(
        """
        CREATE TABLE gold.kpis_brasil AS SELECT * FROM (VALUES
          (2020, 92.10, 80.98, 45.37, 60.63, 67.74, 39.30, 158.2,
           34703025, 99622047, 19.03, 54.64, 18, 7672158349.94, 44.26),
          (2021, 93.33, 84.20, 55.81, 56.02, 80.33, 36.86, 151.3,
           33285121, 92879110, 15.84, 44.19, 258, 15297535452.19, 75.82)
        ) AS t(ano, cobertura_urbana_agua_br, cobertura_agua_in055_br,
          cobertura_esgoto_in056_br, indice_coleta_esgoto_br,
          indice_tratamento_esgoto_br, perdas_in049_br, consumo_per_capita_br,
          pop_sem_agua_br, pop_sem_esgoto_br, pct_sem_agua_br, pct_sem_esgoto_br,
          municipios_sem_info_agua_br, investimento_total_br,
          investimento_per_capita_br)
        """
    )
    con.execute(
        """
        CREATE TABLE gold.esgoto_coleta_tratamento_ano AS SELECT * FROM (VALUES
          (1998, 1578.4, 97.7, FALSE, 233), (2010, 60.63, 67.74, TRUE, 1762),
          (2021, 56.02, 80.33, TRUE, 2800)
        ) AS t(ano, indice_coleta_esgoto, indice_tratamento_esgoto, serie_robusta,
               municipios_informantes_coleta)
        """
    )
    con.execute(
        """
        CREATE TABLE gold.atendimento_porte_ano AS SELECT * FROM (VALUES
          ('1_ate_5mil', 2021, 72.20, 23.60),
          ('6_acima500mil', 2021, 94.47, 77.15),
          ('1_ate_5mil', 2020, 71.0, 22.0)
        ) AS t(faixa_porte, ano, cobertura_agua, cobertura_esgoto)
        """
    )
    con.execute(
        """
        CREATE TABLE gold.avanco_por_renda_painel AS SELECT * FROM (VALUES
          (1, 2010, 80.03), (1, 2021, 82.63), (4, 2010, 96.79), (4, 2021, 97.85)
        ) AS t(quartil_pib, ano, cobertura_urbana_agua)
        """
    )
    con.execute(
        """
        CREATE TABLE gold.ranking_atendimento_variacao AS SELECT * FROM (VALUES
          ('3550308', 'São Paulo', 'Sudeste', 90.0, 95.0, 5.0, 1, FALSE),
          ('2304400', 'Ceará', 'Nordeste', 70.0, 80.0, 10.0, 2, FALSE)
        ) AS t(id_municipio, nome_uf, nome_regiao, cobertura_2010, cobertura_2021,
               variacao_pp, posicao, variacao_extrema)
        """
    )
    con.execute(
        """
        CREATE TABLE gold.atendimento_vs_pib_2021 AS SELECT * FROM (VALUES
          (40000.0, 95.0, FALSE, 'Sudeste'), (12000.0, 70.0, TRUE, 'Nordeste')
        ) AS t(pib_per_capita, cobertura_urbana_agua, investimento_atipico,
               nome_regiao)
        """
    )
    con.execute(
        """
        CREATE TABLE gold.financeiro_uf_ano AS SELECT * FROM (VALUES
          (2021, 'São Paulo', 'Sudeste', 3000000000.00),
          (2021, 'Ceará', 'Nordeste', 500000000.00)
        ) AS t(ano, nome_uf, nome_regiao, investimento_total)
        """
    )
    con.close()
    return banco


def _run(tmp_path, monkeypatch):
    banco = _gold_sintetica(tmp_path)
    monkeypatch.setenv("SNIS_BANCO", str(banco))
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at


def _markdowns(at):
    """Junta markdown + caption + write (st.caption não entra em at.markdown)."""
    partes = []
    for attr in ("markdown", "caption", "text"):
        for e in getattr(at, attr, []):
            partes.append(getattr(e, "value", ""))
    return " ".join(partes)


def test_app_sobe_sem_erro(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    assert at.exception == []
    assert at.error == []


def test_cartoes_valores(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Água (IN055)"] == "84,20%"
    assert metricas["Esgoto (IN056)"] == "55,81%"
    assert metricas["Perdas (IN049)"] == "36,86%"
    assert metricas["Investimento per capita"] == "R$ 75,82/hab"
    assert metricas["Sem água (piso)"] == "33,3 mi · 15,84%"
    assert metricas["Sem esgoto"] == "92,9 mi · 44,19%"
    assert metricas["Água urbana (mart 1)"] == "93,33%"
    # 6 cartões da Faixa A + 1 água urbana no Detalhe
    assert len(at.metric) == 7


def test_cartoes_notas_obrigatorias(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    md = _markdowns(at)
    assert "piso" in md.lower()  # sem água e sem esgoto dizem "piso"
    assert "258" in md  # número de 2021 lido do mart
    assert "por rede coletora; fossa conta como sem esgoto" in md
    assert "entre os municípios que declararam investimento" in md
    assert "pode diferir de valores divulgados" in md  # perdas, sem número publicado
    assert "diferença não reconciliada" in md
    # nota de perdas não cita número publicado
    assert "39,3" not in md and "40,3" not in md and "40,1" not in md


def test_nota_informantes(tmp_path, monkeypatch):
    """E12: a nota exibe o número de informantes (mart 2), lido do mart."""
    at = _run(tmp_path, monkeypatch)
    md = _markdowns(at)
    assert "Informantes de coleta (mart 2)" in md
    assert "1.762" in md and "2.800" in md  # anos robustos (1998 omitido)


def test_seletor_ano_dominio_sem_2022(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    ano_sel = next(s for s in at.selectbox if s.label == "Ano")
    assert list(ano_sel.options) == [str(a) for a in range(2010, 2022)]
    assert "2022" not in [str(o) for o in ano_sel.options]
    assert "urbanos só até 2021" in _markdowns(at)


def test_regiao_so_no_detalhe(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    labels = [s.label for s in at.selectbox]
    assert "Ano" in labels
    assert "Região/UF" in labels
    md = _markdowns(at)
    assert "Região vale só nesta aba" in md


def test_filtro_regiao_altera_dados(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    reg = next(s for s in at.selectbox if s.label == "Região/UF")
    # Sem filtro: ranking tem 2 linhas; filtrando Sudeste, 1 linha.
    assert at.dataframe[0].value.shape[0] == 2
    reg.set_value("Sudeste").run()
    assert at.dataframe[0].value.shape[0] == 1


def test_botao_recarregar_limpa_cache(tmp_path, monkeypatch):
    at = _run(tmp_path, monkeypatch)
    botao = next(b for b in at.button if "Recarregar" in b.label)
    botao.click().run()
    assert at.exception == []  # clicar limpa o cache sem erro


def test_erro_sem_banco(tmp_path, monkeypatch):
    monkeypatch.setenv("SNIS_BANCO", str(tmp_path / "nao_existe.duckdb"))
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert len(at.error) == 1
    assert "pipeline.gold" in at.error[0].value
    # st.stop() impede os cartões de aparecerem
    assert at.metric == []


def test_erro_mart_ausente(tmp_path, monkeypatch):
    """Banco existe mas sem um mart -> erro com o comando de execução."""
    banco = _gold_sintetica(tmp_path)
    con = duckdb.connect(str(banco))
    con.execute("DROP TABLE gold.kpis_brasil")
    con.close()
    monkeypatch.setenv("SNIS_BANCO", str(banco))
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert len(at.error) == 1
    assert "kpis_brasil" in at.error[0].value
    assert "uv run python -m pipeline.gold" in at.error[0].value


def test_app_sem_operacoes_proibidas():
    """Regra 7b: nada de agregação em app.py."""
    codigo = Path(APP).read_text(encoding="utf-8")
    proibidos = [r"\.sum\(", r"\.mean\(", r"\.groupby\(", r"\.merge\(", r"\.agg\("]
    assert [p for p in proibidos if re.search(p, codigo)] == []
