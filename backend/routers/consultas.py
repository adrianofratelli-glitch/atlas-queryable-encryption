"""Módulo 03 — Consulta sobre cifrado.

Igualdade e faixa, as duas pelo cliente cifrado, com a contraprova obrigatória:
o mesmo filtro pelo cliente claro devolvendo zero documentos. Esse zero é o
resultado mais importante do módulo, e a tela precisa rotulá-lo como evidência
esperada e não como falha.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query

from ._comum import erro_do_servidor, serializar
from encryption import COLECAO_CIFRADA, cliente_cifrado, cliente_claro
from settings import settings

router = APIRouter(prefix="/consultas", tags=["03 · consulta sobre cifrado"])


def _colecao(cliente):
    return cliente[settings.mongo_db][COLECAO_CIFRADA]


def _cronometrar(fn):
    inicio = time.perf_counter()
    resultado = fn()
    return resultado, round((time.perf_counter() - inicio) * 1000, 1)


@router.get("/igualdade")
def igualdade(cpf: str = Query(..., min_length=11, max_length=14), limite: int = Query(5, ge=1, le=20)):
    """O driver cifra o valor da busca com a mesma DEK e envia o ciphertext.

    O servidor casa contra os metadados cifrados sem nunca ver o CPF.
    """
    alvo = "".join(ch for ch in cpf if ch.isdigit())
    try:
        docs, ms = _cronometrar(
            lambda: list(_colecao(cliente_cifrado()).find({"cpf": alvo}).limit(limite))
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc

    # Contraprova: o mesmo filtro pelo cliente claro. O valor em claro não casa
    # com nada, porque na coleção só existe ciphertext randomizado.
    claros, ms_claro = _cronometrar(
        lambda: list(_colecao(cliente_claro()).find({"cpf": alvo}).limit(limite))
    )

    return {
        "filtro": {"cpf": alvo},
        "aplicacao": {"encontrados": len(docs), "ms": ms, "documentos": [serializar(d) for d in docs]},
        "dba": {
            "encontrados": len(claros),
            "ms": ms_claro,
            "documentos": [serializar(d) for d in claros],
            "esperado": 0,
            "nota": "zero é a evidência: o valor em claro não casa com ciphertext randomizado",
        },
    }


@router.get("/faixa")
def faixa(
    campo: str = Query("salario", pattern="^(salario|score_credito)$"),
    minimo: int = Query(..., ge=0, le=1_000_000),
    maximo: int = Query(..., ge=0, le=1_000_000),
    limite: int = Query(5, ge=1, le=20),
):
    """O que ninguém espera que funcione. Faixa sobre ciphertext, no servidor."""
    if minimo >= maximo:
        raise HTTPException(status_code=422, detail="`minimo` precisa ser menor que `maximo`.")
    filtro = {campo: {"$gte": minimo, "$lte": maximo}}
    try:
        docs, ms = _cronometrar(lambda: list(_colecao(cliente_cifrado()).find(filtro).limit(limite)))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc

    claros, ms_claro = _cronometrar(lambda: list(_colecao(cliente_claro()).find(filtro).limit(limite)))
    return {
        "filtro": filtro,
        "aplicacao": {"encontrados": len(docs), "ms": ms, "documentos": [serializar(d) for d in docs]},
        "dba": {"encontrados": len(claros), "ms": ms_claro, "esperado": 0},
        "nota": (
            "Range é GA a partir do MongoDB 8.0. A faixa declarada em "
            "`encryptedFields` (min/max) é imutável: um valor fora dela é "
            "rejeitado na escrita."
        ),
    }


@router.get("/explain")
def explain(campo: str = Query("salario", pattern="^(salario|score_credito|cpf)$")):
    """O explain existe para mostrar QUE o servidor executou sem plaintext.

    Não serve para otimizar: não há plano legível dentro das enxcol_.*, e não há
    o que ajustar nelas.
    """
    filtro = {campo: {"$gte": 8_000, "$lte": 15_000}} if campo != "cpf" else {"cpf": "00000000000"}
    try:
        plano = _colecao(cliente_claro()).find(filtro).explain()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc
    vencedor = (plano.get("queryPlanner") or {}).get("winningPlan", {})
    return {
        "filtro": serializar(filtro),
        "winningPlan": serializar(vencedor),
        "contention_configurado": settings.contention_factor,
        "nota_contention": (
            "contention é o número de partições de metadados por campo: mais "
            "partições aliviam contenção de escrita e obrigam a leitura a varrer "
            "mais partições. Imutável depois de criada a coleção."
        ),
    }
