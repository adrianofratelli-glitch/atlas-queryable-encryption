"""Módulo 01 — Cofre de chaves.

Mostra a hierarquia inteira: provedor de KMS ativo, CMK, DEKs em __keyVault e o
mapeamento de campo para chave. Criar DEK é a única mutação barata da PoV; as
outras (rotação, shredding) são destrutivas e moram nos módulos 01 e 05.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from ._comum import erro_do_servidor
from encryption import (
    CAMPOS_CIFRADOS,
    CAMPOS_CLAROS,
    COLECAO_CIFRADA,
    client_encryption,
    descricao_kms,
    encrypted_fields,
    key_vault_collection,
    master_key_ref,
    resumo_dek,
)
from settings import settings

router = APIRouter(prefix="/cofre", tags=["01 · cofre de chaves"])


@router.get("/kms")
def kms():
    """O provedor ativo. Nunca devolve material de chave."""
    descricao = descricao_kms()
    descricao["cofre_namespace"] = settings.key_vault_ns
    descricao["nota_separacao"] = (
        "Nesta PoV o cofre vive no mesmo cluster do dado. Em cliente regulado o "
        "desenho é cofre em cluster separado, com credencial separada: quem tem "
        "acesso ao dado não tem acesso à chave."
    )
    return descricao


@router.get("/deks")
def listar_deks():
    documentos = list(key_vault_collection().find({}).sort("creationDate", 1))
    return {"total": len(documentos), "deks": [resumo_dek(doc) for doc in documentos]}


@router.get("/mapa")
def mapa_de_campos():
    """Qual campo é cifrado, com qual tipo de consulta, e qual continua em claro."""
    ns = f"{settings.mongo_db}.{COLECAO_CIFRADA}"
    campos = encrypted_fields()[ns]["fields"]
    cifrados = [
        {
            "campo": campo["path"],
            "tipo": campo["bsonType"],
            "consulta": (campo.get("queries") or {}).get("queryType", "nenhuma"),
            "contention": (campo.get("queries") or {}).get("contention"),
            "faixa": (
                {"min": campo["queries"]["min"], "max": campo["queries"]["max"]}
                if (campo.get("queries") or {}).get("queryType") == "range"
                else None
            ),
        }
        for campo in campos
    ]
    return {
        "namespace": ns,
        "cifrados": cifrados,
        "claros": list(CAMPOS_CLAROS),
        "nota_observacoes": (
            "`observacoes` é cifrado e NÃO consultável de propósito: campo sem "
            "`queries` não paga custo de metadados. Se o negócio nunca filtra por "
            "ele, essa é a modelagem certa."
        ),
        "nota_imutabilidade": (
            "Este mapa é imutável depois do create_collection. Mudar queryType, "
            "contention, min/max ou adicionar campo exige dropar e recriar a coleção."
        ),
        "total_cifrados": len(CAMPOS_CIFRADOS),
    }


@router.post("/deks")
def criar_dek(nome: str = Body(..., embed=True, min_length=3, max_length=64)):
    """Cria uma DEK com um keyAltName legível. A tela fica melhor com nome que com UUID."""
    if key_vault_collection().find_one({"keyAltNames": nome}):
        raise HTTPException(status_code=409, detail=f"Já existe uma DEK com o nome '{nome}'.")
    try:
        with client_encryption() as cofre:
            dek_id = cofre.create_data_key(
                settings.kms_provider, master_key=master_key_ref() or None, key_alt_names=[nome]
            )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc
    documento = key_vault_collection().find_one({"_id": dek_id})
    return {"criada": True, "dek": resumo_dek(documento)}


@router.post("/rotacionar-cmk")
def rotacionar_cmk():
    """Recifra as DEKs sob a CMK atual — barato e instantâneo.

    Isso NÃO recifra os campos: os campos continuam cifrados pelas mesmas DEKs,
    que apenas passaram a ser guardadas sob outra CMK. Recifrar campo exigiria
    reescrever a coleção inteira. Falar isso errado numa reunião de segurança é
    caro, e é por isso que a resposta carrega os dois fatos separados.
    """
    try:
        with client_encryption() as cofre:
            resultado = cofre.rewrap_many_data_key({}, provider=settings.kms_provider,
                                                   master_key=master_key_ref() or None)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=erro_do_servidor(exc)) from exc
    atualizadas = getattr(getattr(resultado, "bulk_write_result", None), "modified_count", 0)
    return {
        "deks_recifradas": atualizadas,
        "campos_recifrados": 0,
        "nota": (
            "Rotação de CMK recifra as DEKs, não os campos. Os dados permanecem "
            "cifrados pelas mesmas DEKs; apenas o envelope mudou."
        ),
    }


def preflight_checks() -> dict:
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
