#!/usr/bin/env python3
"""Overhead medido do Queryable Encryption contra a mesma massa em claro.

Roda SÓ em banco `*_test` já resetado (`scripts/reset_demo.py`). Cria
`bench_claro` com os MESMOS titulares (mesma semente do seed) e índices em
`cpf` e `salario` — a comparação justa é com uma coleção em claro indexada, não
com um collscan. Mede, pelo mesmo cluster e pela mesma rede:

- igualdade em `cpf` e faixa em `salario`: p50/p95 em ms, N consultas cada;
- insert unitário: p50/p95 em ms (os titulares extras são apagados no fim);
- prefixo, sufixo e trecho cifrados (MongoDB 9.0+): p50/p95 em ms. Não há
  par em claro justo — o equivalente em claro seria `$regex`, que o workspace
  proíbe e que não usa índice —, então o número é lido contra o `ping`;
- storage: coleção cifrada + `enxcol_.*` contra a coleção em claro, em bytes
  lógicos (`size` + índices) e em disco (`storageSize` + índices, comprimido),
  por coleção, ANTES e DEPOIS de `compactStructuredEncryptionData`;
- prova de rede: o comando capturado pelo CommandListener, em BSON, não contém
  os bytes do CPF nem do trecho de e-mail buscados.

    python scripts/bench_qe.py               # 100 consultas por tipo
    python scripts/bench_qe.py --consultas 300
    python scripts/bench_qe.py --compactar   # tenta compactStructuredEncryptionData antes de medir storage

O compact é opt-in: medido em 2026-11-12 (Atlas 9.0.7, 5.000 titulares, ~1 M
entradas na `ecoc` por causa do campo de substring), ele NÃO conclui — a
transação interna estoura `transactionLifetimeLimitSeconds` (padrão 60 s), a
`ecoc` fica renomeada como `ecoc.compact` e cada tentativa ainda acrescenta
entradas à `esc`. Ver docs/adr/0004-bench-storage-e-compactacao.md.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import bson

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from pymongo import MongoClient  # noqa: E402

from encryption import (  # noqa: E402
    APP_NAME,
    COLECAO_CIFRADA,
    _auto_encryption_opts,
    cliente_cifrado,
    cliente_claro,
    executar_capturando,
    versao_servidor,
)
from routers.demo import BUSCAS_STRING  # noqa: E402
from seed_data import gerar  # noqa: E402
from settings import BACKEND_DIR, alvos_de_escrita, banco_de_teste, settings  # noqa: E402

COLECAO_CLARA = "bench_claro"


def _ms(fn) -> float:
    inicio = time.perf_counter()
    fn()
    return (time.perf_counter() - inicio) * 1000


def percentil(amostras: list[float], p: float) -> float:
    """Percentil por posto mais próximo (nearest-rank): o menor valor com pelo
    menos p% das amostras abaixo ou iguais. Com 30 inserts, o p95 é o 29º valor;
    a fórmula antiga (`int(n*0.95) - 1`) pegava o 28º e subestimava a cauda."""
    if not amostras:
        raise ValueError("sem amostras")
    ordenadas = sorted(amostras)
    return ordenadas[max(0, math.ceil(len(ordenadas) * p / 100) - 1)]


def _resumo(amostras: list[float]) -> dict:
    return {"n": len(amostras), "p50_ms": round(statistics.median(amostras), 1),
            "p95_ms": round(percentil(amostras, 95), 1)}


def colecoes_de_metadados(nomes: list[str], colecao: str) -> list[str]:
    """As `enxcol_.<colecao>.*` existentes: `esc`, `ecoc` e, DURANTE um compact,
    `ecoc.compact` (o servidor renomeia a `ecoc` e a consome aos poucos). Contar
    só `esc` + `ecoc` no meio de um compact some com centenas de MB."""
    prefixo = f"enxcol_.{colecao}."
    return sorted(nome for nome in nomes if nome.startswith(prefixo))


def _tamanhos(db, nome: str) -> dict:
    """Bytes lógicos (o que o WiredTiger descomprime) e em disco (comprimido)."""
    try:
        stats = db.command("collStats", nome)
    except Exception:
        return {"docs": 0, "logico": 0, "disco": 0, "indices": 0}
    indices = int(stats.get("totalIndexSize", 0))
    return {
        "docs": int(stats.get("count", 0)),
        "logico": int(stats.get("size", 0)) + indices,
        "disco": int(stats.get("storageSize", 0)) + indices,
        "indices": indices,
    }


def storage(db, colecao: str) -> dict:
    """Storage por coleção da família cifrada, com totais lógico e em disco."""
    nomes = colecoes_de_metadados(db.list_collection_names(), colecao)
    partes = {nome: _tamanhos(db, nome) for nome in (colecao, *nomes)}
    return {
        "por_colecao": partes,
        "logico": sum(p["logico"] for p in partes.values()),
        "disco": sum(p["disco"] for p in partes.values()),
    }


def razao(a: int, b: int) -> float | None:
    return round(a / b, 2) if b else None


def compactar(colecao: str) -> dict:
    """`compactStructuredEncryptionData` por um cliente cifrado só para isso.

    O comando precisa sair por auto-encryption (o driver anexa os
    compactionTokens derivados das DEKs), mas o cliente da aplicação tem
    socketTimeoutMS de 16 s; com ~1 M entradas na `ecoc` o compact leva minutos
    e o cliente desistia enquanto o servidor seguia compactando — o storage
    "depois" saía igual ao "antes". Aqui o timeout de socket é desligado e o
    tempo é limitado no servidor (maxTimeMS não se aplica a este comando, então
    o limite é o do processo).
    """
    cliente = MongoClient(settings.mongo_uri, appname=f"{APP_NAME}-bench-compact",
                          auto_encryption_opts=_auto_encryption_opts(),
                          serverSelectionTimeoutMS=settings.mongo_timeout_ms, socketTimeoutMS=None)
    try:
        inicio = time.perf_counter()
        resposta = cliente[settings.mongo_db].command("compactStructuredEncryptionData", colecao)
        stats = resposta.get("stats", {})
        return {"executada": True, "ms": round((time.perf_counter() - inicio) * 1000, 1),
                "stats": json.loads(json.dumps(stats, default=str))}
    except Exception as exc:  # versão/permissão: registra e segue com o estado atual
        return {"executada": False, "erro": f"{type(exc).__name__}: {str(exc)[:200]}"}
    finally:
        cliente.close()


def termos_de_string(modo: str, exemplo: str, n: int, rng: random.Random) -> list[str]:
    """N termos do mesmo formato do exemplo da tela, dentro dos limites do schema.

    Prefixo: `titularNN` (3–20 caracteres); sufixo: `N@exemplo.invalid` (≤ 30);
    trecho: `NN@exe`/exemplo da tela (3–6, o `strMaxQueryLength` do campo). Todos
    existem na massa de 5.000, então todo termo deve achar documento.
    """
    termos = []
    for _ in range(n):
        d = rng.randrange(10, 100)
        if modo == "prefixo":
            termos.append(f"titular{d}")
        elif modo == "sufixo":
            termos.append(f"{d % 10}@exemplo.invalid")
        else:
            termos.append(f"{d}@exe" if rng.random() < 0.5 else exemplo)
    return termos


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--consultas", type=int, default=100)
    parser.add_argument("--inserts", type=int, default=30)
    parser.add_argument("--compactar", action="store_true",
                        help="tenta compactStructuredEncryptionData antes de medir o storage (ver ADR 0004)")
    args = parser.parse_args()

    # Banco da coleção E banco do cofre: o bench cria DEK em cache, insere e
    # (com --compactar) mexe em metadados; cofre da demo com QE_DB de teste
    # também é recusado, como nos testes live.
    fora_de_teste = [nome for nome in alvos_de_escrita(settings) if not banco_de_teste(nome)]
    if fora_de_teste:
        print(f"❌ bench_qe.py só roda com QE_DB e QE_KEY_VAULT_NS em *_test (fora: {', '.join(fora_de_teste)}).",
              file=sys.stderr)
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

    # Buscas de string cifradas (9.0+). Mesmos exemplos fixos da tela, mais
    # variações do mesmo formato para não medir só o cache de um termo.
    maior, _, _ = versao_servidor()
    resultado["string"] = {}
    if maior >= 9:
        print(f"→ {args.consultas} buscas por prefixo, sufixo e trecho (cifrado)…", flush=True)
        for modo, item in BUSCAS_STRING.items():
            termos = termos_de_string(modo, item["valor"], args.consultas, rng)
            amostras, achou = [], 0
            for termo in termos:
                filtro = {"$expr": {item["operador"]: {"input": f"${item['campo']}", item["argumento"]: termo}}}
                docs: list = []
                amostras.append(_ms(lambda: docs.extend(cifrada.find(filtro, {"_id": 1}).limit(10))))
                achou += bool(docs)
            resultado["string"][modo] = {**_resumo(amostras), "com_resultado": achou}
    else:
        resultado["string"] = {"pulado": f"MongoDB {maior}.x; buscas de string exigem 9.0+"}

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
    # Mesma contagem dos dois lados antes de medir storage (5.000 × 5.000).
    clara.delete_many({"_id": {"$in": inseridos["claro"]}})

    claro_bytes = _tamanhos(db_claro, COLECAO_CLARA)
    antes = storage(db_claro, COLECAO_CIFRADA)
    compactacao: dict = {"executada": False}
    if args.compactar:
        # Cada insert cifrado deixa entradas na `ecoc`; o compact as consolida
        # na `esc`. O comando sai pelo cliente CIFRADO: o driver acrescenta os
        # compactionTokens derivados das DEKs — sem eles o servidor recusa.
        print("→ compactStructuredEncryptionData (minutos com ~1 M entradas na ecoc)…", flush=True)
        compactacao = compactar(COLECAO_CIFRADA)
    depois = storage(db_claro, COLECAO_CIFRADA) if compactacao["executada"] else antes

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
    if maior >= 9:
        item = BUSCAS_STRING["trecho"]
        filtro = {"$expr": {item["operador"]: {"input": f"${item['campo']}", item["argumento"]: item["valor"]}}}
        _, enviado = executar_capturando("find", COLECAO_CIFRADA, lambda: list(cifrada.find(filtro).limit(1)))
        prova["trecho_capturado"] = enviado is not None
        prova["trecho_em_claro_no_comando"] = item["valor"].encode() in bson.encode(enviado or {})

    db_claro.drop_collection(COLECAO_CLARA)

    _, _, versao = versao_servidor()
    saida = {
        "medido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mongodb": versao,
        # Onde a medição rodou: latência absoluta é da rede desta máquina.
        "cliente": {"so": platform.system(), "arquitetura": platform.machine(),
                    "python": platform.python_version()},
        "titulares": total,
        "rtt_ping": rtt,
        "acertos_igualdade": acertos,
        **resultado,
        # Compatível com o formato anterior: `cifrado_com_enxcol` e `razao` em bytes lógicos.
        "storage_bytes": {
            "cifrado_com_enxcol": antes["logico"], "claro_indexado": claro_bytes["logico"],
            "razao": razao(antes["logico"], claro_bytes["logico"]),
            "claro": claro_bytes,
            "antes_do_compact": antes,
            "depois_do_compact": depois,
            "razao_em_disco_depois": razao(depois["disco"], claro_bytes["disco"]),
        },
        "compactacao": compactacao,
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
    for modo, r in resultado["string"].items() if isinstance(resultado["string"], dict) else ():
        if isinstance(r, dict):
            print(f"| {modo} (só QE) | {r['p50_ms']} / {r['p95_ms']} | — | {r['p50_ms'] / rtt['p50_ms']:.2f}x ping |")
    mb = 1024 * 1024
    print(f"\nStorage lógico: QE {antes['logico'] / mb:.1f} MB × claro {claro_bytes['logico'] / mb:.1f} MB")
    print(f"Storage em disco antes/depois do compact: {antes['disco'] / mb:.1f} → {depois['disco'] / mb:.1f} MB "
          f"(claro {claro_bytes['disco'] / mb:.1f} MB)")
    ok = prova["comando_capturado"] and not prova["plaintext_no_comando"] and prova["binary_subtype6_no_filtro"]
    ok = ok and not prova.get("trecho_em_claro_no_comando", False)
    return 0 if ok and acertos["cifrado"] == acertos["claro"] == len(cpfs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
