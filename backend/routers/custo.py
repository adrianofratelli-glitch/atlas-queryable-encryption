"""Módulo 06 — Preço da privacidade.

O número que decide se o projeto acontece. Duas coleções com o MESMO dataset,
uma cifrada e uma em claro, comparadas em storage, latência de escrita e
latência de leitura.

Três armadilhas de medição, todas cobertas aqui:

1. A primeira leitura paga o KMS (rede). Ela é aquecida antes e reportada
   separadamente — é informação legítima ("quanto custa o cold start"), só não
   pode virar custo por operação.
2. Cache do WiredTiger frio faz a coleção cifrada parecer muito pior. As duas
   são aquecidas com o mesmo número de leituras antes de medir.
3. A comparação só vale com o mesmo dataset e o mesmo número de campos.

E o custo de escrita é LOCAL: a cifragem acontece na aplicação, não no servidor.
Ele depende do notebook do apresentador, não do cluster, e a resposta diz isso
para o cliente não atribuir ao Atlas.
"""

from __future__ import annotations

import statistics
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from ._comum import erro_do_servidor
from encryption import CAMPOS_CIFRADOS, COLECAO_CIFRADA, COLECAO_CLARA, cliente_cifrado, cliente_claro
from settings import settings

router = APIRouter(prefix="/custo", tags=["06 · preço da privacidade"])

AQUECIMENTO = 20

# Acima disso, a rede do apresentador domina toda medição e nenhum número desta
# tela diz mais nada sobre o produto. Já medi 238 ms de RTT puro num notebook
# saindo por VPN — com esse piso, uma consulta de 253 ms é 15 ms de trabalho e
# 238 ms de estrada.
RTT_SUSPEITO_MS = 50


def _linha_de_base() -> dict:
    """RTT puro até o cluster: `ping`, sem trabalho nenhum do lado do servidor.

    Sem esse piso ao lado, todo número de latência desta PoV é lido como custo da
    criptografia — e na maior parte das vezes ele é custo de estrada. É a mesma
    disciplina do `/streaming/folga` do Atlas Showcase: um número de desempenho
    tem que dizer de quem foi o teto atingido.
    """
    admin = cliente_claro().admin
    admin.command("ping")  # aquece a conexão; a primeira paga o handshake
    amostras = []
    for _ in range(15):
        inicio = time.perf_counter()
        admin.command("ping")
        amostras.append((time.perf_counter() - inicio) * 1000)
    base = _percentis(amostras)
    base["suspeito"] = base["p50"] > RTT_SUSPEITO_MS
    base["nota"] = (
        "RTT alto: confirme que o notebook não está saindo por VPN antes de "
        "atribuir qualquer latência desta tela ao Atlas ou à criptografia."
        if base["suspeito"] else
        "RTT dentro do esperado para o mesmo continente."
    )
    return base


def _acima_da_base(medida: dict, base: dict) -> dict:
    """O trabalho real, descontada a estrada."""
    return {
        "p50": round(max(0.0, medida["p50"] - base["p50"]), 2),
        "p95": round(max(0.0, medida["p95"] - base["p95"]), 2),
    }


def _stats(nome: str) -> dict:
    db = cliente_claro()[settings.mongo_db]
    try:
        bruto = db.command("collStats", nome)
    except Exception:
        return {"colecao": nome, "existe": False}
    return {
        "colecao": nome,
        "existe": True,
        "documentos": bruto.get("count", 0),
        "tamanho_bytes": bruto.get("size", 0),
        "armazenado_bytes": bruto.get("storageSize", 0),
        "indices_bytes": bruto.get("totalIndexSize", 0),
    }


