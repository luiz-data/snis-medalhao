"""Orquestrador do pipeline medalhão.

Apaga o banco e roda todas as etapas do zero.
Uso: uv run python executar.py
"""

import logging

from pipeline.cobertura import main as cobertura
from pipeline.db import CAMINHO_BANCO
from pipeline.gold import main as gold
from pipeline.ingestao import main as ingestao
from pipeline.ingestao_ibge import main as ingestao_ibge
from pipeline.log import configurar
from pipeline.transformacao import main as transformacao
from pipeline.transformacao_ibge import main as transformacao_ibge

logger = logging.getLogger(__name__)


def main():
    # Configuração central do logging: único ponto que define nível e formato.
    configurar()

    # Apaga o banco e o WAL para garantir início limpo.
    for arq in [CAMINHO_BANCO, CAMINHO_BANCO.with_suffix(".duckdb.wal")]:
        arq.unlink(missing_ok=True)

    logger.info("Banco removido. Iniciando do zero.\n")

    # --- bronze ---
    ingestao()

    # --- silver ---
    transformacao()

    # --- IBGE bronze (spec-ibge.md §8) ---
    ingestao_ibge()

    # --- IBGE silver ---
    transformacao_ibge()

    # --- teste de cobertura de junção SNIS × IBGE (spec-ibge.md §7/§8) ---
    cobertura()

    # --- gold (spec-gold.md §4): 6º passo, após a cobertura ---
    gold()


if __name__ == "__main__":
    main()
