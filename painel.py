"""Consultas e gráficos do dashboard SNIS (spec-dashboard.md §10).

Camada de dados + figuras, SEM Streamlit. Regras duras:
- lê SOMENTE o schema `gold`, em conexão **somente leitura**, abrindo e fechando
  a conexão a cada leitura (regra 7a);
- **sem cálculo na tela**: nenhuma agregação aqui (agrupamento/soma/média/junção) —
  todo número já vem agregado pela gold (regra 7b). As funções de gráfico só
  descrevem a figura; a reformatação para barras agrupadas é feita no Vega
  (`transform_fold`), não em pandas;
- todo gráfico carrega título com unidade, fonte e ano (regra 7h).

A conexão usa o caminho de `pipeline.db` (sobrescritível em teste via `banco`).
"""

import altair as alt

import formato as fmt
import pipeline.db as _db
import tema

P = tema.PALETA

# Mapa lógico -> tabela gold. É a ÚNICA porta de entrada: nada fora de `gold`.
MARTS = {
    "kpis_brasil": "gold.kpis_brasil",
    "esgoto_ano": "gold.esgoto_coleta_tratamento_ano",
    "porte": "gold.atendimento_porte_ano",
    "renda": "gold.avanco_por_renda_painel",
    "ranking": "gold.ranking_atendimento_variacao",
    "renda_pib": "gold.atendimento_vs_pib_2021",
    "financeiro": "gold.financeiro_uf_ano",
}

FONTE = "SNIS + IBGE"

# Rótulos legíveis das faixas de porte (camada de apresentação; a gold guarda o
# código). Ordem fixa do menor para o maior porte.
PORTE_LABEL = {
    "1_ate_5mil": "Até 5 mil",
    "2_5a20mil": "5 a 20 mil",
    "3_20a50mil": "20 a 50 mil",
    "4_50a100mil": "50 a 100 mil",
    "5_100a500mil": "100 a 500 mil",
    "6_acima500mil": "Acima de 500 mil",
}
PORTE_ORDEM = list(PORTE_LABEL.values())

# D38: o mart 9 (renda × PIB) tem 5.302 linhas, acima do limite padrão de 5.000
# do Altair. Tratamos o limite explicitamente para a dispersão renderizar sem
# MaxRowsError (coberto por teste). Afeta só a geração da spec Vega-Lite.
alt.data_transformers.disable_max_rows()


def _conectar_ro(banco=None):
    """Conexão DuckDB **somente leitura** (regra 7a)."""
    import duckdb

    caminho = str(banco) if banco is not None else str(_db.CAMINHO_BANCO)
    return duckdb.connect(caminho, read_only=True)


def ler(mart, banco=None):
    """Lê uma tabela da gold inteira. `mart` precisa estar em MARTS (só gold)."""
    if mart not in MARTS:
        raise ValueError(f"mart desconhecido ou fora do schema gold: {mart!r}")
    con = _conectar_ro(banco)
    try:
        return con.execute(f"SELECT * FROM {MARTS[mart]}").df()
    finally:
        con.close()


def ler_kpis_ano(ano, banco=None):
    """Linha única de `gold.kpis_brasil` para o ano (filtro, não agregação)."""
    con = _conectar_ro(banco)
    try:
        return con.execute("SELECT * FROM gold.kpis_brasil WHERE ano = ?", [ano]).df()
    finally:
        con.close()


def ler_esgoto_robusto(banco=None):
    """Mart 2 só na janela ROBUSTA (serie_robusta = true, >= 2006).

    Omite 1995–2005: nesses anos a série não é robusta (< ~1.000 informantes de
    coleta) e 1998/1999 têm índice de coleta acima de 100% (1.578%/1.609%),
    achatando o resto. Filtro em SQL, não na tela.
    """
    con = _conectar_ro(banco)
    try:
        return con.execute(
            "SELECT * FROM gold.esgoto_coleta_tratamento_ano "
            "WHERE serie_robusta ORDER BY ano"
        ).df()
    finally:
        con.close()


