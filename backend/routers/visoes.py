"""Módulo 02 — Duas visões.

O centro da PoV. A mesma query, no mesmo instante, por dois clientes: a
aplicação (com auto-encryption) e o DBA (cliente comum). Mesmos _id dos dois
lados, campos sensíveis legíveis de um lado e Binary(subtype 6) do outro.
"""

from __future__ import annotations

import json
from pathlib import Path

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query

from ._comum import erro_do_servidor, serializar
from encryption import (
    CAMPOS_CIFRADOS,
    COLECAO_CIFRADA,
    cliente_cifrado,
    cliente_claro,
)
from settings import settings

router = APIRouter(prefix="/visoes", tags=["02 · duas visões"])

SEEDS = Path(__file__).resolve().parent.parent / "data" / "demo_seeds.json"
LIMITE_MAX = 20


def _colecao(cliente):
    return cliente[settings.mongo_db][COLECAO_CIFRADA]


def _filtro(uf: str | None, tenant: str | None) -> dict:
    """Só campos em CLARO são aceitos como filtro aqui.

    Filtrar por campo cifrado é o módulo 03. Aceitar um campo cifrado neste
    endpoint faria o painel do DBA voltar vazio, e o contraste — que é a tela
    inteira — desapareceria sem explicação.
    """
    filtro: dict = {}
    if uf:
        filtro["uf"] = uf.upper()[:2]
    if tenant:
        filtro["tenant_id"] = tenant
    return filtro


@router.get("/comparar")
def comparar(
    uf: str | None = Query(None, max_length=2),
    tenant: str | None = Query(None, max_length=64),
    limite: int = Query(5, ge=1, le=LIMITE_MAX),
):
    filtro = _filtro(uf, tenant)
    projecao = {"observacoes": 0}
    try:
        docs_claros = list(_colecao(cliente_claro()).find(filtro, projecao).sort("_id", 1).limit(limite))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc

    ids = [doc["_id"] for doc in docs_claros]
    try:
        crus = _colecao(cliente_cifrado()).find({"_id": {"$in": ids}}, projecao)
        por_id = {doc["_id"]: doc for doc in crus}
        docs_cifrados = [por_id[_id] for _id in ids if _id in por_id]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc

    return {
        "filtro": filtro,
        "campos_cifrados": list(CAMPOS_CIFRADOS),
        # A ordem é a mesma dos dois lados de propósito: a tela alinha linha a
        # linha, e dois painéis rolando independentes fazem o cliente duvidar
        # que seja o mesmo documento.
        "aplicacao": [serializar(doc) for doc in docs_cifrados],
        "dba": [serializar(doc) for doc in docs_claros],
        "mesmos_ids": [str(_id) for _id in ids],
        "legenda": "mesmo _id · mesma query · mesmo instante",
    }


@router.get("/cpf-repetido")
def cpf_repetido():
    """O par plantado: dois titulares com o MESMO CPF e ciphertexts diferentes.

    É o argumento anti-CSFLE, e ele é visual. CSFLE usa ciphertext determinístico
    para permitir igualdade, e por isso vaza frequência — com o dump em mãos dá
    para ver qual valor se repete. Queryable Encryption é randomizado e continua
    consultável. Achar esse par no palco por sorte não é opção: ele é plantado
    pelo seed e o _id fica em backend/data/demo_seeds.json.
    """
    if not SEEDS.exists():
        raise HTTPException(status_code=503, detail="Rode seed_data.py — demo_seeds.json ausente.")
    seeds = json.loads(SEEDS.read_text())
    ids = [ObjectId(bruto) for bruto in seeds.get("cpf_repetido", [])]
    if len(ids) < 2:
        raise HTTPException(status_code=503, detail="Seed sem par de CPF repetido; rode seed_data.py --drop.")

    try:
        claros = list(_colecao(cliente_claro()).find({"_id": {"$in": ids}}))
        cifrados = list(_colecao(cliente_cifrado()).find({"_id": {"$in": ids}}))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc

    hexes = {str(doc["_id"]): serializar(doc.get("cpf")) for doc in claros}
    distintos = len({item["hex"] for item in hexes.values() if isinstance(item, dict)}) > 1
    return {
        "aplicacao": [serializar(doc) for doc in cifrados],
        "dba": [serializar(doc) for doc in claros],
        "ciphertexts_distintos": distintos,
        "afirmacao": "mesmo CPF, ciphertexts diferentes — é isso que CSFLE não faz",
    }
