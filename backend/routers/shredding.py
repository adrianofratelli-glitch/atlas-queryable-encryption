"""Módulo 05 — Crypto shredding.

Apagar a DEK torna todo campo cifrado por ela matematicamente irrecuperável,
inclusive nos backups já feitos e nas réplicas já propagadas. É o direito ao
esquecimento sem `delete` — e, para serviço financeiro, é o que resolve o
conflito clássico entre a retenção obrigatória do Bacen e a LGPD art. 18: o
registro continua existindo e contabilizável, o conteúdo pessoal não é mais
legível por ninguém.

**A granularidade não é livre.** Com auto-encryption a chave é ligada por CAMPO
DE UMA COLEÇÃO, nunca por documento — e o Queryable Encryption exige uma DEK
distinta por campo (`Duplicate key ids are not allowed`, code 6338401). Disso
saem exatamente dois escopos de shredding, e são os dois que este módulo
demonstra:

- **por campo** — de graça, porque cada campo já tem a sua DEK. Apagar a chave
  do `cpf` deixa o resto do documento legível.
- **por coorte** — separando coleções por chave. `clientes_tenant_beta` tem o
  seu próprio conjunto de DEKs; apagá-las não toca em `clientes`.

Não existe "uma DEK por titular" dentro de uma coleção. Prometer isso numa
reunião é o tipo de erro que só aparece na prova de conceito do cliente.
"""

from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, Body, HTTPException

from encryption import (
    CAMPOS_CIFRADOS,
    COLECAO_CIFRADA,
    COLECAO_CIFRADA_BETA,
    COLECOES_CIFRADAS,
    cliente_cifrado,
    cliente_claro,
    key_vault_collection,
    nome_dek,
    reiniciar_cliente_cifrado,
    resumo_dek,
)
from settings import settings

from ._comum import erro_do_servidor, serializar

router = APIRouter(prefix="/shredding", tags=["05 · crypto shredding"])


# A demo opera na coleção da COORTE por padrão, nunca em `clientes`. Apagar uma
# DEK de `clientes` derruba os módulos 02, 03, 04 e 06 até um reseed completo —
# e descobrir isso no palco, entre dois módulos, é o pior momento possível.
def _colecao(cliente, nome: str = COLECAO_CIFRADA_BETA):
    return cliente[settings.mongo_db][nome]


def _oid(bruto: str) -> ObjectId:
    try:
        return ObjectId(bruto)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="_id inválido.") from exc


def _validar(colecao: str, campo: str | None = None) -> None:
    if colecao not in COLECOES_CIFRADAS:
        raise HTTPException(status_code=404, detail=f"Coleção desconhecida: {colecao}")
    if campo is not None and campo not in CAMPOS_CIFRADOS:
        raise HTTPException(status_code=404, detail=f"Campo não cifrado: {campo}")


@router.get("/escopos")
def escopos():
    """Os dois escopos que o produto realmente entrega, com o custo de cada um."""
    cofre = key_vault_collection()
    vivas = {
        nome
        for documento in cofre.find({}, {"keyAltNames": 1})
        for nome in documento.get("keyAltNames", [])
    }
    return {
        "escopos": [
            {
                "chave": "campo",
                "titulo": "Por campo",
                "como": "cada campo cifrado já tem a sua própria DEK — é obrigatório no QE",
                "esquecimento": "apaga um atributo e mantém o resto do documento legível",
                "custo": "zero: a granularidade vem de graça com o modelo",
            },
            {
                "chave": "coorte",
                "titulo": "Por coorte (inquilino)",
                "como": "uma coleção por escopo de chave, com o seu próprio conjunto de DEKs",
                "esquecimento": "offboarding de cliente corporativo em um comando",
                "custo": "uma coleção por coorte; é o desenho que a maioria adota",
            },
            {
                "chave": "titular",
                "titulo": "Por titular",
                "como": "NÃO existe com auto-encryption: a chave é por campo da coleção, "
                        "nunca por documento. Exigiria uma coleção por pessoa.",
                "esquecimento": "inatingível nesta modelagem",
                "custo": "impraticável — não prometa isso em reunião",
            },
        ],
        "chaves_vivas": {
            colecao: [campo for campo in CAMPOS_CIFRADOS if nome_dek(colecao, campo) in vivas]
            for colecao in COLECOES_CIFRADAS
        },
    }


@router.get("/titular/{doc_id}")
def ler_titular(doc_id: str, colecao: str = COLECAO_CIFRADA_BETA):
    """Passo 1 da linha do tempo: o documento ainda legível."""
    _validar(colecao)
    oid = _oid(doc_id)
    cru = _colecao(cliente_claro(), colecao).find_one({"_id": oid})
    if cru is None:
        raise HTTPException(status_code=404, detail="Titular não encontrado.")
    try:
        legivel = _colecao(cliente_cifrado(), colecao).find_one({"_id": oid})
    except Exception as exc:
        # Já sem DEK: é um estado válido da demo, não um erro da API.
        return {"legivel": False, "erro": erro_do_servidor(exc), "dba": serializar(cru)}
    return {"legivel": True, "aplicacao": serializar(legivel), "dba": serializar(cru)}


