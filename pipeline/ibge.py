"""Constantes e utilidades compartilhadas das fontes IBGE (spec-ibge.md).

Reúne o que as etapas IBGE (bronze, silver e teste de cobertura) precisam em
comum, para que haja UM único lugar com:

- a **data da extração** usada nas pastas `data/raw/ibge/<fonte>/<DATA>/`
  (spec-ibge.md §3 e §12);
- o **mapa estático dos 27 códigos de UF** → (sigla, macrorregião), do qual a
  silver da DTB deriva `sigla_uf` e `nome_regiao` (spec-ibge.md §5.3). O arquivo
  da DTB traz só o código numérico da UF; nada é adivinhado por município.

As **contagens esperadas** de cada fonte NÃO ficam aqui: cada módulo declara as
suas no próprio topo, citando a seção da spec (pedido do usuário).
"""

from pipeline.db import PASTA_RAW

# Data da extração — definida num ÚNICO lugar (spec-ibge.md §3 e §12). As três
# fontes foram baixadas nesta data; as pastas são data/raw/ibge/<fonte>/<DATA>/.
DATA_EXTRACAO = "2026-11-08"

PASTA_IBGE = PASTA_RAW / "ibge"

# Janela analítica do projeto (spec-ibge.md §6; limitada pela série do PIB).
JANELA_INICIO, JANELA_FIM = 2010, 2021


def arquivo_fonte(fonte, nome):
    """Caminho do arquivo <nome> da <fonte> na extração corrente."""
    return PASTA_IBGE / fonte / DATA_EXTRACAO / nome


# --- Mapa estático dos 27 códigos de UF do IBGE (spec-ibge.md §5.3) ----------
# código numérico da UF (2 dígitos) -> (sigla, macrorregião).
# A macrorregião também sai do 1º dígito do código (1=Norte … 5=Centro-Oeste),
# mas é mantida explícita por UF para o teste de completude pegar qualquer
# inconsistência. Grafia "Centro-Oeste" com hífen (spec-ibge.md §5.3).
MAPA_UF = {
    "11": ("RO", "Norte"),
    "12": ("AC", "Norte"),
    "13": ("AM", "Norte"),
    "14": ("RR", "Norte"),
    "15": ("PA", "Norte"),
    "16": ("AP", "Norte"),
    "17": ("TO", "Norte"),
    "21": ("MA", "Nordeste"),
    "22": ("PI", "Nordeste"),
    "23": ("CE", "Nordeste"),
    "24": ("RN", "Nordeste"),
    "25": ("PB", "Nordeste"),
    "26": ("PE", "Nordeste"),
    "27": ("AL", "Nordeste"),
    "28": ("SE", "Nordeste"),
    "29": ("BA", "Nordeste"),
    "31": ("MG", "Sudeste"),
    "32": ("ES", "Sudeste"),
    "33": ("RJ", "Sudeste"),
    "35": ("SP", "Sudeste"),
    "41": ("PR", "Sul"),
    "42": ("SC", "Sul"),
    "43": ("RS", "Sul"),
    "50": ("MS", "Centro-Oeste"),
    "51": ("MT", "Centro-Oeste"),
    "52": ("GO", "Centro-Oeste"),
    "53": ("DF", "Centro-Oeste"),
}

MACRORREGIOES = ("Norte", "Nordeste", "Sudeste", "Sul", "Centro-Oeste")


def case_sql(coluna, indice):
    """Expressão SQL CASE que traduz `coluna` (código de UF) via MAPA_UF.

    `indice` 0 → sigla, 1 → macrorregião. Código fora do mapa vira NULL, que a
    pré-validação da silver reprova (bloqueante).
    """
    whens = " ".join(
        f"WHEN '{cod}' THEN '{destino[indice]}'" for cod, destino in MAPA_UF.items()
    )
    return f"CASE {coluna} {whens} END"
