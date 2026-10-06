#!/usr/bin/env python3
"""Reset único da demo: coleções, cofre, DEKs, coleção cifrada, dados e índices.

    python scripts/reset_demo.py                    # mantém as DEKs existentes
    python scripts/reset_demo.py --recriar-chaves   # apaga o cofre e gera DEKs novas
    python scripts/reset_demo.py --full             # 100.000 titulares em vez de 5.000

Idempotente. Em banco `*_test` roda direto; contra o banco da demo exige
`ALLOW_DEMO_DB_WRITE=1`. Pare o backend antes de `--recriar-chaves`: ele guarda o
keyId de cada campo na memória e, com DEKs novas, só volta a abrir o dado depois
de reiniciar.

Etapas, na ordem que o Queryable Encryption exige:
1. `limpar-cofre.py` dropa `clientes` e as `enxcol_.*` (e o cofre, com
   `--recriar-chaves`). Metadata órfã faz a recriação falhar.
2. `criar-cofre.py` garante o índice único parcial em `keyAltNames` e cria só as
   DEKs que faltam.
3. `seed_data.py --drop` recria a coleção com `encryptedFields`, grava os
   titulares pelo cliente cifrado e cria os índices nos campos em claro.
4. Verificação: contagem, par plantado, `Binary(subtype 6)` em todo campo
   cifrado lido sem chave e uma igualdade cifrada que acha o titular.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from settings import arquivo_seeds, exigir_permissao_de_escrita, settings  # noqa: E402


def _rodar(*args: str) -> None:
    inicio = time.perf_counter()
    print(f"\n▶ {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, *args], cwd=RAIZ, check=True)
    print(f"  ({time.perf_counter() - inicio:.1f} s)", flush=True)


def verificar(total_esperado: int) -> list[str]:
    """Confere a demo pelo mesmo caminho que a tela usa. Devolve os problemas."""
    from bson import Binary, ObjectId

    from encryption import CAMPOS_CIFRADOS, COLECAO_CIFRADA, cliente_cifrado, cliente_claro

    problemas: list[str] = []
    claro = cliente_claro()[settings.mongo_db][COLECAO_CIFRADA]
    cifrado = cliente_cifrado()[settings.mongo_db][COLECAO_CIFRADA]

    total = claro.count_documents({})
    if total != total_esperado:
        problemas.append(f"{total} documentos; esperado {total_esperado}")

    indices = set(claro.index_information())
    for campo in ("tenant_id", "uf", "cadastro_em"):
        if f"{campo}_1" not in indices:
            problemas.append(f"índice {campo}_1 ausente")

    seeds = json.loads(arquivo_seeds().read_text())
    par = [ObjectId(bruto) for bruto in seeds.get("cpf_repetido", [])]
    if claro.count_documents({"_id": {"$in": par}}) != 2:
        problemas.append("par plantado ausente")

    bruto = claro.find_one({}, {campo: 1 for campo in CAMPOS_CIFRADOS})
    for campo in CAMPOS_CIFRADOS:
        valor = (bruto or {}).get(campo)
        if not (isinstance(valor, Binary) and valor.subtype == 6):
            problemas.append(f"{campo} não está como Binary(subtype 6) na leitura sem chave")

    legivel = cifrado.find_one({"_id": bruto["_id"]}, {"cpf": 1}) if bruto else None
    cpf = (legivel or {}).get("cpf")
    if not isinstance(cpf, str):
        problemas.append("cliente cifrado não decifrou o cpf")
    elif cifrado.count_documents({"cpf": cpf}) < 1:
        problemas.append("igualdade cifrada não achou o titular")
    elif claro.count_documents({"cpf": cpf}) != 0:
        problemas.append("cliente sem chave casou o cpf em claro")
    return problemas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recriar-chaves", action="store_true",
                        help="apaga o cofre e cria DEKs novas (crypto shredding do dataset anterior)")
    parser.add_argument("--full", action="store_true", help="100.000 titulares")
    args = parser.parse_args()

    exigir_permissao_de_escrita("reset_demo.py")
    print(f"→ reset de {settings.mongo_db} (cofre {settings.key_vault_ns})")
    inicio = time.perf_counter()

    _rodar("scripts/limpar-cofre.py", *(["--chaves"] if args.recriar_chaves else []))
    _rodar("scripts/criar-cofre.py")
    _rodar("backend/seed_data.py", "--drop", *(["--full"] if args.full else []))

    problemas = verificar(100_000 if args.full else 5_000)
    if problemas:
        print("\n❌ Reset terminou com problemas:\n  - " + "\n  - ".join(problemas), file=sys.stderr)
        return 1
    print(f"\n✅ Demo resetada e verificada em {time.perf_counter() - inicio:.1f} s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
