"""Bronze das três fontes IBGE (spec-ibge.md §4) — espelho fiel, tudo VARCHAR.

Segue o mesmo contrato da bronze do SNIS (pipeline/ingestao.py): `read_csv` com
`all_varchar=true`, `CREATE OR REPLACE` (idempotente), transação única e
validações bloqueantes BB1–BB3. A bronze NÃO converte, filtra, renomeia nem
trata nulo — a célula vazia vira NULL.

As contagens esperadas são constantes nomeadas aqui (não lidas do MANIFEST.md em
tempo de execução, por decisão do usuário); cada uma cita a seção da spec.
"""

import sys

from pipeline.db import conectar
from pipeline.ibge import DATA_EXTRACAO, arquivo_fonte

# --- Contagens esperadas da extração 2026-11-08 (spec-ibge.md §9 e §12) ------
# Fixas no código (não lidas do MANIFEST.md em runtime). Alimentam BB2/BB3.
LINHAS_POP, COLUNAS_POP = 191_099, 3  # §9.1 P1 · §12.1
LINHAS_PIB, COLUNAS_PIB = 66_840, 6  # §9.2 B1 · §12.2
LINHAS_DTB, COLUNAS_DTB = 5_571, 9  # §9.3 D1 (D12) · §12.3

# fonte -> (tabela bronze, arquivo CSV, linhas esperadas, colunas esperadas).
FONTES = {
    "populacao": (
        "bronze.ibge_populacao_municipio",
        "populacao_municipio.csv",
        LINHAS_POP,
        COLUNAS_POP,
    ),
    "pib": (
        "bronze.ibge_pib_municipio",
        "pib_municipio.csv",
        LINHAS_PIB,
        COLUNAS_PIB,
    ),
    "dtb": (
        "bronze.ibge_dtb_municipio",
        "dtb_municipio.csv",
        LINHAS_DTB,
        COLUNAS_DTB,
    ),
}


def _bronze_fonte(con, fonte, tabela, arquivo, linhas_esp, colunas_esp):
    """Grava uma bronze IBGE e valida BB1–BB3. Sai com 1 em qualquer falha."""
    caminho = arquivo_fonte(fonte, arquivo)
    if not caminho.exists():  # BB1
        print(f"[BLOQUEANTE] Arquivo ausente ({fonte}): {caminho}")
        sys.exit(1)

    origem = (
        f"read_csv('{caminho}', all_varchar=true, header=true, "
        f"delim=',', encoding='utf-8')"
    )

    con.execute("BEGIN TRANSACTION")
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute(f"CREATE OR REPLACE TABLE {tabela} AS SELECT * FROM {origem}")

    linhas = con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]
    colunas = len(con.execute(f"DESCRIBE {tabela}").fetchall())

    if linhas != linhas_esp:  # BB2
        con.execute("ROLLBACK")
        print(
            f"[BLOQUEANTE] {tabela}: linhas={linhas}, esperado {linhas_esp} "
            "(spec-ibge.md §9/§12). Verifique a extração em data/raw/ibge/."
        )
        sys.exit(1)
    if colunas != colunas_esp:  # BB3
        con.execute("ROLLBACK")
        print(
            f"[BLOQUEANTE] {tabela}: colunas={colunas}, esperado {colunas_esp} "
            "(spec-ibge.md §9/§12)."
        )
        sys.exit(1)

    con.execute("COMMIT")
    print(f"{tabela} · {linhas} linhas · {colunas} colunas")


def main():
    print(f"IBGE bronze (extração {DATA_EXTRACAO}):")
    con = conectar()
    try:
        for fonte, (tabela, arq, linhas, colunas) in FONTES.items():
            _bronze_fonte(con, fonte, tabela, arq, linhas, colunas)
    finally:
        con.close()


if __name__ == "__main__":
    main()
