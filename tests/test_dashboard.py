"""Testes unitários do dashboard (painel.py + formato.py), sem Streamlit.

Dado inventado em tmp_path com DuckDB real; nunca toca no snis.duckdb do projeto.
Valores de formatação conferidos à mão. Sem skip/xfail, sem teste sem assert, sem
pytest.approx em dinheiro (igualdade exata de string formatada).
"""

import re
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import pytest

import formato as fmt
import painel

# --- Infra: gold temporária -------------------------------------------------


def _gold_kpis(tmp_path):
    """Cria um snis.duckdb temporário com gold.kpis_brasil (2 linhas)."""
    banco = tmp_path / "snis.duckdb"
    con = duckdb.connect(str(banco))
    con.execute("CREATE SCHEMA gold")
    con.execute(
        """
        CREATE TABLE gold.kpis_brasil AS
        SELECT * FROM (VALUES
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
    con.close()
    return banco


# --- formato.py -------------------------------------------------------------


def test_brl_valor_grande():
    assert fmt.brl(15297535452.19) == "R$ 15.297.535.452,19"


def test_brl_per_capita():
    assert fmt.brl(75.82) == "R$ 75,82"


def test_pct_duas_casas():
    assert fmt.pct(44.19) == "44,19%"
    assert fmt.pct(36.86) == "36,86%"


def test_inteiro_milhar():
    assert fmt.inteiro(258) == "258"
    assert fmt.inteiro(213317639) == "213.317.639"


def test_milhao_uma_casa():
    assert fmt.milhao(92879110) == "92,9 mi"
    assert fmt.milhao(33285121) == "33,3 mi"


def test_ausente_vira_traco():
    assert fmt.brl(None) == "—"
    assert fmt.pct(None) == "—"
    assert fmt.inteiro(None) == "—"
    assert fmt.milhao(None) == "—"
    assert fmt.pct(float("nan")) == "—"


def test_negativo_preserva_sinal():
    assert fmt.brl(-19046.0) == "R$ -19.046,00"
    assert fmt.pct(-2.44) == "-2,44%"


# --- painel.py: leitura só-gold, read-only ---------------------------------


def test_ler_kpis_retorna_linhas(tmp_path):
    banco = _gold_kpis(tmp_path)
    df = painel.ler("kpis_brasil", banco=banco)
    assert len(df) == 2
    assert "perdas_in049_br" in df.columns


def test_ler_mart_desconhecido_levanta(tmp_path):
    banco = _gold_kpis(tmp_path)
    with pytest.raises(ValueError):
        painel.ler("silver_qualquer", banco=banco)


def test_ler_kpis_ano_filtra(tmp_path):
    banco = _gold_kpis(tmp_path)
    df = painel.ler_kpis_ano(2021, banco=banco)
    assert len(df) == 1
    assert int(df.iloc[0]["ano"]) == 2021
    assert round(float(df.iloc[0]["perdas_in049_br"]), 2) == 36.86


def test_leitores_filtrados_por_ano_e_regiao(tmp_path):
    """ler_porte (ano), ler_financeiro (ano/região) e ler_detalhe (região)."""
    banco = tmp_path / "snis.duckdb"
    con = duckdb.connect(str(banco))
    con.execute("CREATE SCHEMA gold")
    con.execute(
        "CREATE TABLE gold.atendimento_porte_ano AS SELECT * FROM (VALUES "
        "('1_ate_5mil', 2021, 72.2, 23.6), ('1_ate_5mil', 2020, 71.0, 22.0)) "
        "AS t(faixa_porte, ano, cobertura_agua, cobertura_esgoto)"
    )
    con.execute(
        "CREATE TABLE gold.financeiro_uf_ano AS SELECT * FROM (VALUES "
        "(2021, 'SP', 'Sudeste', 3.0), (2021, 'CE', 'Nordeste', 1.0)) "
        "AS t(ano, nome_uf, nome_regiao, investimento_total)"
    )
    con.execute(
        "CREATE TABLE gold.ranking_atendimento_variacao AS SELECT * FROM (VALUES "
        "('1', 'SP', 'Sudeste', 1.0), ('2', 'CE', 'Nordeste', 2.0)) "
        "AS t(id_municipio, nome_uf, nome_regiao, variacao_pp)"
    )
    con.close()
    assert len(painel.ler_porte(2021, banco=banco)) == 1
    assert len(painel.ler_financeiro(2021, banco=banco)) == 2
    assert len(painel.ler_financeiro(2021, regiao="Sudeste", banco=banco)) == 1
    assert len(painel.ler_detalhe("ranking", banco=banco)) == 2
    assert len(painel.ler_detalhe("ranking", regiao="Nordeste", banco=banco)) == 1
    with pytest.raises(ValueError):
        painel.ler_detalhe("fora_do_gold", banco=banco)


def test_conexao_somente_leitura(tmp_path):
    """A conexão de painel é read-only: escrever deve falhar."""
    banco = _gold_kpis(tmp_path)
    con = painel._conectar_ro(banco)
    try:
        with pytest.raises(duckdb.Error):
            con.execute("CREATE TABLE gold.x AS SELECT 1 AS a")
    finally:
        con.close()


# --- painel.py: resumo executivo (frases-modelo) ---------------------------


def test_frases_resumo_valores():
    kpis = {
        "ano": 2021,
        "pct_sem_esgoto_br": 44.19,
        "pop_sem_esgoto_br": 92879110,
        "pct_sem_agua_br": 15.84,
        "pop_sem_agua_br": 33285121,
        "municipios_sem_info_agua_br": 258,
        "cobertura_agua_in055_br": 84.20,
        "indice_tratamento_esgoto_br": 80.33,
        "indice_coleta_esgoto_br": 56.02,
        "perdas_in049_br": 36.86,
    }
    frases = painel.frases_resumo(kpis)
    assert frases[0] == (
        "Em 2021, 44,19% da população (92,9 mi) estava sem coleta de esgoto por rede."
    )
    assert frases[1] == (
        "15,84% (33,3 mi) sem água — número mínimo, fora 258 municípios sem informação."
    )
    assert frases[2] == "A cobertura de água (IN055) era 84,20% em 2021."
    assert frases[3] == (
        "O volume de esgoto coletado equivalia a 56,02% do volume de água "
        "consumido e 80,33% do coletado era tratado."
    )
    assert frases[4] == "As perdas de água na distribuição somavam 36,86% (IN049)."
    # Resumo sem explicação causal (regra 7j).
    causais = ("porque", "causa", "devido", "por isso")
    assert not any(t in f.lower() for f in frases for t in causais)


# --- painel.py: figuras Altair ---------------------------------------------


def test_grafico_serie_esgoto_titulo_e_spec():
    df = pd.DataFrame(
        {
            "ano": [2010, 2021],
            "indice_coleta_esgoto": [60.63, 56.02],
            "indice_tratamento_esgoto": [67.74, 80.33],
        }
    )
    g = painel.grafico_serie_esgoto(df)
    assert isinstance(g, alt.Chart)
    spec = g.to_dict()
    assert "SNIS" in spec["title"]
    assert "%" in spec["title"]


def test_grafico_porte_barras_agrupadas():
    df = pd.DataFrame(
        {
            "faixa_porte": ["1_ate_5mil", "6_acima500mil"],
            "cobertura_agua": [72.20, 94.47],
            "cobertura_esgoto": [23.60, 77.15],
        }
    )
    g = painel.grafico_porte(df, 2021)
    spec = g.to_dict()
    assert "2021" in spec["title"]
    assert "SNIS" in spec["title"]


def test_grafico_porte_legenda_texto_agua_esgoto():
    """Regra 7k: legenda em TEXTO 'Água'/'Esgoto' (cor nunca é o único significado)."""
    import json

    df = pd.DataFrame(
        {
            "faixa_porte": ["1_ate_5mil"],
            "cobertura_agua": [72.20],
            "cobertura_esgoto": [23.60],
        }
    )
    spec = json.dumps(painel.grafico_porte(df, 2021).to_dict(), ensure_ascii=False)
    assert "Água" in spec and "Esgoto" in spec


def test_ler_esgoto_robusto_exclui_acima_100(tmp_path):
    """A série exibida (robusta) não traz ano com índice de coleta/tratamento > 100%."""
    banco = tmp_path / "snis.duckdb"
    con = duckdb.connect(str(banco))
    con.execute("CREATE SCHEMA gold")
    con.execute(
        "CREATE TABLE gold.esgoto_coleta_tratamento_ano AS SELECT * FROM (VALUES "
        "(1998, 1578.4, 97.7, FALSE), (1999, 1609.2, 94.5, FALSE), "
        "(2006, 61.5, 61.8, TRUE), (2021, 56.02, 80.33, TRUE)) "
        "AS t(ano, indice_coleta_esgoto, indice_tratamento_esgoto, serie_robusta)"
    )
    con.close()
    df = painel.ler_esgoto_robusto(banco=banco)
    assert df["ano"].min() >= 2006
    assert df["serie_robusta"].all()
    assert (df["indice_coleta_esgoto"] <= 100).all()
    assert (df["indice_tratamento_esgoto"] <= 100).all()
    assert 1998 not in list(df["ano"]) and 1999 not in list(df["ano"])


def test_grafico_porte_rotulos_legiveis():
    """Códigos de faixa viram rótulos legíveis na camada de apresentação."""
    import json

    df = pd.DataFrame(
        {
            "faixa_porte": ["1_ate_5mil", "6_acima500mil"],
            "cobertura_agua": [72.20, 94.47],
            "cobertura_esgoto": [23.60, 77.15],
        }
    )
    spec = json.dumps(painel.grafico_porte(df, 2021).to_dict(), ensure_ascii=False)
    assert "Até 5 mil" in spec
    assert "Acima de 500 mil" in spec
    assert painel.PORTE_ORDEM[0] == "Até 5 mil"


def test_grafico_serie_legenda_texto_coleta_tratamento():
    import json

    df = pd.DataFrame(
        {
            "ano": [2021],
            "indice_coleta_esgoto": [56.02],
            "indice_tratamento_esgoto": [80.33],
        }
    )
    spec = json.dumps(painel.grafico_serie_esgoto(df).to_dict(), ensure_ascii=False)
    assert "Coleta" in spec and "Tratamento" in spec


def test_grafico_renda_tem_titulo():
    df = pd.DataFrame(
        {
            "quartil_pib": [1, 1, 4, 4],
            "ano": [2010, 2021, 2010, 2021],
            "cobertura_urbana_agua": [80.03, 82.63, 96.79, 97.85],
        }
    )
    g = painel.grafico_renda(df)
    assert "água" in g.to_dict()["title"]


def test_grafico_financeiro_nominal_no_titulo():
    df = pd.DataFrame(
        {"nome_uf": ["São Paulo", "Rio"], "investimento_total": [1.0e9, 5.0e8]}
    )
    g = painel.grafico_financeiro(df, 2021)
    assert "nominal" in g.to_dict()["title"].lower()


def test_grafico_renda_cobertura_5302_linhas():
    """D38: mart 9 tem 5.302 linhas (> 5.000). A spec Vega-Lite deve gerar sem erro."""
    n = 5302
    df = pd.DataFrame(
        {
            "pib_per_capita": [10000.0 + i for i in range(n)],
            "cobertura_urbana_agua": [90.0] * n,
            "investimento_atipico": [False] * n,
        }
    )
    g = painel.grafico_renda_cobertura(df)
    spec = g.to_dict()  # não pode levantar MaxRowsError (limite tratado, D38)
    # Os dados ficam inline em data.values ou em datasets (Altair decide); conta-os.
    if "values" in spec.get("data", {}):
        linhas = spec["data"]["values"]
    else:
        linhas = next(iter(spec["datasets"].values()))
    assert len(linhas) == n


# --- Regra 7b: sem operações proibidas em painel.py ------------------------


def test_painel_sem_operacoes_proibidas():
    """Nenhuma agregação na camada de tela (chamadas .sum(/.mean(/.groupby(/...)."""
    codigo = Path(painel.__file__).read_text(encoding="utf-8")
    proibidos = [r"\.sum\(", r"\.mean\(", r"\.groupby\(", r"\.merge\(", r"\.agg\("]
    achados = [p for p in proibidos if re.search(p, codigo)]
    assert achados == []
