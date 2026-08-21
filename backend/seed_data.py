#!/usr/bin/env python3
"""Seed determinístico das duas coleções.

Escreve os MESMOS documentos, com os MESMOS _id, em `clientes` (pelo cliente
cifrado) e `clientes_claro` (pelo cliente claro). O mesmo _id dos dois lados é o
que permite ao módulo 02 provar que é o mesmo dado e ao módulo 06 comparar
documento a documento.

Este é o único lugar da PoV que escreve em `clientes_claro`.

    python seed_data.py            # 5.000 titulares
    python seed_data.py --full     # 100.000, para o storage do módulo 06 significar algo
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
    COLECAO_CIFRADA_BETA,
    COLECAO_CLARA,
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
    for cifrada in (COLECAO_CIFRADA, COLECAO_CIFRADA_BETA):
        for nome in (cifrada, f"enxcol_.{cifrada}.esc", f"enxcol_.{cifrada}.ecoc"):
            db_claro.drop_collection(nome)
    db_claro.drop_collection(COLECAO_CLARA)


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
    print(f"→ escrevendo {total} titulares em {COLECAO_CIFRADA} (cifrado) e {COLECAO_CLARA} (claro)…")

    lote = 500
    for inicio in range(0, len(documentos), lote):
        fatia = documentos[inicio:inicio + lote]
        db_cifrado[COLECAO_CIFRADA].insert_many([dict(doc) for doc in fatia])
        db_claro[COLECAO_CLARA].insert_many([dict(doc) for doc in fatia])
        # A coleção do tenant beta carrega SÓ o subconjunto dele, cifrado pela
        # DEK própria. É o que torna o crypto shredding por coorte demonstrável:
        # apagar aquela DEK não pode afetar o tenant alfa.
        beta = [dict(doc) for doc in fatia if doc["tenant_id"] == TENANTS[1]]
        if beta:
            db_cifrado[COLECAO_CIFRADA_BETA].insert_many(beta)
        print(f"  {min(inicio + lote, len(documentos))}/{len(documentos)}", end="\r", flush=True)

    # Índices só em campo NÃO cifrado. Índice comum sobre campo cifrado é
    # recusado pelo servidor — o módulo 04 tenta um de propósito.
    for colecao in (db_claro[COLECAO_CIFRADA], db_claro[COLECAO_CLARA]):
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

    beta = db_claro[COLECAO_CIFRADA_BETA].estimated_document_count()
    print(f"\n✅ {total} titulares em {COLECAO_CIFRADA} e {COLECAO_CLARA}; "
          f"{beta} em {COLECAO_CIFRADA_BETA} (DEK própria).")
    print(f"   Par de CPF repetido gravado em {ARQUIVO_SEEDS.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
