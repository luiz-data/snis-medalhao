"""Orquestrador do pipeline medalhão.

Apaga o banco e roda todas as etapas do zero.
Uso: uv run python executar.py
"""

from pipeline.db import CAMINHO_BANCO
from pipeline.ingestao import main as ingestao


def main():
    # Apaga o banco e o WAL para garantir início limpo.
    for arq in [CAMINHO_BANCO, CAMINHO_BANCO.with_suffix(".duckdb.wal")]:
        arq.unlink(missing_ok=True)

    print("Banco removido. Iniciando do zero.\n")

    # --- bronze ---
    ingestao()

    # --- silver e gold entram nas próximas etapas ---


if __name__ == "__main__":
    main()