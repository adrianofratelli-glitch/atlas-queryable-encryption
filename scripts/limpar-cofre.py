#!/usr/bin/env python3
"""Limpeza com escopo estrito das coleções da demo.

O script nunca aceita nome de coleção por parâmetro: escopo fixo, coleções
conhecidas. Mesma disciplina do cleanup do Atlas Showcase.

A ordem importa. A coleção cifrada sai primeiro, com as enxcol_.* junto —
metadata órfã de uma coleção que não existe mais faz a recriação falhar com uma
mensagem que não menciona isso. O cofre só sai com --chaves, porque apagá-lo por
acidente é o crypto shredding do dataset inteiro.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from encryption import COLECAO_CIFRADA, COLECAO_CLARA, cliente_claro, key_vault_collection  # noqa: E402
from settings import settings  # noqa: E402

ESCOPO = (
    COLECAO_CIFRADA,
    f"enxcol_.{COLECAO_CIFRADA}.esc",
    f"enxcol_.{COLECAO_CIFRADA}.ecoc",
    COLECAO_CLARA,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chaves", action="store_true",
                        help="apaga TAMBÉM o cofre — irreversível, todo ciphertext vira lixo")
    args = parser.parse_args()

    db = cliente_claro()[settings.mongo_db]
    for nome in ESCOPO:
        db.drop_collection(nome)
        print(f"  - {settings.mongo_db}.{nome}")

    if args.chaves:
        cofre = key_vault_collection()
        total = cofre.estimated_document_count()
        cofre.drop()
        print(f"  - {settings.key_vault_ns} ({total} DEK(s)) — irreversível")

    print("\n✅ Limpeza concluída. Rode scripts/criar-cofre.py e backend/seed_data.py para repor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
