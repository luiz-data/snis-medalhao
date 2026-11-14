"""Configuração central do logging do pipeline.

Único ponto onde se decide nível, formato e destino da saída. Cada módulo usa
`logger = logging.getLogger(__name__)` e não configura nada — assim o prefixo
da linha identifica a etapa (`pipeline.gold: ...`) e dá para silenciar ou
elevar um módulo isolado sem tocar no código dele.

Sem timestamp no formato: a saída do pipeline é um relatório lido de uma vez no
terminal (~60 linhas) e a hora de cada linha não é o que se lê ali. Se um dia
houver log em arquivo, o timestamp entra só no handler de arquivo.
"""

import logging

FORMATO = "%(levelname)s %(name)s: %(message)s"
NIVEL = logging.INFO


def configurar(nivel=NIVEL):
    """Configura o root logger. Chamada por executar.py e pelos `__main__`.

    Os módulos de etapa também rodam sozinhos (`uv run python -m
    pipeline.gold`); sem esta chamada eles cairiam no fallback WARNING do root
    logger e todo o INFO de progresso desapareceria.
    """
    logging.basicConfig(format=FORMATO, level=nivel)
