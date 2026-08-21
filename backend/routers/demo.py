"""A demo inteira: uma busca, dois clientes, dois resultados.

Esta PoV tem um argumento só, e ele se prova numa tela. O mesmo filtro sai ao
mesmo tempo por dois clientes contra o mesmo cluster: a aplicação, com
auto-encryption, acha o documento e lê o campo; o cliente comum — o DBA, o
operador do Atlas, quem levar o backup — recebe `Binary(subtype 6)` e, quando o
filtro é por campo cifrado, não acha nada.

O filtro por campo cifrado é o ponto que separa Queryable Encryption de tudo que
veio antes. O driver cifra o valor da busca com a mesma DEK e manda o
ciphertext; o servidor casa contra estruturas de metadados que ele mantém sem
conseguir interpretar. É por isso que a igualdade funciona sem ciphertext
determinístico — e é o determinismo que faz CSFLE e `pgcrypto` vazarem
frequência para quem tem o dump.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query

from ._comum import erro_do_servidor, serializar
from encryption import (
    CAMPOS_CIFRADOS,
    COLECAO_CIFRADA,
    cliente_cifrado,
    cliente_claro,
    key_vault_collection,
)
from settings import settings

router = APIRouter(prefix="/demo", tags=["demo"])

SEEDS = Path(__file__).resolve().parent.parent / "data" / "demo_seeds.json"
LIMITE_MAX = 10


def _colecao(cliente):
    return cliente[settings.mongo_db][COLECAO_CIFRADA]


def _cronometrar(fn):
    inicio = time.perf_counter()
    return fn(), round((time.perf_counter() - inicio) * 1000, 1)


def _ids_do_par() -> list:
    """Os `_id` do par plantado, se o seed já rodou."""
    if not SEEDS.exists():
        return []
    try:
        seeds = json.loads(SEEDS.read_text())
        return [ObjectId(bruto) for bruto in seeds.get("cpf_repetido", [])]
    except Exception:
        return []


def _executar(filtro: dict, limite: int) -> dict:
    """O mesmo filtro nos dois clientes, no mesmo instante.

    Os dois lados rodam mesmo quando o de baixo vai voltar vazio: o zero do
    cliente comum é a evidência, não uma falha a ser escondida.
    """
    projecao = {"observacoes": 0}
    try:
        cifrados, ms_app = _cronometrar(
            lambda: list(_colecao(cliente_cifrado()).find(filtro, projecao).limit(limite))
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc

    try:
        claros, ms_dba = _cronometrar(
            lambda: list(_colecao(cliente_claro()).find(filtro, projecao).limit(limite))
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc

    return {
        "aplicacao": {
            "encontrados": len(cifrados),
            "ms": ms_app,
            "documentos": [serializar(doc) for doc in cifrados],
        },
        "dba": {
            "encontrados": len(claros),
            "ms": ms_dba,
            "documentos": [serializar(doc) for doc in claros],
        },
    }


@router.get("/buscar")
def buscar(
    cpf: str | None = Query(None, min_length=11, max_length=14),
    salario_min: int | None = Query(None, ge=0, le=1_000_000),
    salario_max: int | None = Query(None, ge=0, le=1_000_000),
    uf: str | None = Query(None, max_length=2),
    limite: int = Query(5, ge=1, le=LIMITE_MAX),
):
    """Igualdade sobre `cpf`, faixa sobre `salario`, ou `uf` como contraste.

    `uf` está aqui de propósito: é um campo em claro, e com ele os dois painéis
    devolvem a mesma quantidade de documentos. É o controle do experimento — sem
    ele, alguém pode achar que o cliente comum simplesmente não enxerga a
    coleção.
    """
    filtro: dict = {}
    tipo = None
    if cpf:
        filtro["cpf"] = "".join(ch for ch in cpf if ch.isdigit())
        tipo = "igualdade sobre campo cifrado"
    if salario_min is not None or salario_max is not None:
        faixa: dict = {}
        if salario_min is not None:
            faixa["$gte"] = salario_min
        if salario_max is not None:
            faixa["$lte"] = salario_max
        filtro["salario"] = faixa
        tipo = "faixa sobre campo cifrado" if tipo is None else "igualdade + faixa sobre campo cifrado"
    if uf:
        filtro["uf"] = uf.upper()[:2]
        tipo = tipo or "campo em claro (controle)"
    if not filtro:
        raise HTTPException(status_code=422, detail="Informe cpf, faixa de salário ou uf.")

    resultado = _executar(filtro, limite)
    cifrado = bool(cpf) or filtro.get("salario") is not None
    return {
        "filtro": serializar(filtro),
        "tipo": tipo,
        "campo_cifrado": cifrado,
        "campos_cifrados": list(CAMPOS_CIFRADOS),
        **resultado,
        "leitura": (
            "O cliente comum devolve zero: o valor em claro não casa com ciphertext randomizado."
            if cifrado
            else "Campo em claro: os dois lados acham os mesmos documentos, e só os campos sensíveis divergem."
        ),
    }


@router.get("/exemplos")
def exemplos(quantos: int = Query(4, ge=1, le=8)):
    """Alguns titulares reais da base, para a tela oferecer em vez de exigir
    que alguém decore um CPF.

    Sai pelo cliente CIFRADO de propósito: é a aplicação lendo o próprio dado,
    exatamente como faria em produção. Digitar um CPF errado no palco devolve
    zero pelo motivo errado — e "zero" é justamente a evidência que a demo usa
    para outra coisa.
    """
    # O par plantado fica de fora: o CPF dele aparece em dois titulares, e uma
    # busca por igualdade voltando com dois documentos antes de a tela explicar
    # o par parece defeito. Ele tem a sua própria seção.
    filtro = {"_id": {"$nin": _ids_do_par()}} if _ids_do_par() else {}

    # Uma folga acima do pedido cobre qualquer duplicata que sobre.
    try:
        docs = list(
            _colecao(cliente_cifrado())
            .find(filtro, {"_id": 1, "nome": 1, "cpf": 1, "salario": 1, "uf": 1})
            # `find` sem `sort` não promete ordem nenhuma: duas chamadas podem
            # devolver conjuntos diferentes, e a demo deixa de ser reprodutível.
            .sort("_id", 1)
            .limit(quantos + 3)
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc

    # O par plantado compartilha o CPF. Oferecer os dois como se fossem opções
    # distintas confunde: a mesma busca traria dois titulares, e a tela ainda
    # não explicou por quê.
    vistos: set[str] = set()
    unicos = []
    for doc in docs:
        cpf = doc.get("cpf")
        if not isinstance(cpf, str) or cpf in vistos:
            continue
        vistos.add(cpf)
        unicos.append({
            "cpf": cpf,
            "nome": doc.get("nome"),
            "salario": doc.get("salario"),
            "uf": doc.get("uf"),
        })
        if len(unicos) == quantos:
            break
    return {"titulares": unicos}


@router.get("/par-repetido")
def par_repetido():
    """Dois titulares com o MESMO CPF e ciphertexts diferentes.

    É o argumento anti-CSFLE, e ele é visual. CSFLE e `pgcrypto` determinístico
    permitem igualdade justamente por cifrarem o mesmo valor no mesmo
    ciphertext — e é isso que entrega frequência a quem tem o dump. Queryable
    Encryption é randomizado e continua consultável. Achar esse par no palco por
    sorte não é opção: ele é plantado pelo seed.
    """
    if not SEEDS.exists():
        raise HTTPException(status_code=503, detail="Rode seed_data.py — demo_seeds.json ausente.")
    ids = _ids_do_par()
    if len(ids) < 2:
        raise HTTPException(status_code=503, detail="Seed sem par de CPF repetido; rode seed_data.py --drop.")

    try:
        claros = list(_colecao(cliente_claro()).find({"_id": {"$in": ids}}, {"observacoes": 0}))
        cifrados = list(_colecao(cliente_cifrado()).find({"_id": {"$in": ids}}, {"observacoes": 0}))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc

    # Sem os dois documentos não há o que comparar: um conjunto de zero ou um
    # hex faz "distintos" virar falso, e a tela passa a afirmar "ciphertexts
    # iguais" — o oposto da verdade. Falhar alto aqui é obrigatório.
    if len(claros) < 2:
        raise HTTPException(
            status_code=503,
            detail=(
                f"O par plantado não está no banco ({len(claros)} de 2 documentos). "
                "demo_seeds.json ficou de um seed anterior — rode seed_data.py --drop."
            ),
        )

    amostras = [serializar(doc.get("cpf")) for doc in claros]
    distintos = len({a["hex"] for a in amostras if isinstance(a, dict)}) > 1
    return {
        "aplicacao": [serializar(doc) for doc in cifrados],
        "dba": [serializar(doc) for doc in claros],
        "ciphertexts_distintos": distintos,
        "leitura": (
            "mesmo CPF, ciphertexts diferentes — é isso que CSFLE não faz"
            if distintos
            else "ciphertexts iguais: o par não veio deste seed; rode seed_data.py --drop"
        ),
    }


def preflight_checks() -> dict:
    """Cofre e KMS, para o selo de pré-voo.

    Um cofre vazio só se manifesta como erro de criptografia na primeira busca,
    e ali ninguém lembra que faltou rodar `scripts/criar-cofre.py`.
    """
    try:
        total = key_vault_collection().estimated_document_count()
    except Exception as exc:
        return {"cofre": {"ok": False, "message": f"cofre inacessível: {type(exc).__name__}"}}
    return {
        "cofre": {
            "ok": total > 0,
            "message": f"{total} DEK(s)" if total else "vazio — rode scripts/criar-cofre.py",
        },
        "kms": {
            "ok": settings.kms_configurado,
            "message": f"provedor {settings.kms_provider}"
            + ("" if settings.kms_configurado else " sem credencial/arquivo"),
        },
    }
