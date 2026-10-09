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
determinístico — e é o determinismo que faz CSFLE determinístico (e as funções
"raw" `encrypt()` do pgcrypto, cujo IV padrão é zero) vazarem frequência para
quem tem o dump. As funções PGP do pgcrypto são randomizadas e o PostgreSQL
consegue filtrar com elas, mas decifrando no servidor, com a chave na sessão:
a diferença de QE é a fronteira de confiança, não a capacidade de filtrar.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query

from ._comum import erro_do_servidor, serializar
from encryption import (
    CAMPOS_CIFRADOS,
    COLECAO_CIFRADA,
    cliente_cifrado,
    cliente_claro,
    executar_capturando,
    key_vault_collection,
    nomes_dek,
    resumir_comando_enviado,
)
from settings import ler_arquivo_seeds, settings

router = APIRouter(prefix="/demo", tags=["demo"])

LIMITE_MAX = 10

# As duas buscas de `_executar` vão para clientes MongoClient distintos (cada
# um com seu próprio pool de conexões e, no caso do cifrado, seu próprio
# contexto de auto-encryption) — PyMongo é thread-safe para uso concorrente
# entre threads, então rodar as duas em paralelo é seguro e corta a latência
# pela metade. O pool é só para isso; 2 workers bastam por request.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="qe-demo-busca")


def _colecao(cliente):
    return cliente[settings.mongo_db][COLECAO_CIFRADA]


def _cronometrar(fn):
    inicio = time.perf_counter()
    return fn(), round((time.perf_counter() - inicio) * 1000, 1)


def _ids_do_par() -> list:
    """Os `_id` do par plantado, se o seed já rodou."""
    arquivo = ler_arquivo_seeds()
    if arquivo is None:
        return []
    try:
        seeds = json.loads(arquivo.read_text())
        return [ObjectId(bruto) for bruto in seeds.get("cpf_repetido", [])]
    except Exception:
        return []