@router.get("/storage")
def storage():
    """As enxcol_.* CONTAM. Ignorá-las é subestimar e virar surpresa em produção."""
    cifrada = _stats(COLECAO_CIFRADA)
    clara = _stats(COLECAO_CLARA)
    esc = _stats(f"enxcol_.{COLECAO_CIFRADA}.esc")
    ecoc = _stats(f"enxcol_.{COLECAO_CIFRADA}.ecoc")

    total_cifrado = sum(
        item.get("armazenado_bytes", 0) + item.get("indices_bytes", 0)
        for item in (cifrada, esc, ecoc)
    )
    total_claro = clara.get("armazenado_bytes", 0) + clara.get("indices_bytes", 0)
    comparavel = clara.get("existe") and cifrada.get("existe") and total_claro > 0
    mesmo_dataset = comparavel and cifrada.get("documentos") == clara.get("documentos")

    # O FATOR SOZINHO ENGANA, e engana para cima. O custo do Queryable
    # Encryption é aproximadamente CONSTANTE por campo cifrado (um payload de
    # subtipo 6 tem centenas de bytes, e as enxcol_ crescem com contention ×
    # documentos), enquanto o denominador é o tamanho do documento em claro.
    # Documento pequeno, como o desta PoV, produz um múltiplo enorme; o mesmo
    # dado dentro de um documento realista de negócio produz um múltiplo bem
    # menor. Reportar bytes por documento e por campo é o número honesto — o
    # fator só faz sentido ao lado do tamanho do documento que o gerou.
    documentos = cifrada.get("documentos") or 0
    campos = len(CAMPOS_CIFRADOS)
    por_documento = round((total_cifrado - total_claro) / documentos, 1) if documentos else None

    return {
        "cifrada": cifrada,
        "clara": clara,
        "metadados": {"esc": esc, "ecoc": ecoc},
        "total_cifrado_bytes": total_cifrado,
        "total_claro_bytes": total_claro,
        "fator": round(total_cifrado / total_claro, 2) if comparavel else None,
        "overhead_por_documento_bytes": por_documento,
        "overhead_por_campo_bytes": round(por_documento / campos, 1) if por_documento else None,
        "doc_claro_medio_bytes": round(total_claro / documentos, 1) if documentos else None,
        "campos_cifrados": campos,
        "nota_fator": (
            "O fator depende do tamanho do documento em claro, não só da "
            "criptografia: o custo por campo cifrado é praticamente constante. "
            "Documento pequeno infla o múltiplo. Use o overhead por documento."
        ),
        "tier": settings.cluster_tier or None,
        "nota_tier": _nota_tier(),
        "mesmo_dataset": mesmo_dataset,
        "aviso": None if mesmo_dataset else "As duas coleções têm contagens diferentes; rode seed_data.py --drop antes de comparar.",
    }


def _nota_tier() -> str:
    """Um número de latência ou de storage sem o tier ao lado não significa nada."""
    if settings.cluster_tier:
        return f"Medido em {settings.cluster_tier}. Outro tier dá outro número."
    return "Preencha QE_CLUSTER_TIER no .env; um número sem tier ao lado não significa nada."


def _percentis(amostras: list[float]) -> dict:
    ordenado = sorted(amostras)
    def p(q: float) -> float:
        if not ordenado:
            return 0.0
        indice = min(len(ordenado) - 1, int(round(q * (len(ordenado) - 1))))
        return round(ordenado[indice], 2)
    return {
        "n": len(ordenado),
        "p50": p(0.50),
        "p95": p(0.95),
        "media": round(statistics.fmean(ordenado), 2) if ordenado else 0.0,
    }


def _documento(indice: int) -> dict:
    return {
        "nome": f"Benchmark {indice}",
        "cpf": f"{indice:011d}",
        "email": f"bench{indice}@exemplo.invalid",
        "salario": 1_500 + (indice % 40_000),
        "score_credito": indice % 1_000,
        "observacoes": "documento de benchmark",
        "cidade": "São Paulo",
        "uf": "SP",
        "tenant_id": "bench",
        "faixa_salarial": "bench",
        "cadastro_em": datetime.now(timezone.utc),
        "benchmark": True,
    }


