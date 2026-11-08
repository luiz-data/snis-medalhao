"""Teste de cobertura de junção SNIS × IBGE (spec-ibge.md §7).

É um TESTE, não uma correção: nenhum município é editado (D6). Mede, antes de
qualquer JOIN dos marts, quanto de `silver.municipio_agua_esgoto` casa com cada
fonte IBGE e lista as divergências. Entra como o 5º passo do executor
(spec-ibge.md §8), depois das silvers do SNIS e do IBGE.

Os limiares de aceite da D7 são **constantes nomeadas** (provisórios; revisar
após a 1ª medição real e registrar o definitivo em docs/decisoes.md). Nada de
número mágico espalhado pelo código.
"""

import sys

from pipeline.db import conectar
from pipeline.ibge import JANELA_FIM, JANELA_INICIO

# --- Limiares de aceite (constantes nomeadas) -------------------------------
# D7 (spec-ibge.md §7.3), PROVISÓRIOS — revisar após a 1ª medição real.
COBERTURA_ALERTA = 0.99  # abaixo disto: alerta inspecionável (não bloqueia)
COBERTURA_BLOQUEIO = 0.95  # abaixo disto: bloqueante (id desalinhado)
# D12 (spec-ibge.md §7.3): divergências SNIS→DTB aceitas (31 municípios de ano
# único). Acima disto, ou fora da lista conhecida, é bloqueante.
DTB_MAX_DIVERGENCIAS = 31

SNIS = "silver.municipio_agua_esgoto"


def _um(con, sql):
    return con.execute(sql).fetchone()[0]


def cobertura_dtb(con):
    """Cobertura cadastral SNIS→DTB (total). Retorna (divergencias, bloqueia)."""
    div = _um(
        con,
        f"""
        SELECT count(*) FROM (
            SELECT DISTINCT id_municipio FROM {SNIS}
            EXCEPT
            SELECT id_municipio FROM silver.ibge_dtb_municipio
        )
        """,
    )
    bloqueia = div > DTB_MAX_DIVERGENCIAS
    status = "BLOQUEANTE" if bloqueia else "ok"
    print(
        f"  DTB: {div} id(s) do SNIS sem par na DTB "
        f"(limite {DTB_MAX_DIVERGENCIAS}, D12) — {status}"
    )
    return div, bloqueia


def cobertura_por_ano(con, fonte, tabela):
    """Cobertura por ano na janela analítica. Retorna True se algum ano bloqueia."""
    linhas = con.execute(
        f"""
        WITH snis AS (
            SELECT ano, count(DISTINCT id_municipio) AS n
            FROM {SNIS}
            WHERE ano BETWEEN {JANELA_INICIO} AND {JANELA_FIM}
            GROUP BY ano
        ),
        casados AS (
            SELECT s.ano, count(DISTINCT s.id_municipio) AS n
            FROM {SNIS} s
            JOIN {tabela} f USING (ano, id_municipio)
            WHERE s.ano BETWEEN {JANELA_INICIO} AND {JANELA_FIM}
            GROUP BY s.ano
        )
        SELECT snis.ano, snis.n, coalesce(casados.n, 0) AS casados
        FROM snis LEFT JOIN casados USING (ano)
        ORDER BY snis.ano
        """
    ).fetchall()

    bloqueia = False
    piores = []
    for ano, n, casados in linhas:
        taxa = casados / n if n else 1.0
        if taxa < COBERTURA_BLOQUEIO:
            bloqueia = True
            piores.append((ano, taxa, "BLOQUEANTE"))
        elif taxa < COBERTURA_ALERTA:
            piores.append((ano, taxa, "alerta"))
    taxas = [casados / n if n else 1.0 for _, n, casados in linhas]
    minimo = min(taxas) if taxas else 1.0
    print(
        f"  {fonte}: cobertura por ano {JANELA_INICIO}–{JANELA_FIM} — "
        f"mínimo {minimo:.2%} "
        f"(alerta <{COBERTURA_ALERTA:.0%}, bloqueio <{COBERTURA_BLOQUEIO:.0%})"
    )
    for ano, taxa, nivel in piores:
        print(f"    {ano}: {taxa:.2%} [{nivel}]")
    return bloqueia


def main():
    print("Cobertura de junção SNIS × IBGE (spec-ibge.md §7):")
    con = conectar()
    try:
        _, dtb_bloqueia = cobertura_dtb(con)
        pop_bloqueia = cobertura_por_ano(
            con, "POP", "silver.ibge_populacao_municipio"
        )
        pib_bloqueia = cobertura_por_ano(con, "PIB", "silver.ibge_pib_municipio")
    finally:
        con.close()

    if dtb_bloqueia or pop_bloqueia or pib_bloqueia:
        print("[BLOQUEANTE] Cobertura abaixo do limiar de aceite (D7/D12).")
        sys.exit(1)
    print("Cobertura dentro dos limiares (D7/D12).")


if __name__ == "__main__":
    main()
