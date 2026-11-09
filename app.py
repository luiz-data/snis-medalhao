"""Dashboard SNIS — Streamlit (spec-dashboard.md §3/§10). SEM cálculo na tela.

Lê só o schema `gold` (via painel.py, somente leitura). Monta a página em faixas
(Visão Brasil) + aba Detalhe. Cartões = st.container(border=True) + st.metric +
st.caption. Figuras vêm de painel.py. Tema e paleta de tema.py (fonte única).

Rodar:  uv run streamlit run app.py
"""

import os

import streamlit as st

import formato as fmt
import painel
import pipeline.db as _db
import tema

# D36: domínio do seletor de ano = 2010–2021. NUNCA 2022 (urbano nulo em 2022, D2).
ANOS = list(range(2010, 2022))
ANO_PADRAO = 2021
REGIOES = ["Todas", "Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]

CMD = "uv run python -m pipeline.gold"
MARTS_NECESSARIOS = [
    "gold.kpis_brasil",
    "gold.esgoto_coleta_tratamento_ano",
    "gold.atendimento_porte_ano",
    "gold.avanco_por_renda_painel",
    "gold.ranking_atendimento_variacao",
    "gold.atendimento_vs_pib_2021",
    "gold.financeiro_uf_ano",
]


def _banco():
    """Caminho do banco: env SNIS_BANCO (testes) ou o padrão do pipeline."""
    return os.environ.get("SNIS_BANCO") or str(_db.CAMINHO_BANCO)


def _verificar(banco):
    """Devolve mensagem de erro se faltar o banco ou um mart; senão None."""
    import duckdb

    if not os.path.exists(banco):
        return f"Banco não encontrado em {banco}. Rode: {CMD}"
    try:
        con = duckdb.connect(banco, read_only=True)
    except duckdb.Error as exc:
        return f"Não foi possível abrir o banco ({exc}). Rode: {CMD}"
    try:
        existentes = {
            f"{s}.{t}"
            for s, t in con.execute(
                "SELECT schema_name, table_name FROM duckdb_tables() "
                "WHERE schema_name = 'gold'"
            ).fetchall()
        }
    finally:
        con.close()
    faltam = [m for m in MARTS_NECESSARIOS if m not in existentes]
    if faltam:
        return f"Mart(s) ausente(s): {', '.join(faltam)}. Rode: {CMD}"
    return None


st.set_page_config(page_title="Saneamento no Brasil — SNIS", layout="wide")
st.markdown(tema.css(), unsafe_allow_html=True)

BANCO = _banco()
_erro = _verificar(BANCO)
if _erro:
    st.error(_erro)
    st.stop()

st.title("Saneamento no Brasil — SNIS")

aba_visao, aba_detalhe = st.tabs(["Visão Brasil", "Detalhe"])

with aba_visao:
    cab = st.columns([2, 4, 1])
    with cab[0]:
        ano = st.selectbox("Ano", ANOS, index=ANOS.index(ANO_PADRAO))
    with cab[1]:
        st.caption(
            "Indicadores urbanos só até 2021 (nunca 2022); o mart 11 cobre "
            "2010–2021. Região só na aba Detalhe."
        )
    with cab[2]:
        if st.button("Recarregar dados"):
            st.cache_data.clear()

    k = painel.ler_kpis_ano(ano, banco=BANCO).iloc[0]
    n_sem_info = fmt.inteiro(k["municipios_sem_info_agua_br"])

    # Faixa A — 3 colunas temáticas (Água / Esgoto / Gestão), 2 cartões cada.
    col_agua, col_esgoto, col_gestao = st.columns(3)
    with col_agua:
        st.caption("ÁGUA")
        with st.container(border=True):
            st.metric("Água (IN055)", fmt.pct(k["cobertura_agua_in055_br"]))
            st.caption("Base pop. total IBGE (informantes de água).")
        with st.container(border=True):
            st.metric(
                "Sem água (piso)",
                f"{fmt.milhao(k['pop_sem_agua_br'])} · {fmt.pct(k['pct_sem_agua_br'])}",
            )
            st.caption(
                f"Piso: {n_sem_info} municípios sem informação de água ficam fora "
                f"(em {int(k['ano'])})."
            )
    with col_esgoto:
        st.caption("ESGOTO")
        with st.container(border=True):
            st.metric("Esgoto (IN056)", fmt.pct(k["cobertura_esgoto_in056_br"]))
            st.caption("Cobertura por população (não é o índice por volume).")
        with st.container(border=True):
            st.metric(
                "Sem esgoto",
                f"{fmt.milhao(k['pop_sem_esgoto_br'])} · "
                f"{fmt.pct(k['pct_sem_esgoto_br'])}",
            )
            st.caption(
                "Piso; por rede coletora; fossa conta como sem esgoto. Exclui "
                f"{n_sem_info} municípios sem informação de água."
            )
    with col_gestao:
        st.caption("GESTÃO")
        with st.container(border=True):
            st.metric("Perdas (IN049)", fmt.pct(k["perdas_in049_br"]))
            st.caption(
                "Cálculo próprio pela fórmula do SNIS; pode diferir de valores "
                "divulgados (diferença não reconciliada)."
            )
        with st.container(border=True):
            st.metric(
                "Investimento per capita",
                f"{fmt.brl(k['investimento_per_capita_br'])}/hab",
            )
            st.caption("Nominal, entre os municípios que declararam investimento.")

    # Faixa B — série (ignora o Ano) + resumo executivo.
    fb1, fb2 = st.columns([2, 1])
    with fb1, st.container(border=True):
        serie = painel.ler_esgoto_robusto(banco=BANCO)
        st.altair_chart(painel.grafico_serie_esgoto(serie), width="stretch")
        st.caption(
            "Índice por VOLUME (coletado ÷ consumido) ≠ cobertura de esgoto por "
            "rede (população): 56,02% ≠ 55,81%. Janela 2006–2022 (**ignora o "
            "filtro de Ano**). Omitidos 1995–2005: série não robusta (< ~1.000 "
            "informantes de coleta) e 1998/1999 com coleta acima de 100% "
            "(1.578%/1.609%)."
        )
        # E12: número de informantes exibido onde afeta a leitura (mart 2).
        ini, fim = serie.iloc[0], serie.iloc[-1]
        st.caption(
            "Informantes de coleta (mart 2): "
            f"{fmt.inteiro(ini['municipios_informantes_coleta'])} em "
            f"{int(ini['ano'])} → "
            f"{fmt.inteiro(fim['municipios_informantes_coleta'])} em "
            f"{int(fim['ano'])}."
        )
    with fb2, st.container(border=True):
        st.caption("RESUMO EXECUTIVO")
        for frase in painel.frases_resumo(k):
            st.write(frase)

    # Faixa C — porte (reage ao Ano) + renda (ignora o Ano).
    fc1, fc2 = st.columns(2)
    with fc1, st.container(border=True):
        st.altair_chart(
            painel.grafico_porte(painel.ler_porte(ano, banco=BANCO), ano),
            width="stretch",
        )
        st.caption(
            "Base pop. total IBGE; não cruzar com o mart 1 (urbano). Reage ao "
            "Ano. Legenda em texto Água/Esgoto."
        )
    with fc2, st.container(border=True):
        st.altair_chart(
            painel.grafico_renda(painel.ler("renda", banco=BANCO)),
            width="stretch",
        )
        st.caption(
            "Só água urbana (painel 4.472). Recorte fixo 2010→2021: **ignora o "
            "filtro de Ano**."
        )

    with st.container(border=True):
        st.caption(
            "Fonte: SNIS + IBGE · janela 2010–2021 · C9 (Brasil = Σ regiões) e C10 "
            "conferidas por teste. Valores em R$ são nominais (comparar só no ano)."
        )

with aba_detalhe:
    regiao = st.selectbox("Região/UF", REGIOES, index=0)
    st.caption("O filtro de Região vale só nesta aba (marts 4, 5, 9).")

    with st.container(border=True):
        st.metric("Água urbana (mart 1)", fmt.pct(k["cobertura_urbana_agua_br"]))
        st.caption(
            "Cobertura urbana (SNIS), medida distinta do IN055 e válida só até "
            "2021 — não comparar com o IN055."
        )

    det1, det2, det3 = st.columns(3)
    with det1, st.container(border=True):
        st.subheader("Ranking de municípios")
        st.caption("mart 4 · quem mais melhorou/piorou (variação em pp).")
        st.dataframe(
            painel.ler_detalhe("ranking", regiao=regiao, banco=BANCO),
            width="stretch",
            height=260,
        )
    with det2, st.container(border=True):
        st.altair_chart(
            painel.grafico_renda_cobertura(
                painel.ler_detalhe("renda_pib", regiao=regiao, banco=BANCO)
            ),
            width="stretch",
        )
        st.caption("mart 9 · 2021 · associação, não causa.")
    with det3, st.container(border=True):
        st.altair_chart(
            painel.grafico_financeiro(
                painel.ler_financeiro(ano, regiao=regiao, banco=BANCO), ano
            ),
            width="stretch",
        )
        st.caption("mart 5 · R$ nominal (comparar só no ano) · nota: RN afetada.")
