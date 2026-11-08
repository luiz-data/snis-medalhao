"""Orquestrador do pipeline medalhão.

Apaga o banco e roda todas as etapas do zero.
Uso: uv run python executar.py
"""

from pipeline.cobertura import main as cobertura
from pipeline.db import CAMINHO_BANCO
from pipeline.gold import main as gold
from pipeline.ingestao import main as ingestao
from pipeline.ingestao_ibge import main as ingestao_ibge
from pipeline.transformacao import main as transformacao
from pipeline.transformacao_ibge import main as transformacao_ibge


def main():
    # Apaga o banco e o WAL para garantir início limpo.
    for arq in [CAMINHO_BANCO, CAMINHO_BANCO.with_suffix(".duckdb.wal")]:
        arq.unlink(missing_ok=True)

    print("Banco removido. Iniciando do zero.\n")

    # --- bronze ---
    ingestao()

    # --- silver ---
    print()
    transformacao()

    # --- IBGE bronze (spec-ibge.md §8) ---
    print()
    ingestao_ibge()

    # --- IBGE silver ---
    print()
    transformacao_ibge()

    # --- teste de cobertura de junção SNIS × IBGE (spec-ibge.md §7/§8) ---
    print()
    cobertura()

    # --- gold (spec-gold.md §4): 6º passo, após a cobertura ---
    print()
    gold()


if __name__ == "__main__":
    main()