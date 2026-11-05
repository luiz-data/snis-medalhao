# Projeto SNIS: pipeline medalhão

- Stack: Python com uv, DuckDB, Streamlit, pytest, ruff. Comandos sempre com `uv run`.
- Camadas: bronze, silver, gold (schemas no `snis.duckdb`).
- Fonte: data/raw/br_mdr_snis_municipio_agua_esgoto.csv.gz (somente leitura).
- Método: spec-driven. Escreva a spec em docs/ antes de qualquer código.
- Nunca edite nada em data/raw/. Não adicione dependências sem avisar.
- Trabalhe um passo por vez e só faça o que eu pedir.
- Responda em português.