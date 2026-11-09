"""Formatação própria de números para o dashboard (spec-dashboard.md §10).

Sem depender de `locale`: separador de milhar `.` e decimal `,` montados à mão.
Valor ausente (None/NaN) vira o traço "—". Nenhuma formatação faz cálculo de
agregação — só apresentação.
"""

import math


def _ausente(valor):
    return valor is None or (isinstance(valor, float) and math.isnan(valor))


def _grupos_milhar(inteiro_str):
    """'15297535452' -> '15.297.535.452' (agrupa de 3 em 3, da direita)."""
    partes = []
    while len(inteiro_str) > 3:
        partes.insert(0, inteiro_str[-3:])
        inteiro_str = inteiro_str[:-3]
    partes.insert(0, inteiro_str)
    return ".".join(partes)


def _numero(valor, casas):
    """Número com milhar '.' e decimal ','. `casas` fixa as decimais."""
    if _ausente(valor):
        return "—"
    negativo = float(valor) < 0
    corpo_num = f"{abs(float(valor)):.{casas}f}"
    if casas > 0:
        parte_int, parte_frac = corpo_num.split(".")
        corpo = _grupos_milhar(parte_int) + "," + parte_frac
    else:
        corpo = _grupos_milhar(corpo_num)
    return ("-" if negativo else "") + corpo


def brl(valor, casas=2):
    """Reais nominais: 15297535452.19 -> 'R$ 15.297.535.452,19'."""
    texto = _numero(valor, casas)
    return texto if texto == "—" else f"R$ {texto}"


def pct(valor, casas=2):
    """Percentual: 44.19 -> '44,19%'."""
    texto = _numero(valor, casas)
    return texto if texto == "—" else f"{texto}%"


def inteiro(valor):
    """Inteiro com milhar: 15297535452 -> '15.297.535.452'."""
    return _numero(valor, 0)


def milhao(valor, casas=1):
    """Milhões: 92879110 -> '92,9 mi'."""
    if _ausente(valor):
        return "—"
    return _numero(float(valor) / 1_000_000, casas) + " mi"
