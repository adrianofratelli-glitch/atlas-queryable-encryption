#!/usr/bin/env python3
"""Seed determinístico da coleção cifrada.

Escreve em `clientes` pelo cliente CIFRADO — é a aplicação gravando, e o
plaintext nunca sai desta máquina. Uma coleção só: o contraste da tela vem de
dois CLIENTES lendo a mesma coleção, não de duas coleções.

    python seed_data.py            # 5.000 titulares — basta para a demo
    python seed_data.py --full     # 100.000; leva bem mais tempo e a tela não precisa
    python seed_data.py --drop     # recria do zero (leva junto as enxcol_.*)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bson import ObjectId
from pymongo.errors import CollectionInvalid

sys.path.insert(0, str(Path(__file__).resolve().parent))

from encryption import (  # noqa: E402
    COLECAO_CIFRADA,
    cliente_cifrado,
    cliente_claro,
    encrypted_fields,
)
from settings import settings  # noqa: E402

SEMENTE = 20260819
ARQUIVO_SEEDS = Path(__file__).resolve().parent / "data" / "demo_seeds.json"

NOMES = ["Marina", "Rafael", "Beatriz", "Caio", "Helena", "Otávio", "Lívia", "Bruno",
         "Camila", "Diego", "Fernanda", "Gustavo", "Isabela", "Leandro", "Natália"]
SOBRENOMES = ["Alves", "Barbosa", "Cardoso", "Duarte", "Esteves", "Ferreira", "Gomes",
              "Henriques", "Ibrahim", "Junqueira", "Lima", "Machado", "Nogueira"]
CIDADES = [("São Paulo", "SP"), ("Rio de Janeiro", "RJ"), ("Belo Horizonte", "MG"),
           ("Curitiba", "PR"), ("Porto Alegre", "RS"), ("Salvador", "BA"),
           ("Recife", "PE"), ("Fortaleza", "CE"), ("Goiânia", "GO"), ("Manaus", "AM")]
TENANTS = ["banco-alfa", "banco-beta"]


def cpf_sintetico(rng: random.Random) -> str:
    """CPF com dígito verificador válido, em faixa NÃO emitida (prefixo 999).

    Ele vai aparecer em screenshot; ele não pode pertencer a ninguém.
    """
    base = [9, 9, 9] + [rng.randint(0, 9) for _ in range(6)]
    for _ in range(2):
        peso = len(base) + 1
        soma = sum(digito * (peso - indice) for indice, digito in enumerate(base))
        resto = (soma * 10) % 11
        base.append(0 if resto == 10 else resto)
    return "".join(str(digito) for digito in base)


def faixa_salarial(salario: int) -> str:
    """Derivada em CLARO pela aplicação, a partir do salário ainda em memória.

    É a resposta do módulo 04: campo cifrado é campo de filtro e de leitura, não
    de análise. O que se agrega é a faixa, grossa o bastante para não
    reidentificar e fina o bastante para o relatório servir.
    """
    limites = [(5_000, "0-5k"), (10_000, "5k-10k"), (15_000, "10k-15k"),
               (25_000, "15k-25k"), (40_000, "25k-40k")]
    for teto, rotulo in limites:
        if salario < teto:
            return rotulo
    return "40k+"


def gerar(total: int) -> tuple[list[dict], list]:
    rng = random.Random(SEMENTE)
    agora = datetime.now(timezone.utc)
    documentos = []
    for indice in range(total):
        cidade, uf = CIDADES[rng.randrange(len(CIDADES))]
        # Massa concentrada nas faixas que a demo consulta: uma faixa que devolve
        # zero documento no palco parece falha.
        salario = int(rng.triangular(1_500, 45_000, 11_000))
        nome = f"{NOMES[rng.randrange(len(NOMES))]} {SOBRENOMES[rng.randrange(len(SOBRENOMES))]}"
        documentos.append({
            "_id": ObjectId(),
            "nome": nome,
            "cpf": cpf_sintetico(rng),
            "email": f"titular{indice}@exemplo.invalid",
            "salario": salario,
            "score_credito": rng.randint(0, 1_000),
            "observacoes": rng.choice([
                "cliente desde a abertura da conta digital",
                "analise de credito revisada no ultimo trimestre",
                "contato preferencial por aplicativo",
            ]),
            "cidade": cidade,
            "uf": uf,
            "tenant_id": TENANTS[indice % len(TENANTS)],
            "faixa_salarial": faixa_salarial(salario),
            "cadastro_em": agora - timedelta(days=rng.randint(0, 900)),
        })

    # O par plantado do módulo 02: dois titulares com o MESMO CPF. Sem plantar,
    # achar um par assim no palco é sorte.
    if len(documentos) >= 2:
        documentos[1]["cpf"] = documentos[0]["cpf"]
    par = [documentos[0]["_id"], documentos[1]["_id"]] if len(documentos) >= 2 else []
    return documentos, par


def dropar(db_claro) -> None:
    """Dropar coleção cifrada tem que levar junto as enxcol_.*. Metadata órfã de
    uma coleção que não existe mais faz a recriação falhar com uma mensagem que
    não menciona isso em lugar nenhum."""
    for nome in (COLECAO_CIFRADA, f"enxcol_.{COLECAO_CIFRADA}.esc", f"enxcol_.{COLECAO_CIFRADA}.ecoc"):
        db_claro.drop_collection(nome)


def criar_colecoes_cifradas(db_cifrado) -> None:
    for nome, definicao in encrypted_fields().items():
        colecao = nome.split(".", 1)[1]
        try:
            db_cifrado.create_collection(colecao, encryptedFields=definicao)
        except CollectionInvalid:
            pass  # já existe; o encryptedFields dela é imutável de qualquer forma


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="100.000 titulares")
    parser.add_argument("--drop", action="store_true", help="recria do zero")
    args = parser.parse_args()

    total = 100_000 if args.full else 5_000
    db_claro = cliente_claro()[settings.mongo_db]
    db_cifrado = cliente_cifrado()[settings.mongo_db]

    if args.drop:
        # DDL de coleção cifrada pega lock. Um seed anterior travado segura esse
        # lock e o create_collection seguinte espera para sempre, a 0% de CPU —
        # parece problema de rede e não é. Garanta um processo só.
        print("→ dropando coleções (inclui enxcol_.*)…", flush=True)
        dropar(db_claro)

    criar_colecoes_cifradas(db_cifrado)

    if db_claro[COLECAO_CIFRADA].count_documents({}, limit=1) and not args.drop:
        print("→ já semeado; use --drop para recriar.")
        return 0

    documentos, par = gerar(total)
    print(f"→ escrevendo {total} titulares em {COLECAO_CIFRADA} (cifrado)…")

    lote = 500
    for inicio in range(0, len(documentos), lote):
        fatia = documentos[inicio:inicio + lote]
        db_cifrado[COLECAO_CIFRADA].insert_many([dict(doc) for doc in fatia])
        print(f"  {min(inicio + lote, len(documentos))}/{len(documentos)}", end="\r", flush=True)

    # Índices só em campo NÃO cifrado. Índice comum sobre campo cifrado é
    # recusado pelo servidor — o módulo 04 tenta um de propósito.
    colecao = db_claro[COLECAO_CIFRADA]
    colecao.create_index("tenant_id")
    colecao.create_index("uf")
    colecao.create_index("cadastro_em")

    ARQUIVO_SEEDS.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO_SEEDS.write_text(json.dumps({
        "semente": SEMENTE,
        "total": total,
        "cpf_repetido": [str(_id) for _id in par],
        "tenants": TENANTS,
    }, indent=2))

    print(f"\n✅ {total} titulares em {COLECAO_CIFRADA} (cifrada).")
    print(f"   Par de CPF repetido gravado em {ARQUIVO_SEEDS.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