def ler_porte(ano, banco=None):
    """Mart 6 filtrado por ano (filtro em SQL, não agregação)."""
    con = _conectar_ro(banco)
    try:
        return con.execute(
            "SELECT * FROM gold.atendimento_porte_ano WHERE ano = ? "
            "ORDER BY faixa_porte",
            [ano],
        ).df()
    finally:
        con.close()


def ler_financeiro(ano, regiao=None, banco=None):
    """Mart 5 filtrado por ano e (opcional) região — filtros em SQL."""
    con = _conectar_ro(banco)
    try:
        if regiao and regiao != "Todas":
            return con.execute(
                "SELECT * FROM gold.financeiro_uf_ano WHERE ano = ? "
                "AND nome_regiao = ? ORDER BY investimento_total DESC",
                [ano, regiao],
            ).df()
        return con.execute(
            "SELECT * FROM gold.financeiro_uf_ano WHERE ano = ? "
            "ORDER BY investimento_total DESC",
            [ano],
        ).df()
    finally:
        con.close()


def ler_detalhe(mart, regiao=None, banco=None):
    """Lê um mart do Detalhe (ranking/renda_pib) com filtro opcional de região."""
    if mart not in MARTS:
        raise ValueError(f"mart desconhecido ou fora do schema gold: {mart!r}")
    con = _conectar_ro(banco)
    try:
        if regiao and regiao != "Todas":
            return con.execute(
                f"SELECT * FROM {MARTS[mart]} WHERE nome_regiao = ?", [regiao]
            ).df()
        return con.execute(f"SELECT * FROM {MARTS[mart]}").df()
    finally:
        con.close()


# --- Figuras Altair (recebem dados já agregados; devolvem alt.Chart) --------
# Fontes de nota/legenda >= 12 px (regra 7k); legenda sempre com TEXTO, nunca só
# cor. Cores vêm de tema.PALETA (fonte única).


def _config(ch):
    """Aplica fontes >= 12 px (eixos, legenda, título) a uma figura."""
    return (
        ch.configure_axis(labelFontSize=12, titleFontSize=13)
        .configure_legend(labelFontSize=12, titleFontSize=12)
        .configure_title(fontSize=15)
    )


def grafico_serie_esgoto(df):
    """Mart 2: índice de coleta/tratamento de esgoto por ano (%), por VOLUME.

    Recebe a janela ROBUSTA (ler_esgoto_robusto, 2006–2022): sem pontos > 100%.
    """
    titulo = f"Índice de coleta/tratamento de esgoto (volume) · % · {FONTE} · 2006–2022"
    ch = (
        alt.Chart(df)
        .transform_fold(
            ["indice_coleta_esgoto", "indice_tratamento_esgoto"], as_=["col", "valor"]
        )
        .transform_calculate(
            indicador="datum.col == 'indice_coleta_esgoto' ? 'Coleta' : 'Tratamento'"
        )
        .mark_line(point=True)
        .encode(
            x=alt.X("ano:O", title="Ano"),
            y=alt.Y("valor:Q", title="% do esgoto"),
            color=alt.Color(
                "indicador:N",
                title="Indicador",
                scale=alt.Scale(
                    domain=["Coleta", "Tratamento"], range=[P["teal"], P["amber"]]
                ),
            ),
        )
        .properties(title=titulo)
    )
    return _config(ch)


def grafico_porte(df, ano):
    """Mart 6: cobertura água/esgoto por faixa de porte. Legenda em texto Água/Esgoto.

    Base = população total IBGE (IN055/IN056). NÃO cruzar com o mart 1 (urbano).
    """
    titulo = (
        f"Cobertura por porte — {ano} · IN055/IN056 · base pop. total IBGE · {FONTE}"
    )
    # Rótulos legíveis das faixas, mapeados no Vega (apresentação; a gold não muda).
    mapa = ", ".join(f"'{cod}':'{lab}'" for cod, lab in PORTE_LABEL.items())
    ch = (
        alt.Chart(df)
        .transform_calculate(porte=f"({{{mapa}}})[datum.faixa_porte]")
        .transform_fold(["cobertura_agua", "cobertura_esgoto"], as_=["col", "valor"])
        .transform_calculate(
            indicador="datum.col == 'cobertura_agua' ? 'Água' : 'Esgoto'"
        )
        .mark_bar()
        .encode(
            x=alt.X("porte:N", title="Faixa de porte", sort=PORTE_ORDEM),
            xOffset=alt.XOffset("indicador:N"),
            y=alt.Y("valor:Q", title="Cobertura (%)"),
            color=alt.Color(
                "indicador:N",
                title="Indicador",
                scale=alt.Scale(
                    domain=["Água", "Esgoto"], range=[P["teal"], P["amber"]]
                ),
            ),
        )
        .properties(title=titulo)
    )
    return _config(ch)


