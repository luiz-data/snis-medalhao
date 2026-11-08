"""Executor da camada gold (silver -> gold) — spec-gold.md §4, D20.

Mesma arquitetura dos executores existentes (pipeline/transformacao.py,
pipeline/transformacao_ibge.py): conexão de pipeline.db, UMA transação,
ROLLBACK + sys.exit(1) em qualquer erro, saída no mesmo formato das etapas.

Regra central (D20): cada arquivo sql/gold/NN_nome.sql contém **apenas um
SELECT**. O executor é quem compõe o `CREATE TABLE gold.<nome> AS <select>` e
controla a transação — assim a regra "uma tabela por arquivo" vive num único
ponto. O arquivo NÃO traz CREATE/DROP/INSERT, nem múltiplos statements.

Este passo entrega só o EXECUTOR; os 10 marts (sql/gold/01..10_*.sql) vêm
depois. Com sql/gold/ vazia, o executor ainda recria o schema `gold` (idempotência)
e cria 0 tabelas, saindo com 0 — é o estado esperado antes dos marts.
"""

import re
import sys
from pathlib import Path

import duckdb

from pipeline.db import conectar

# Pasta dos SQL da gold (spec-gold.md §1.1). Criada no repositório.
RAIZ = Path(__file__).resolve().parent.parent
PASTA_SQL = RAIZ / "sql" / "gold"

# Prefixo numérico obrigatório: NN_nome.sql (00..10). Ordena a leitura.
RE_ARQUIVO = re.compile(r"^(\d{2})_([a-z0-9_]+)\.sql$")

# Palavras-chave proibidas num arquivo de mart (D20: só um SELECT).
RE_DDL_DML = re.compile(
    r"\b(create|drop|insert|update|delete|alter|attach|copy|truncate|grant)\b",
    re.IGNORECASE,
)


def erro(con, msg):
    """ROLLBACK defensivo, imprime e sai com 1 (igual à silver do SNIS/IBGE)."""
    try:
        con.execute("ROLLBACK")
    except duckdb.Error:
        pass
    print(msg)
    con.close()
    sys.exit(1)


def _um(con, sql):
    return con.execute(sql).fetchone()[0]


def _sem_comentarios(sql):
    """Remove comentários -- de linha e /* */ de bloco (para a validação D20)."""
    sem_bloco = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sem_bloco)


def nome_mart(arquivo):
    """`NN_nome.sql` -> `nome` (nome da tabela gold)."""
    return RE_ARQUIVO.match(arquivo).group(2)


def _validar_select(corpo):
    """Valida D20: o arquivo é UM único SELECT. Devolve (ok, motivo)."""
    limpo = _sem_comentarios(corpo).strip()
    if not limpo:
        return False, "arquivo vazio (sem SELECT)"
    # Um único statement: no máximo um `;` e só no fim.
    sem_fim = limpo.rstrip().rstrip(";").strip()
    if ";" in sem_fim:
        return False, "mais de um statement (';' separando comandos)"
    # Precisa começar com SELECT ou WITH (CTE -> SELECT); marts 4/10 usam WITH.
    if not re.match(r"^\s*(select|with)\b", sem_fim, re.IGNORECASE):
        return False, "não começa com SELECT nem WITH"
    if RE_DDL_DML.search(sem_fim):
        return False, "contém DDL/DML (CREATE/DROP/INSERT/...)"
    return True, ""


def listar_arquivos():
    """Arquivos sql/gold/NN_*.sql em ordem numérica pelo prefixo NN."""
    if not PASTA_SQL.is_dir():
        return []
    arquivos = [p for p in PASTA_SQL.iterdir() if RE_ARQUIVO.match(p.name)]
    return sorted(arquivos, key=lambda p: p.name)


def executar_gold(con):
    arquivos = listar_arquivos()

    try:
        con.execute("BEGIN TRANSACTION")
        con.execute("DROP SCHEMA IF EXISTS gold CASCADE")
        con.execute("CREATE SCHEMA gold")
    except duckdb.Error as exc:
        erro(con, f"[BLOQUEANTE] Falha ao (re)criar o schema gold: {exc}")

    if not arquivos:
        # Estado esperado antes dos marts: schema recriado, 0 tabelas.
        con.execute("COMMIT")
        print("gold: schema recriado, nenhum mart em sql/gold/ (0 tabelas).")
        return

    def n_tabelas():
        return _um(
            con,
            "SELECT count(*) FROM duckdb_tables() WHERE schema_name = 'gold'",
        )

    resultados = []
    for arq in arquivos:
        nome = nome_mart(arq.name)
        corpo = arq.read_text(encoding="utf-8")

        ok, motivo = _validar_select(corpo)
        if not ok:  # D20: um único SELECT por arquivo
            erro(
                con,
                f"[BLOQUEANTE] D20: {arq.name} não é um único SELECT ({motivo}).",
            )

        antes = n_tabelas()
        select = _sem_comentarios(corpo).strip().rstrip().rstrip(";")
        try:
            con.execute(f"CREATE TABLE gold.{nome} AS\n{select}")
        except duckdb.Error as exc:
            erro(con, f"[BLOQUEANTE] Falha ao criar gold.{nome} ({arq.name}): {exc}")

        # Confere: exatamente uma tabela nova e a esperada existe (D20).
        depois = n_tabelas()
        if depois != antes + 1:
            erro(
                con,
                f"[BLOQUEANTE] D20: {arq.name} criou {depois - antes} tabela(s), "
                f"esperado 1.",
            )
        existe = _um(
            con,
            "SELECT count(*) FROM duckdb_tables() "
            f"WHERE schema_name = 'gold' AND table_name = '{nome}'",
        )
        if not existe:
            erro(con, f"[BLOQUEANTE] D20: tabela gold.{nome} não foi criada.")

        linhas = _um(con, f"SELECT count(*) FROM gold.{nome}")
        colunas = _um(
            con,
            "SELECT count(*) FROM duckdb_columns() "
            f"WHERE schema_name = 'gold' AND table_name = '{nome}'",
        )
        resultados.append((nome, linhas, colunas))

    con.execute("COMMIT")

    for nome, linhas, colunas in resultados:
        print(f"gold.{nome} · {linhas} linhas · {colunas} colunas")

    # Bloco de diagnóstico (spec-gold.md §4, item 5). Vazio até os marts
    # existirem — municípios fora de painel (4/10), sinalizados D4,
    # inconsistentes D3 virão com cada mart.
    print("  diagnóstico: (sem marts; nada a reportar)")


def main():
    print("gold:")
    con = conectar()
    executar_gold(con)
    con.close()


if __name__ == "__main__":
    main()