@router.post("/executar")
def executar(
    colecao: str = Body(..., embed=True),
    campos: list[str] = Body(..., embed=True),
    confirmacao: str = Body(..., embed=True),
):
    """Passos 2 e 3: DELETE das DEKs e limpeza do cache.

    O passo do cache é a armadilha número um deste módulo. O driver mantém a DEK
    decifrada em memória (padrão de 60 s). Sem recriar o cliente, o documento
    continua abrindo depois do delete e a demo parece falhar — quando é um cache
    se comportando corretamente. Por isso ele é um passo VISÍVEL da linha do
    tempo, e não um detalhe de implementação escondido aqui dentro.
    """
    _validar(colecao)
    for campo in campos:
        _validar(colecao, campo)
    if not campos:
        raise HTTPException(status_code=422, detail="Escolha ao menos um campo.")
    if confirmacao != colecao:
        raise HTTPException(
            status_code=428,
            detail="Confirme digitando o nome exato da coleção. Esta operação é irreversível.",
        )

    cofre = key_vault_collection()
    apagadas = []
    for campo in campos:
        documento = cofre.find_one({"keyAltNames": nome_dek(colecao, campo)})
        if documento is None:
            continue
        cofre.delete_one({"_id": documento["_id"]})
        apagadas.append({"campo": campo, "dek": resumo_dek(documento)})

    reiniciar_cliente_cifrado()

    return {
        "linha_do_tempo": [
            {"passo": 1, "acao": "documento legível", "concluido": True},
            {"passo": 2, "acao": f"DELETE de {len(apagadas)} DEK(s) de {colecao}",
             "concluido": bool(apagadas)},
            {"passo": 3, "acao": "cache de DEK limpo (cliente recriado)", "concluido": True},
            {"passo": 4, "acao": "reler o documento", "concluido": False},
        ],
        "deks_apagadas": apagadas,
        "alcance": (
            "O efeito alcança réplicas e backups já feitos: sem a DEK, o "
            "ciphertext não é decifrável por ninguém, em lugar nenhum."
        ),
        "reversivel": False,
    }


@router.get("/verificar/{doc_id}")
def verificar(doc_id: str, colecao: str = COLECAO_CIFRADA_BETA, campo: str = "cpf"):
    """Passo 4: a leitura que agora falha — e a que continua funcionando.

    Medido no cluster depois de apagar a DEK do `cpf`:

    - `find_one({...})` falha inteiro: "not all keys requested were satisfied";
    - `find_one({...}, {"cpf": 0})` devolve nome, salário e e-mail normalmente;
    - a consulta por faixa em `salario` continua respondendo;
    - a consulta de igualdade por `cpf` falha.

    Ou seja: o shredding por campo é real, mas ele **impõe uma mudança na
    aplicação**. Enquanto alguém projetar o campo apagado, toda leitura daquele
    documento quebra. Quem vende isso sem dizer entrega um incidente junto.
    """
    _validar(colecao, campo)
    oid = _oid(doc_id)
    servidor = _colecao(cliente_claro(), colecao).find_one({"_id": oid})
    if servidor is None:
        raise HTTPException(status_code=404, detail="Titular não encontrado.")

    resposta = {"dba": serializar(servidor), "campo_alvo": campo}

    try:
        completo = _colecao(cliente_cifrado(), colecao).find_one({"_id": oid})
        resposta["leitura_completa"] = {"ok": True, "documento": serializar(completo)}
    except Exception as exc:
        resposta["leitura_completa"] = {"ok": False, "erro": erro_do_servidor(exc)}

    try:
        parcial = _colecao(cliente_cifrado(), colecao).find_one({"_id": oid}, {campo: 0})
        resposta["leitura_sem_o_campo"] = {"ok": True, "documento": serializar(parcial)}
    except Exception as exc:
        resposta["leitura_sem_o_campo"] = {"ok": False, "erro": erro_do_servidor(exc)}

    resposta["legivel"] = resposta["leitura_completa"]["ok"]
    resposta["nota"] = (
        f"O documento continua no banco, íntegro e contabilizável, e tudo que não "
        f"depende da DEK de `{campo}` continua legível. Mas qualquer leitura que "
        f"projete `{campo}` falha: o shredding por campo exige que a aplicação pare "
        f"de pedir aquele campo."
        if not resposta["leitura_completa"]["ok"]
        else f"Ainda legível — a DEK de `{campo}` não foi apagada, ou o cache não foi limpo."
    )
    return resposta


@router.get("/contraprova")
def contraprova():
    """A coorte vizinha continua intacta.

    Um shredding que derruba o inquilino errado não é privacidade, é incidente.
    Esta é a única evidência que separa "apaguei a chave certa" de "apaguei
    alguma chave", e ela precisa estar na mesma tela.
    """
    saida = {}
    for colecao in COLECOES_CIFRADAS:
        try:
            documento = _colecao(cliente_cifrado(), colecao).find_one({})
            saida[colecao] = {
                "legivel": True,
                "amostra": serializar({campo: documento.get(campo) for campo in ("nome", "cpf", "salario")})
                if documento else None,
            }
        except Exception as exc:
            saida[colecao] = {"legivel": False, "erro": erro_do_servidor(exc)}
    return {
        "colecoes": saida,
        "nota": (
            f"`{COLECAO_CIFRADA}` e `{COLECAO_CIFRADA_BETA}` têm conjuntos de DEK "
            "separados. Apagar as de uma não pode afetar a outra."
        ),
    }