def _executar(filtro: dict, limite: int) -> dict:
    """O mesmo filtro nos dois clientes, no mesmo instante.

    Os dois lados rodam mesmo quando o de baixo vai voltar vazio: o zero do
    cliente comum é a evidência, não uma falha a ser escondida.

    As duas buscas saem em paralelo (ThreadPoolExecutor) em vez de sequenciais:
    o driver é síncrono, mas os dois clientes são objetos MongoClient distintos
    e thread-safe, então esperar um terminar para começar o outro só dobra a
    latência por request sem necessidade nenhuma.
    """
    projecao = {"observacoes": 0}
    futuro_cifrado = _executor.submit(
        _cronometrar,
        lambda: executar_capturando(
            "find", COLECAO_CIFRADA,
            lambda: list(_colecao(cliente_cifrado()).find(filtro, projecao).limit(limite)),
        ),
    )
    futuro_claro = _executor.submit(
        _cronometrar, lambda: list(_colecao(cliente_claro()).find(filtro, projecao).limit(limite))
    )

    try:
        (cifrados, enviado), ms_app = futuro_cifrado.result()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc

    try:
        claros, ms_dba = futuro_claro.result()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc

    # O zero do cliente comum prova que o servidor não casa o filtro sem a chave;
    # não prova que o documento está escondido. O DBA continua lendo o disco: os
    # mesmos documentos que a aplicação achou, por `_id`, vêm como Binary(6).
    # A tela mostra as duas coisas, separadas e rotuladas.
    ids_app = [doc["_id"] for doc in cifrados]
    if claros or not ids_app:
        lidos, origem = claros, "filtro"
    else:
        try:
            lidos = list(_colecao(cliente_claro()).find({"_id": {"$in": ids_app}}, projecao))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc
        origem = "por_id"

    return {
        "query_details": {
            "operation": "find",
            "namespace": f"{settings.mongo_db}.{COLECAO_CIFRADA}",
            "command": {
                "find": COLECAO_CIFRADA,
                "filter": serializar(filtro),
                "projection": projecao,
                "limit": limite,
            },
            "clients": ["MongoClient + AutoEncryptionOpts", "MongoClient comum"],
            # O comando como o servidor o recebeu, capturado por CommandListener
            # depois da auto-encryption. É a prova de que o valor buscado não
            # chega em claro: o campo cifrado aparece como Binary(subtype 6).
            "sent_to_server": resumir_comando_enviado(enviado),
            "explain": {
                "mode": "not_auto_executed",
                "reason": "o painel não repete a consulta com executionStats; use o comando exibido em ambiente controlado",
            },
        },
        "aplicacao": {
            "encontrados": len(cifrados),
            "ms": ms_app,
            "documentos": [serializar(doc) for doc in cifrados],
        },
        "dba": {
            # Quantos o MESMO filtro achou sem a chave.
            "encontrados": len(claros),
            "ms": ms_dba,
            # De onde vêm `documentos`: "filtro" (o próprio filtro achou) ou
            # "por_id" (o filtro achou zero; leitura direta dos mesmos _id).
            "origem": origem,
            "documentos": [serializar(doc) for doc in lidos],
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
    if cpf is not None:
        digitos = "".join(ch for ch in cpf if ch in "0123456789")
        # Só pontuação de CPF é tolerada. Sem esta checagem, "abc.def.ghi-jk"
        # virava uma busca cifrada por "" e voltava zero — que na tela parece
        # a prova da tese, e é só entrada inválida.
        if len(digitos) != 11 or any(ch not in "0123456789.- " for ch in cpf):
            raise HTTPException(status_code=422, detail="CPF deve ter 11 dígitos (pontuação opcional).")
        filtro["cpf"] = digitos
        tipo = "igualdade sobre campo cifrado"
    if salario_min is not None and salario_max is not None and salario_min > salario_max:
        raise HTTPException(status_code=422, detail="salario_min não pode ser maior que salario_max.")
    if salario_min is not None or salario_max is not None:
        faixa: dict = {}
        if salario_min is not None:
            faixa["$gte"] = salario_min
        if salario_max is not None:
            faixa["$lte"] = salario_max
        filtro["salario"] = faixa
        tipo = "faixa sobre campo cifrado" if tipo is None else "igualdade + faixa sobre campo cifrado"
    if uf is not None:
        if len(uf) != 2 or not uf.isascii() or not uf.isalpha():
            raise HTTPException(status_code=422, detail="UF deve ter 2 letras, ex.: SP.")
        filtro["uf"] = uf.upper()
        tipo = tipo or "campo em claro (controle)"
    if not filtro:
        raise HTTPException(status_code=422, detail="Informe cpf, faixa de salário ou uf.")

    resultado = _executar(filtro, limite)
    cifrado = "cpf" in filtro or "salario" in filtro
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


BUSCAS_STRING = {
    "prefixo": {"campo": "email_prefix", "operador": "$encStrStartsWith",
                "argumento": "prefix", "valor": "titular0", "label": "E-mail começa com titular0"},
    "sufixo": {"campo": "email_suffix", "operador": "$encStrEndsWith",
               "argumento": "suffix", "valor": "@exemplo.invalid", "label": "E-mail termina com @exemplo.invalid"},
    "trecho": {"campo": "email_substring", "operador": "$encStrContains",
              "argumento": "substring", "valor": "ular0@", "label": "E-mail contém ular0@"},
}


@router.get("/buscas-string")
def buscas_string():
    """Opções fechadas para demonstrar buscas parciais sobre e-mail cifrado."""
    return {"opcoes": [{"id": chave, "label": item["label"]} for chave, item in BUSCAS_STRING.items()]}


@router.get("/buscar-string")
def buscar_string(tipo: str = Query(..., pattern=r"^(prefixo|sufixo|trecho)$")):
    """Executa um dos exemplos selecionáveis; a API não aceita texto livre."""
    try:
        versao = cliente_claro().server_info().get("versionArray", [])
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Não foi possível confirmar a versão do cluster.") from exc
    if tuple(versao[:2]) < (9, 0):
        raise HTTPException(status_code=409, detail="Buscas QE por prefixo, sufixo e trecho requerem MongoDB 9.0+.")
    item = BUSCAS_STRING[tipo]
    filtro = {"$expr": {item["operador"]: {
        "input": f"${item['campo']}", item["argumento"]: item["valor"]
    }}}
    try:
        encontrados, enviado = executar_capturando(
            "find", COLECAO_CIFRADA,
            lambda: list(_colecao(cliente_cifrado()).find(filtro, {"_id": 1, "nome": 1, item["campo"]: 1})
                         .limit(LIMITE_MAX)),
        )
        ids = [doc["_id"] for doc in encontrados]
        # A visão sem chave lê os mesmos documentos por _id e exibe o binário
        # cifrado: evita fingir que o cliente comum consegue montar a busca QE.
        claros = list(_colecao(cliente_claro()).find({"_id": {"$in": ids}}, {"_id": 1, "nome": 1, item["campo"]: 1})) if ids else []
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc
    return {
        "tipo": item["label"], "campo": item["campo"],
        "operador": item["operador"], "modo": tipo, "valor": item["valor"],
        "limite": LIMITE_MAX,
        "filtro": serializar(filtro),
        "enviado_ao_servidor": resumir_comando_enviado(enviado),
        "aplicacao": {"encontrados": len(encontrados), "documentos": [serializar(d) for d in encontrados]},
        "dba": {"encontrados": len(claros), "documentos": [serializar(d) for d in claros]},
        "leitura": (
            f"O servidor casou \"{item['valor']}\" contra o campo {item['campo']} sem decifrá-lo; "
            "a aplicação decifra o resultado localmente. O DBA não consegue montar essa busca "
            "e lê os mesmos registros, por _id, como BinData cifrado."
        ),
    }


@router.get("/exemplos")
def exemplos(quantos: int = Query(4, ge=1, le=8)):
    """Alguns titulares da base para a tela oferecer como opções prontas.

    Sai pelo cliente CIFRADO de propósito: é a aplicação lendo o próprio dado,
    exatamente como faria em produção. A tela não exige que a pessoa decore ou
    digite um CPF.
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

    É o argumento anti-CSFLE, e ele é visual. CSFLE determinístico permite
    igualdade justamente por cifrar o mesmo valor no mesmo ciphertext — e é
    isso que entrega frequência a quem tem o dump. Queryable
    Encryption é randomizado e continua consultável. Achar esse par no palco por
    sorte não é opção: ele é plantado pelo seed.
    """
    if ler_arquivo_seeds() is None:
        raise HTTPException(status_code=503, detail="Rode seed_data.py — metadados do seed ausentes.")
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
        cofre = key_vault_collection()
        total = cofre.estimated_document_count()
        encontrados = list(cofre.find(
            {"keyAltNames": {"$in": nomes_dek()}}, {"keyAltNames": 1}
        ))
        nomes_presentes = {nome for doc in encontrados for nome in doc.get("keyAltNames", [])}
        faltando = [nome for nome in nomes_dek() if nome not in nomes_presentes]
    except Exception as exc:
        # erro_do_servidor() carrega code/codeName do MongoDB quando existem —
        # diferencia "cluster fora do ar" de "sem permissão" no selo, em vez
        # de só o nome genérico da exceção.
        detalhe = erro_do_servidor(exc)
        codigo = f" (code={detalhe['codigo']})" if "codigo" in detalhe else ""
        return {
            "cofre": {
                "ok": False,
                "message": f"cofre inacessível: {detalhe['tipo']}{codigo}: {detalhe['mensagem']}",
            }
        }
    return {
        "cofre": {
            "ok": total > 0 and not faltando,
            "message": (f"{total - len(faltando)} DEK(s) da demo" if not faltando
                        else f"DEK(s) ausente(s): {', '.join(faltando)} — rode scripts/criar-cofre.py"),
        },
        "kms": {
            "ok": settings.kms_configurado,
            "message": f"provedor {settings.kms_provider}"
            + ("" if settings.kms_configurado else " sem credencial/arquivo"),
        },
    }