def grafico_renda(df):
    """Mart 10: avanço do atendimento urbano de ÁGUA por quartil de renda."""
    titulo = (
        "Avanço por renda (só água urbana) 2010→2021 · % · "
        f"painel 4.472 municípios · {FONTE}"
    )
    ch = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("quartil_pib:O", title="Quartil de PIB per capita (1=menor)"),
            xOffset=alt.XOffset("ano:N"),
            y=alt.Y("cobertura_urbana_agua:Q", title="Cobertura urbana de água (%)"),
            color=alt.Color(
                "ano:N",
                title="Ano",
                scale=alt.Scale(domain=[2010, 2021], range=[P["grid"], P["teal"]]),
            ),
        )
        .properties(title=titulo)
    )
    return _config(ch)


def grafico_renda_cobertura(df):
    """Mart 9: dispersão PIB per capita × cobertura urbana de água (2021).

    Associação, não causa (D33). 5.302 pontos — ver D38 (limite do Altair tratado).
    """
    titulo = f"Renda × cobertura de água (2021) · associação, não causa · {FONTE}"
    ch = (
        alt.Chart(df)
        .mark_circle(opacity=0.35)
        .encode(
            x=alt.X("pib_per_capita:Q", title="PIB per capita (R$)"),
            y=alt.Y("cobertura_urbana_agua:Q", title="Cobertura urbana de água (%)"),
            color=alt.Color(
                "investimento_atipico:N",
                title="Investimento atípico",
                scale=alt.Scale(domain=[False, True], range=[P["teal"], P["amber"]]),
            ),
        )
        .properties(title=titulo)
    )
    return _config(ch)


def grafico_financeiro(df, ano):
    """Mart 5: investimento total por UF (R$ nominal). Comparar só no mesmo ano."""
    titulo = (
        f"Investimento total por UF — {ano} · R$ nominal (comparar só no ano) · {FONTE}"
    )
    ch = (
        alt.Chart(df)
        .mark_bar(color=P["teal"])
        .encode(
            x=alt.X("investimento_total:Q", title="Investimento total (R$ nominal)"),
            y=alt.Y("nome_uf:N", title="UF", sort="-x"),
        )
        .properties(title=titulo)
    )
    return _config(ch)


def frases_resumo(kpis):
    """Resumo executivo por frases-modelo (spec-dashboard §6).

    `kpis` é uma linha (mapeável por coluna) de `gold.kpis_brasil`. Sem número
    escrito à mão e sem explicação causal — só os campos do mart formatados.
    """
    ano = int(kpis["ano"])
    return [
        (
            f"Em {ano}, {fmt.pct(kpis['pct_sem_esgoto_br'])} da população "
            f"({fmt.milhao(kpis['pop_sem_esgoto_br'])}) estava sem coleta de "
            "esgoto por rede."
        ),
        (
            f"{fmt.pct(kpis['pct_sem_agua_br'])} "
            f"({fmt.milhao(kpis['pop_sem_agua_br'])}) sem água — número mínimo, "
            f"fora {fmt.inteiro(kpis['municipios_sem_info_agua_br'])} municípios "
            "sem informação."
        ),
        (
            f"A cobertura de água (IN055) era "
            f"{fmt.pct(kpis['cobertura_agua_in055_br'])} em {ano}."
        ),
        (
            "O volume de esgoto coletado equivalia a "
            f"{fmt.pct(kpis['indice_coleta_esgoto_br'])} do volume de água "
            f"consumido e {fmt.pct(kpis['indice_tratamento_esgoto_br'])} do "
            "coletado era tratado."
        ),
        (
            f"As perdas de água na distribuição somavam "
            f"{fmt.pct(kpis['perdas_in049_br'])} (IN049)."
        ),
    ]