@router.get("/escrita")
def escrita(docs: int = Query(None, ge=10, le=5_000)):
    """N inserts em cada coleção, um a um, com p50/p95."""
    total = docs or min(settings.bench_docs, 5_000)
    try:
        col_cif = cliente_cifrado()[settings.mongo_db][COLECAO_CIFRADA]
        col_clr = cliente_claro()[settings.mongo_db][COLECAO_CLARA]

        medidas: dict[str, list[float]] = {"cifrada": [], "clara": []}
        primeira: dict[str, float] = {}
        for rotulo, colecao in (("cifrada", col_cif), ("clara", col_clr)):
            for indice in range(total):
                doc = _documento(indice)
                inicio = time.perf_counter()
                colecao.insert_one(doc)
                decorrido = (time.perf_counter() - inicio) * 1000
                if indice == 0:
                    # A primeira paga a abertura da DEK contra o KMS: é rede, e
                    # ela não é custo por operação.
                    primeira[rotulo] = round(decorrido, 2)
                else:
                    medidas[rotulo].append(decorrido)

        col_cif.delete_many({"benchmark": True})
        col_clr.delete_many({"benchmark": True})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc

    base = _linha_de_base()
    cifrada_ms = _percentis(medidas["cifrada"])
    clara_ms = _percentis(medidas["clara"])
    return {
        "amostra": total,
        "linha_de_base_ms": base,
        "cifrada_ms": cifrada_ms,
        "clara_ms": clara_ms,
        "acima_da_base": {
            "cifrada": _acima_da_base(cifrada_ms, base),
            "clara": _acima_da_base(clara_ms, base),
        },
        "primeira_operacao_ms": primeira,
        "onde_esta_o_custo": (
            "local, não no cluster: a cifragem acontece na aplicação. Este número "
            "depende do hardware do apresentador."
        ),
        "tier": settings.cluster_tier or None,
        "nota_tier": _nota_tier(),
    }


@router.get("/leitura")
def leitura(repeticoes: int = Query(30, ge=5, le=500)):
    """Igualdade e faixa nas duas coleções, com aquecimento."""
    try:
        col_cif = cliente_cifrado()[settings.mongo_db][COLECAO_CIFRADA]
        col_clr = cliente_claro()[settings.mongo_db][COLECAO_CLARA]
        alvo = col_clr.find_one({}, {"cpf": 1})
        if alvo is None:
            raise HTTPException(status_code=503, detail="Rode seed_data.py antes de medir leitura.")
        cpf = alvo.get("cpf")

        cenarios = {
            "igualdade_cifrada": lambda: list(col_cif.find({"cpf": cpf}).limit(5)),
            "igualdade_clara": lambda: list(col_clr.find({"cpf": cpf}).limit(5)),
            "faixa_cifrada": lambda: list(col_cif.find({"salario": {"$gte": 8_000, "$lte": 15_000}}).limit(5)),
            "faixa_clara": lambda: list(col_clr.find({"salario": {"$gte": 8_000, "$lte": 15_000}}).limit(5)),
        }

        resultado = {}
        for nome, fn in cenarios.items():
            # Aquecimento igual para os dois lados: cache frio faz a coleção
            # cifrada parecer muito pior do que ela é.
            for _ in range(AQUECIMENTO):
                fn()
            amostras = []
            for _ in range(repeticoes):
                inicio = time.perf_counter()
                fn()
                amostras.append((time.perf_counter() - inicio) * 1000)
            resultado[nome] = _percentis(amostras)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc

    base = _linha_de_base()
    return {
        "aquecimento": AQUECIMENTO,
        "repeticoes": repeticoes,
        "linha_de_base_ms": base,
        "resultados": resultado,
        "acima_da_base": {nome: _acima_da_base(valores, base) for nome, valores in resultado.items()},
        "tier": settings.cluster_tier or None,
        "nota_tier": _nota_tier(),
        "nota": "Aquecido dos dois lados com o mesmo número de leituras antes de medir.",
    }
