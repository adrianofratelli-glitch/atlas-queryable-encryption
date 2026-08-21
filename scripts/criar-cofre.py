#!/usr/bin/env python3
"""Cria o cofre de chaves: índice único do keyVault e as três DEKs da demo.

As três estratégias existem ao mesmo tempo de propósito. O contraste é o ponto
pedagógico do módulo 05: uma DEK por titular dá o direito ao esquecimento mais
limpo que existe e cobra em documentos no cofre, chamadas ao KMS e pressão de
cache; uma DEK por inquilino é o desenho que a maioria dos clientes adota. Ter
as três na tela transforma "qual é o jeito certo" em "qual é o seu caso".
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from encryption import (  # noqa: E402
    client_encryption,
    descricao_kms,
    key_vault_collection,
    master_key_ref,
    nomes_dek,
)
from settings import settings  # noqa: E402

# Uma DEK por campo por coleção — não é escolha nossa: o Queryable Encryption
# recusa a coleção se dois campos compartilharem keyId (`Duplicate key ids are
# not allowed`, code 6338401). Cinco campos em duas coleções são dez DEKs.
NOMES = nomes_dek()


def main() -> int:
    descricao = descricao_kms()
    if not descricao["configurado"]:
        print(f"❌ KMS '{descricao['provedor']}' não configurado. Veja backend/.env.example.", file=sys.stderr)
        return 1
    print(f"→ KMS: {descricao['provedor']}" + ("" if descricao["producao"] else "  ⚠️  não é para produção"))

    cofre = key_vault_collection()
    # Sem este índice, dois keyAltName iguais convivem e a busca de DEK por nome
    # fica não determinística.
    cofre.create_index(
        "keyAltNames",
        unique=True,
        partialFilterExpression={"keyAltNames": {"$exists": True}},
    )
    print(f"→ índice único parcial em {settings.key_vault_ns}")
    print(f"→ {len(NOMES)} DEK(s) esperadas: uma por campo cifrado, por coleção")

    criadas = 0
    with client_encryption() as encryption:
        for nome in NOMES:
            if cofre.find_one({"keyAltNames": nome}):
                print(f"  = {nome} (já existe)")
                continue
            encryption.create_data_key(
                settings.kms_provider, master_key=master_key_ref() or None, key_alt_names=[nome]
            )
            criadas += 1
            print(f"  + {nome}")

    print(f"\n✅ Cofre pronto: {cofre.estimated_document_count()} DEK(s), {criadas} nova(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
