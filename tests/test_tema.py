"""Testes do tema (paleta, contraste WCAG e CSS)."""

import tema


def test_contraste_todos_os_pares_passam():
    linhas = tema.contraste()
    assert len(linhas) == 11
    assert all(ok for _, _, _, ok in linhas), [ln for ln in linhas if not ln[3]]


def test_razao_contraste_conhecida():
    # texto claro sobre fundo escuro: alto contraste (~15:1).
    r = tema.razao_contraste(tema.PALETA["text"], tema.PALETA["bg"])
    assert round(r, 2) == 15.14
    # par simétrico dá a mesma razão.
    assert tema.razao_contraste("#FFFFFF", "#000000") == tema.razao_contraste(
        "#000000", "#FFFFFF"
    )


def test_grid_passa_mesmo_sendo_o_menor():
    r = tema.razao_contraste(tema.PALETA["grid"], tema.PALETA["bg"])
    assert r >= 3.0


def test_css_espelha_a_paleta():
    css = tema.css()
    assert tema.PALETA["bg"] in css
    assert tema.PALETA["teal"] in css
    assert "font-size: 12px" in css  # notas >= 12 px (regra 7k)
    assert css.strip().startswith("<style>")
