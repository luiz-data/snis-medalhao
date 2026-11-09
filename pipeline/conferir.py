import sys

import duckdb

from pipeline.db import PASTA_RAW

ARQUIVO = PASTA_RAW / "br_mdr_snis_municipio_agua_esgoto.csv.gz"
CHAVES = ["ano", "id_municipio", "sigla_uf"]


def main():
    if not ARQUIVO.exists():
        print(f"Arquivo não encontrado: {ARQUIVO}")
        sys.exit(1)

    con = duckdb.connect()
    origem = f"read_csv('{ARQUIVO}', all_varchar=true)"

    def um(consulta):
        return con.execute(consulta).fetchone()[0]

    colunas = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM {origem}").fetchall()]
    total = um(f"SELECT count(*) FROM {origem}")

    print(f"Arquivo:   {ARQUIVO.name}")
    print(f"Linhas:    {total}")
    print(f"Colunas:   {len(colunas)}")
    print(
        f"Anos:      {um(f'SELECT min(ano) FROM {origem}')} a "
        f"{um(f'SELECT max(ano) FROM {origem}')} "
        f"({um(f'SELECT count(DISTINCT ano) FROM {origem}')} distintos)"
    )
    print(
        f"Municípios distintos: {um(f'SELECT count(DISTINCT id_municipio) FROM {origem}')}"
    )
    print(
        f"UFs distintas:        {um(f'SELECT count(DISTINCT sigla_uf) FROM {origem}')}"
    )

    dup = um(
        f"SELECT count(*) FROM (SELECT 1 FROM {origem} "
        f"GROUP BY ano, id_municipio HAVING count(*) > 1)"
    )
    print(f"\nChaves (ano, id_municipio) duplicadas: {dup}")

    print("\nNulos nas colunas-chave:")
    for c in CHAVES:
        n = um(f'SELECT count(*) FROM {origem} WHERE "{c}" IS NULL')
        print(f"  {c}: {n}")

    ano_ruim = um(
        f"SELECT count(*) FROM {origem} WHERE NOT regexp_matches(ano, '^[0-9]{{4}}$')"
    )
    mun_ruim = um(
        f"SELECT count(*) FROM {origem} WHERE NOT regexp_matches(id_municipio, '^[0-9]{{7}}$')"
    )
    print(f"\nano fora do formato AAAA:          {ano_ruim}")
    print(f"id_municipio fora de 7 dígitos:    {mun_ruim}")

    preenchidos = con.execute(
        "SELECT " + ", ".join(f'count("{c}")' for c in colunas) + f" FROM {origem}"
    ).fetchone()
    nulos = sorted(((total - p, c) for c, p in zip(colunas, preenchidos)), reverse=True)
    print("\n10 colunas com mais nulos:")
    for n, c in nulos[:10]:
        print(f"  {c}: {n} ({n / total:.1%})")

    print("\nAmostra:")
    print(
        con.execute(
            f"SELECT ano, id_municipio, sigla_uf, populacao_atendida_agua FROM {origem} LIMIT 5"
        )
        .df()
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
