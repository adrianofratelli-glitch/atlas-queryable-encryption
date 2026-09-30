"""Serialização compartilhada pelos routers.

A regra desta PoV é que a tela nunca mostre um valor sem procedência. Por isso a
serialização é explícita: `Binary(subtype 6)` vira um objeto rotulado, com o
tamanho real em bytes ao lado — é ele que explica o overhead de storage no
módulo 06 — e nunca um texto ilustrativo.
"""

from __future__ import annotations

from datetime import date, datetime

from bson import Binary, ObjectId

# Subtipo BSON 6 = ciphertext de Queryable Encryption / CSFLE.
SUBTIPO_CIFRADO = 6

# Um payload de subtipo 6 começa com 1 byte de tipo de blob seguido do UUID de
# 16 bytes da DEK. Esses 17 bytes são IGUAIS para todo valor daquele campo — é
# o endereço da chave, não o segredo.
#
# Mostrar o começo do blob na tela era um defeito grave e silencioso: dois CPF
# distintos apareciam com o mesmo hex, e o par plantado do módulo 02 provava o
# oposto do que existe para provar. A amostra tem que sair do payload.
CABECALHO_BYTES = 17


def _binario(valor: Binary) -> dict:
    bruto = bytes(valor)
    cifrado = valor.subtype == SUBTIPO_CIFRADO
    payload = bruto[CABECALHO_BYTES:] if cifrado else bruto
    return {
        "__cifrado__": cifrado,
        "subtype": valor.subtype,
        "bytes": len(bruto),
        # Identifica a DEK usada: igual para todo valor do mesmo campo, e é isso
        # que a tela rotula como chave — nunca como ciphertext.
        "chave": bruto[1:CABECALHO_BYTES].hex() if cifrado else None,
        "hex": payload[:16].hex(),
        "fim": payload[-8:].hex() if len(payload) > 24 else None,
    }


def serializar(valor):
    if isinstance(valor, Binary):
        return _binario(valor)
    if isinstance(valor, ObjectId):
        return str(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: serializar(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [serializar(item) for item in valor]
    if isinstance(valor, bytes):
        return {"__bytes__": len(valor), "hex": valor[:16].hex()}
    return valor


def erro_do_servidor(exc: Exception) -> dict:
    """A mensagem crua do MongoDB. O módulo 04 depende de ela não ser traduzida:
    o valor da tela está em o erro vir do servidor, não de um texto nosso."""
    detalhe = {"tipo": type(exc).__name__, "mensagem": str(exc)}
    codigo = getattr(exc, "code", None)
    if codigo is not None:
        detalhe["codigo"] = codigo
    return detalhe
