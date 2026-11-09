"""Tema do dashboard — FONTE ÚNICA da paleta (D37, spec-dashboard §10/regra 7k).

Tema escuro verde-azulado. `.streamlit/config.toml` espelha estes valores
(backgroundColor=bg, secondaryBackgroundColor=surface, primaryColor=teal,
textColor=text). As razões de contraste WCAG estão em `contraste()` e foram
verificadas: texto normal ≥ 4,5:1, texto grande/gráfico ≥ 3:1.
"""

PALETA = {
    "bg": "#0B1F24",  # fundo base
    "surface": "#123A42",  # superfície (faixas, resumo)
    "card": "#0E2E35",  # cartão de KPI
    "text": "#EAF4F1",  # texto principal
    "muted": "#AFCDC8",  # texto secundário
    "teal": "#45D0BB",  # acento positivo (cobertura/água)
    "amber": "#F4B65A",  # acento alerta (déficit)
    "danger": "#F2765A",  # piora/atípico
    "grid": "#3E7480",  # linhas de grade/eixo
}

# Pares usados (fg, bg, tipo) e o alvo WCAG por tipo.
_ALVO = {"normal": 4.5, "grande": 3.0, "grafico": 3.0}
_PARES = [
    ("text", "bg", "normal"),
    ("text", "surface", "normal"),
    ("text", "card", "normal"),
    ("muted", "surface", "normal"),
    ("muted", "card", "normal"),
    ("teal", "card", "grande"),
    ("amber", "card", "grande"),
    ("danger", "card", "grande"),
    ("teal", "bg", "grafico"),
    ("amber", "bg", "grafico"),
    ("grid", "bg", "grafico"),
]


def _luminancia(hexs):
    def canal(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    h = hexs.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def razao_contraste(fg, bg):
    """Razão de contraste WCAG entre duas cores hex (>= 1)."""
    a, b = _luminancia(fg), _luminancia(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def contraste():
    """Tabela [(par, razao, alvo, passa)] para todos os pares usados."""
    linhas = []
    for fg, bg, tipo in _PARES:
        r = razao_contraste(PALETA[fg], PALETA[bg])
        linhas.append((f"{fg}/{bg}", round(r, 2), _ALVO[tipo], r >= _ALVO[tipo]))
    return linhas


def css():
    """Bloco <style> (só cor e espaçamento) para o app espelhar a paleta.

    Não injeta conteúdo HTML — apenas regras de cor/espaço sobre componentes
    nativos do Streamlit. Notas (st.caption) ficam >= 12 px (regra 7k).
    """
    p = PALETA
    return f"""<style>
    .stApp {{ background-color: {p["bg"]}; }}
    [data-testid="stMetricValue"] {{ color: {p["teal"]}; font-weight: 700; }}
    [data-testid="stMetricLabel"] {{ color: {p["text"]}; }}
    [data-testid="stCaptionContainer"], .stCaption {{
        color: {p["muted"]}; font-size: 12px; line-height: 1.35;
    }}
    [data-testid="stVerticalBlockBorderWrapper"] {{
        border-color: {p["grid"]}; border-radius: 10px;
    }}
    h1, h2, h3 {{ color: {p["text"]}; }}
    </style>"""


if __name__ == "__main__":
    print(f"{'par':16} {'razao':>6} {'alvo':>5} passa")
    for par, r, alvo, ok in contraste():
        print(f"{par:16} {r:6.2f} {alvo:5.1f} {'OK' if ok else 'FALHA'}")
