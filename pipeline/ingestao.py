import sys

from pipeline.db import PASTA_RAW, conectar

ARQUIVO = PASTA_RAW / "br_mdr_snis_municipio_agua_esgoto.csv.gz"
TABELA = "bronze.municipio_agua_esgoto"


def main():
    if not ARQUIVO.exists():
        print(f"Arquivo não encontrado: {ARQUIVO}")
        sys.exit(1)

    fonte = (
        f"read_csv('{ARQUIVO}', all_varchar=true, header=true, "
        f"delim=',', encoding='utf-8')"
    )

    con = conectar()
    try:
        linhas_fonte = con.execute(f"SELECT count(*) FROM {fonte}").fetchone()[0]
        colunas_fonte = len(con.execute(f"DESCRIBE SELECT * FROM {fonte}").fetchall())

        con.execute("BEGIN TRANSACTION")
        con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
        con.execute(f"CREATE OR REPLACE TABLE {TABELA} AS SELECT * FROM {fonte}")

        linhas_tabela = con.execute(f"SELECT count(*) FROM {TABELA}").fetchone()[0]
        colunas_tabela = len(con.execute(f"DESCRIBE {TABELA}").fetchall())

        if linhas_tabela != linhas_fonte:
            con.execute("ROLLBACK")
            print(
                f"Divergência de linhas: arquivo={linhas_fonte}, tabela={linhas_tabela}"
            )
            sys.exit(1)

        if colunas_tabela != colunas_fonte:
            con.execute("ROLLBACK")
            print(
                f"Divergência de colunas: arquivo={colunas_fonte}, "
                f"tabela={colunas_tabela}"
            )
            sys.exit(1)

        con.execute("COMMIT")
    finally:
        con.close()

    print(f"Tabela gravada: {TABELA}")
    print(f"Linhas:  {linhas_tabela}")
    print(f"Colunas: {colunas_tabela}")


if __name__ == "__main__":
    main()
