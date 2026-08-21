"""Módulo 04 — Fronteiras.

O módulo que compra credibilidade para todo o resto. Cada limite roda de verdade
e devolve o erro CRU do servidor. Nada aqui é texto escrito à mão: o valor da
tela está exatamente em a mensagem vir do MongoDB.

Uma demo de criptografia que só mostra o que funciona é a demo que perde o
segundo encontro, porque o arquiteto do cliente vai testar `sort` em campo
cifrado na segunda-feira e concluir que a gente escondeu alguma coisa.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ._comum import erro_do_servidor, serializar
from encryption import COLECAO_CIFRADA, cliente_cifrado
from settings import settings

router = APIRouter(prefix="/fronteiras", tags=["04 · fronteiras"])


def _colecao():
    return cliente_cifrado()[settings.mongo_db][COLECAO_CIFRADA]


def _tentar(descricao: str, comando: str, razao: str, fn):
    """Roda a operação de verdade. Sucesso e falha são os dois resultados válidos.

    E há um terceiro, que é o pior de todos: a operação que NÃO falha e devolve
    resultado sem sentido. `sort` sobre campo cifrado é exatamente isso — ele
    ordena por ciphertext, em silêncio. Um erro do servidor um time descobre no
    primeiro teste; uma ordenação errada vai para produção.
    """
    try:
        amostra = fn()
        silenciosa = isinstance(amostra, dict) and amostra.get("__silenciosa__") is True
        return {
            "tentativa": descricao,
            "comando": comando,
            "funcionou": True,
            "silenciosa": silenciosa,
            "razao": razao,
            "resultado": serializar(amostra),
            "erro": None,
        }
    except Exception as exc:
        return {
            "tentativa": descricao,
            "comando": comando,
            "funcionou": False,
            "silenciosa": False,
            "razao": razao,
            "resultado": None,
            "erro": erro_do_servidor(exc),
        }


def _sort_silencioso() -> dict:
    """A evidência do pior caso: a ordem devolvida contra a ordem real.

    Medido no cluster: `sort("salario", 1)` devolveu 11245, 6281, 6594, 6671,
    16309, 9825, 11075, 18542. Nenhum erro, nenhum aviso, ordem errada.
    """
    docs = list(_colecao().find({}, {"nome": 1, "salario": 1}).sort("salario", 1).limit(8))
    ordem = [doc["salario"] for doc in docs]
    return {
        "__silenciosa__": True,
        "ordem_devolvida": ordem,
        "ordem_real": sorted(ordem),
        "esta_ordenada": ordem == sorted(ordem),
        "nomes": [doc["nome"] for doc in docs],
    }


TENTATIVAS = {
    "sort": (
        "sort por campo range cifrado",
        'find({}).sort("salario", 1).limit(8)',
        "não falha: ordena por ciphertext e devolve ordem sem sentido, em silêncio",
        lambda: _sort_silencioso(),
    ),
    "regex": (
        "regex em campo cifrado",
        'find({"email": {"$regex": "^ana"}})',
        "o servidor precisaria do texto em claro para casar o padrão",
        lambda: list(_colecao().find({"email": {"$regex": "^ana"}}).limit(3)),
    ),
    "search": (
        "$search (Atlas Search) sobre campo cifrado",
        '$search: { text: { query: "…", path: "observacoes" } }',
        "o índice do Atlas Search é construído sobre plaintext, que não existe no servidor "
        "(sem índice definido, o erro que aparece é o da ausência dele)",
        lambda: list(
            _colecao().aggregate(
                [{"$search": {"text": {"query": "credito", "path": "observacoes"}}}, {"$limit": 3}]
            )
        ),
    ),
    "group": (
        "$group / $sum sobre campo cifrado",
        '$group: { _id: "$uf", total: { $sum: "$salario" } }',
        "agregação no servidor precisa do valor numérico, e ele está cifrado",
        lambda: list(
            _colecao().aggregate([{"$group": {"_id": "$uf", "total": {"$sum": "$salario"}}}, {"$limit": 3}])
        ),
    ),
    "lookup": (
        "$lookup casando por campo cifrado",
        '$lookup: { localField: "cpf", foreignField: "cpf", … }',
        "o join compara valores no servidor; ciphertexts randomizados nunca casam",
        lambda: list(
            _colecao().aggregate(
                [
                    {"$lookup": {"from": COLECAO_CIFRADA, "localField": "cpf",
                                 "foreignField": "cpf", "as": "par"}},
                    {"$limit": 3},
                ]
            )
        ),
    ),
    "indice": (
        "índice comum sobre campo cifrado",
        'createIndex({ "cpf": 1 })',
        "campo cifrado é indexado pelas enxcol_.*, mantidas pelo servidor; índice comum é recusado",
        lambda: _colecao().create_index("cpf"),
    ),
    "inc": (
        "$inc em campo range cifrado",
        'updateOne({…}, { $inc: { salario: 100 } })',
        "o servidor não faz aritmética sobre ciphertext",
        lambda: _colecao().update_one({}, {"$inc": {"salario": 100}}).raw_result,
    ),
}


@router.get("/lista")
def lista():
    return {
        "tentativas": [
            {"chave": chave, "tentativa": t[0], "comando": t[1], "razao": t[2]}
            for chave, t in TENTATIVAS.items()
        ]
    }


@router.get("/tentar/{chave}")
def tentar(chave: str):
    """GET de propósito: a guarda de mutação ignora métodos seguros, e a única
    tentativa que muda estado (`$inc`) falha antes de escrever qualquer coisa."""
    if chave not in TENTATIVAS:
        raise HTTPException(status_code=404, detail=f"Tentativa desconhecida: {chave}")
    descricao, comando, razao, fn = TENTATIVAS[chave]
    return _tentar(descricao, comando, razao, fn)


@router.get("/modelagem")
def modelagem():
    """A resposta, não o consolo.

    A pergunta seguinte do cliente é sempre "então como eu faço meu relatório?".
    Campo cifrado é campo de filtro e de leitura, não de análise: o que se agrega
    é a faixa derivada, com a granularidade que o time de privacidade aceitar —
    grossa o bastante para não reidentificar, fina o bastante para servir.
    """
    try:
        distribuicao = list(
            _colecao().aggregate(
                [
                    {"$group": {"_id": "$faixa_salarial", "titulares": {"$sum": 1}}},
                    {"$sort": {"_id": 1}},
                ]
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc
    return {
        "padrao": "campo derivado em claro ao lado do campo cifrado",
        "exemplo": {"cifrado": "salario", "derivado": "faixa_salarial"},
        "pipeline": '$group: { _id: "$faixa_salarial", titulares: { $sum: 1 } }',
        "distribuicao": serializar(distribuicao),
        "nota": (
            "`faixa_salarial` é calculada pela aplicação no momento da escrita, a "
            "partir do salário ainda em claro na memória do cliente. O servidor "
            "recebe a faixa já pronta e o salário já cifrado."
        ),
    }
