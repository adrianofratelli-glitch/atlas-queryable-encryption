#!/usr/bin/env python3
"""Overhead medido do Queryable Encryption contra a mesma massa em claro.

Roda SÓ em banco `*_test` já resetado (`scripts/reset_demo.py`). Cria
`bench_claro` com os MESMOS titulares (mesma semente do seed) e índices em
`cpf` e `salario` — a comparação justa é com uma coleção em claro indexada, não
com um collscan. Mede, pelo mesmo cluster e pela mesma rede:

- igualdade em `cpf` e faixa em `salario`: p50/p95 em ms, N consultas cada;
- insert unitário: p50/p95 em ms (os titulares extras são apagados no fim);
- storage: coleção cifrada + `enxcol_.*` contra a coleção em claro;
- prova de rede: o comando capturado pelo CommandListener, em BSON, não contém
  os bytes do CPF buscado.

    python scripts/bench_qe.py               # 100 consultas por tipo
    python scripts/bench_qe.py --consultas 300
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import bson

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from encryption import (  # noqa: E402
    COLECAO_CIFRADA,
    cliente_cifrado,
    cliente_claro,
    executar_capturando,
    versao_servidor,
)
from seed_data import gerar  # noqa: E402
from settings import BACKEND_DIR, banco_de_teste, settings  # noqa: E402

COLECAO_CLARA = "bench_claro"


def _ms(fn) -> float:
    inicio = time.perf_counter()
    fn()
    return (time.perf_counter() - inicio) * 1000


def _resumo(amostras: list[float]) -> dict:
    ordenadas = sorted(amostras)
    p95 = ordenadas[max(0, int(len(ordenadas) * 0.95) - 1)]
    return {"n": len(amostras), "p50_ms": round(statistics.median(ordenadas), 1), "p95_ms": round(p95, 1)}


def _tamanho(db, nome: str) -> int:
    try:
        stats = db.command("collStats", nome)
    except Exception:
        return 0
    return int(stats.get("size", 0)) + int(stats.get("totalIndexSize", 0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--consultas", type=int, default=100)
    parser.add_argument("--inserts", type=int, default=30)
    args = parser.parse_args()

    if not banco_de_teste(settings.mongo_db):
        print("❌ bench_qe.py só roda em banco *_test.", file=sys.stderr)
        return 1

    db_claro = cliente_claro()[settings.mongo_db]
    cifrada = cliente_cifrado()[settings.mongo_db][COLECAO_CIFRADA]
    total = db_claro[COLECAO_CIFRADA].count_documents({})
    if not total:
        print("❌ coleção cifrada vazia; rode scripts/reset_demo.py antes.", file=sys.stderr)
        return 1

    documentos, _ = gerar(total)
    print(f"→ {total} titulares; criando {COLECAO_CLARA} com a mesma massa…", flush=True)
    db_claro.drop_collection(COLECAO_CLARA)
    clara = db_claro[COLECAO_CLARA]
    for inicio in range(0, len(documentos), 1000):
        clara.insert_many([dict(doc) for doc in documentos[inicio:inicio + 1000]])
    clara.create_index("cpf")
    clara.create_index("salario")

    rng = random.Random(7)
    cpfs = [documentos[rng.randrange(len(documentos))]["cpf"] for _ in range(args.consultas)]
    faixas = []
    for _ in range(args.consultas):
        piso = rng.randrange(2_000, 40_000, 500)
        faixas.append({"$gte": piso, "$lte": piso + 2_000})

    # Aquecimento: conexão, DEKs no cache do driver, plano de execução.
    for colecao in (cifrada, clara):
        list(colecao.find({"cpf": cpfs[0]}).limit(5))
        list(colecao.find({"salario": faixas[0]}).limit(5))

    # Linha de base da rede: um `ping` é o round-trip sem trabalho no servidor.
    # Todo número abaixo carrega esse custo dos dois lados; sem ele, um RTT alto
    # parece overhead de criptografia.
    rtt = _resumo([_ms(lambda: cliente_claro().admin.command("ping")) for _ in range(30)])

    print(f"→ {args.consultas} igualdades e {args.consultas} faixas por lado…", flush=True)
    resultado: dict = {"igualdade": {}, "faixa": {}, "insert": {}}
    acertos = {"cifrado": 0, "claro": 0}
    for lado, colecao in (("cifrado", cifrada), ("claro", clara)):
        amostras = []
        for cpf in cpfs:
            docs: list = []
            amostras.append(_ms(lambda: docs.extend(colecao.find({"cpf": cpf}, {"_id": 1}).limit(5))))
            acertos[lado] += bool(docs)
        resultado["igualdade"][lado] = _resumo(amostras)
        amostras = [_ms(lambda: list(colecao.find({"salario": f}, {"_id": 1}).limit(10))) for f in faixas]
        resultado["faixa"][lado] = _resumo(amostras)

    print(f"→ {args.inserts} inserts unitários por lado…", flush=True)
    extras, _ = gerar(args.inserts)
    inseridos: dict[str, list] = {"cifrado": [], "claro": []}
    for lado, colecao in (("cifrado", cifrada), ("claro", clara)):
        amostras = []
        for doc in extras:
            novo = {k: v for k, v in doc.items() if k != "_id"}
            novo["_id"] = bson.ObjectId()
            amostras.append(_ms(lambda: colecao.insert_one(novo)))
            inseridos[lado].append(novo["_id"])
        resultado["insert"][lado] = _resumo(amostras)
    db_claro[COLECAO_CIFRADA].delete_many({"_id": {"$in": inseridos["cifrado"]}})

    bytes_cifrado = sum(_tamanho(db_claro, nome) for nome in (
        COLECAO_CIFRADA, f"enxcol_.{COLECAO_CIFRADA}.esc", f"enxcol_.{COLECAO_CIFRADA}.ecoc"))
    bytes_claro = _tamanho(db_claro, COLECAO_CLARA)

    # Prova de rede: os bytes do CPF não estão no comando que saiu.
    alvo = cpfs[0]
    _, enviado = executar_capturando("find", COLECAO_CIFRADA, lambda: list(cifrada.find({"cpf": alvo}).limit(1)))
    bson_enviado = bson.encode(enviado or {})
    prova = {
        "comando_capturado": enviado is not None,
        "plaintext_no_comando": alvo.encode() in bson_enviado,
        "binary_subtype6_no_filtro": isinstance((enviado or {}).get("filter", {}).get("cpf", {}).get("$eq"),
                                                bson.Binary),
    }

    db_claro.drop_collection(COLECAO_CLARA)

    maior, menor, versao = versao_servidor()
    saida = {
        "medido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mongodb": versao,
        "titulares": total,
        "rtt_ping": rtt,
        "acertos_igualdade": acertos,
        **resultado,
        "storage_bytes": {"cifrado_com_enxcol": bytes_cifrado, "claro_indexado": bytes_claro,
                          "razao": round(bytes_cifrado / bytes_claro, 2) if bytes_claro else None},
        "prova_de_rede": prova,
    }
    destino = BACKEND_DIR / "data" / f"bench.{settings.mongo_db}.json"
    destino.write_text(json.dumps(saida, indent=2))
    print(json.dumps(saida, indent=2))

    def fator(tipo):
        a, b = resultado[tipo]["cifrado"]["p50_ms"], resultado[tipo]["claro"]["p50_ms"]
        return f"{a / b:.2f}x" if b else "—"

    print(f"\nRTT (ping) p50/p95: {rtt['p50_ms']} / {rtt['p95_ms']} ms")
    print("| operação | QE p50 / p95 (ms) | claro p50 / p95 (ms) | fator p50 |")
    print("|---|---|---|---|")
    for tipo in ("igualdade", "faixa", "insert"):
        c, p = resultado[tipo]["cifrado"], resultado[tipo]["claro"]
        print(f"| {tipo} | {c['p50_ms']} / {c['p95_ms']} | {p['p50_ms']} / {p['p95_ms']} | {fator(tipo)} |")
    ok = prova["comando_capturado"] and not prova["plaintext_no_comando"] and prova["binary_subtype6_no_filtro"]
    return 0 if ok and acertos["cifrado"] == acertos["claro"] == len(cpfs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
