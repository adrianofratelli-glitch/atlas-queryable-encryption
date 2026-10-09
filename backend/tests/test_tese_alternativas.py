"""Guarda da comparação com alternativas (achado QE-01 da revisão de 2026-10).

A tela e o README não podem afirmar que o pgcrypto impede o banco de filtrar:
o PostgreSQL filtra com `pgp_sym_decrypt` no `WHERE`, decifrando no servidor.
A diferença real é a fronteira de confiança — e é ela que o texto deve dizer.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
APP = (RAIZ / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")
README = (RAIZ / "README.md").read_text(encoding="utf-8")

FRASES_FALSAS = [
    "deixa de conseguir filtrar",
    "removes the database's ability to filter",
    "pgcrypto determinístico",
]


def test_sem_afirmacao_falsa_sobre_pgcrypto():
    for texto in (APP, README):
        for frase in FRASES_FALSAS:
            assert frase not in texto


def test_linha_pgcrypto_nao_e_impossibilidade_de_filtro():
    linha = re.search(r"\['pgcrypto[^\]]*\]", APP)
    assert linha, "a tabela de alternativas precisa ter uma linha para pgcrypto"
    assert "'nao'" not in linha.group(0)
    assert "servidor" in linha.group(0)


def test_fontes_oficiais_citadas():
    for texto in (APP, README):
        assert "postgresql.org/docs/current/pgcrypto.html" in texto
        assert "mongodb.com/docs/manual/core/queryable-encryption" in texto
