from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent
PASTA_RAW = RAIZ / "data" / "raw"
CAMINHO_BANCO = RAIZ / "snis.duckdb"


def conectar():
    return duckdb.connect(str(CAMINHO_BANCO))
