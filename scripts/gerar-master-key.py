#!/usr/bin/env python3
"""Gera a chave mestra local de 96 bytes.

A chave NÃO vai para o .env: fica em arquivo próprio, com permissão 0600, e o
caminho entra em QE_LOCAL_MASTER_KEY_PATH. Um .env vaza em screenshot com uma
facilidade que 96 bytes em outro arquivo não perdoa.

KMS local não é para produção — a chave mestra em disco ao lado da aplicação
anula boa parte do modelo de ameaça. Ele existe para a reunião em que ninguém
quer mexer em IAM. Em produção: AWS KMS, Azure Key Vault, GCP KMS ou KMIP.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

PADRAO = Path(__file__).resolve().parent.parent / "backend" / "secrets" / "master-key.bin"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, default=PADRAO)
    parser.add_argument("--forcar", action="store_true", help="sobrescreve uma chave existente")
    args = parser.parse_args()

    if args.saida.exists() and not args.forcar:
        # Sobrescrever a chave mestra é crypto shredding do dataset inteiro: sem
        # ela, nenhuma DEK do cofre volta a abrir.
        print(f"❌ {args.saida} já existe. Sobrescrever torna TODO o dado cifrado "
              f"irrecuperável. Use --forcar se é isso mesmo.", file=sys.stderr)
        return 1

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_bytes(secrets.token_bytes(96))
    os.chmod(args.saida, 0o600)

    print(f"✅ Chave mestra de 96 bytes em {args.saida} (modo 0600).")
    print(f"   QE_LOCAL_MASTER_KEY_PATH={args.saida}")
    print("   Não commite este arquivo. Ele já está no .gitignore.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
