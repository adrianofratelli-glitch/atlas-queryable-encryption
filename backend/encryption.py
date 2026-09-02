"""Os dois clientes MongoDB desta PoV, o cofre de chaves e o mapa de campos cifrados.

A PoV inteira nasce da diferença entre dois objetos deste módulo:

- `cliente_cifrado()` — MongoClient com `AutoEncryptionOpts`. É a aplicação: ele
  cifra na saída e decifra na volta, e o código que usa ele não sabe disso.
- `cliente_claro()` — MongoClient comum, mesma URI, mesmo cluster. É o DBA, o
  operador da nuvem e quem levar o backup. Ele nunca escreve nesta PoV.

Nada aqui devolve chave mestra, DEK decifrada ou `keyMaterial` cru. O módulo 01
mostra o documento da DEK com o material truncado e rotulado como cifrado pela
CMK; material completo se investiga no mongosh, não pela API.
"""

from __future__ import annotations

import base64
import logging
import threading
from pathlib import Path

from bson.binary import UUID_SUBTYPE, Binary
from pymongo import MongoClient
from pymongo.encryption import ClientEncryption
from pymongo.encryption_options import AutoEncryptionOpts

from routers._comum import erro_do_servidor
from settings import settings

APP_NAME = "atlas-queryable-encryption"

COLECAO_CIFRADA = "clientes"
# UMA coleção, e só uma. Os dois painéis da tela leem esta mesma coleção — o que
# muda entre eles é o CLIENTE (com e sem AutoEncryptionOpts), nunca o destino da
# query. Uma segunda coleção com os mesmos dados em claro existiu enquanto a PoV
# media overhead de storage; ela sumiu junto com aquela tela, e ainda bem: cem
# mil CPF legíveis num projeto que argumenta que ninguém consegue ler o dado é o
# tipo de coisa que derruba a reunião se alguém abrir o Compass.

# Ordem fixa: ela define os nomes das DEKs, e renomear DEK depois do seed obriga
# a recriar a coleção.
CAMPOS_CIFRADOS = ("cpf", "email", "salario", "score_credito", "observacoes")
CAMPOS_CLAROS = ("nome", "cidade", "uf", "tenant_id", "faixa_salarial", "cadastro_em")

COLECOES_CIFRADAS = (COLECAO_CIFRADA,)

logger = logging.getLogger("qe.encryption")


def nome_dek(colecao: str, campo: str) -> str:
    """Uma DEK POR CAMPO POR COLEÇÃO.

    Não é escolha de modelagem: o Queryable Encryption recusa a coleção se dois
    campos compartilharem keyId — `Duplicate key ids are not allowed`, code
    6338401, vindo da própria crypt_shared antes de a requisição sair da
    máquina. Cinco campos cifrados são cinco DEKs.
    """
    return f"dek-{colecao}-{campo}"


def nomes_dek() -> list[str]:
    return [nome_dek(colecao, campo)
            for colecao in COLECOES_CIFRADAS
            for campo in CAMPOS_CIFRADOS]


# ── Mapa de campos cifrados ──────────────────────────────────────────────────
# IMUTÁVEL depois do create_collection. Trocar queryType, contention, min/max ou
# adicionar campo exige dropar e recriar a coleção — o único erro desta PoV que
# custa o dataset inteiro. Decida uma vez, aqui.
#
# `observacoes` não tem `queries` de propósito: campo cifrado e não consultável
# não paga custo de metadados. É uma decisão de modelagem que a demo vende.
def _campos(colecao: str) -> list[dict]:
    forte = settings.contention_factor
    faixa = max(0, forte // 2)
    def chave(campo: str):
        return dek_id(nome_dek(colecao, campo))
    return [
        {"keyId": chave("cpf"), "path": "cpf", "bsonType": "string",
         "queries": {"queryType": "equality", "contention": forte}},
        {"keyId": chave("email"), "path": "email", "bsonType": "string",
         "queries": {"queryType": "equality", "contention": forte}},
        {"keyId": chave("salario"), "path": "salario", "bsonType": "int",
         "queries": {"queryType": "range", "contention": faixa,
                     "min": 0, "max": 1_000_000, "sparsity": 1}},
        {"keyId": chave("score_credito"), "path": "score_credito", "bsonType": "int",
         "queries": {"queryType": "range", "contention": faixa,
                     "min": 0, "max": 1_000, "sparsity": 1}},
        {"keyId": chave("observacoes"), "path": "observacoes", "bsonType": "string"},
    ]


_deks_cache: dict[str, object] = {}


def dek_id(nome: str):
    """UUID da DEK, resolvido pelo keyAltName no cofre.

    O mapa de campos precisa do keyId no momento em que o cliente é construído;
    é por isso que o cofre tem de existir ANTES do primeiro cliente cifrado.
    Sem o índice único parcial em `keyAltNames` esta busca seria não
    determinística — daí ele ser criado pelo scripts/criar-cofre.py.

    Uma DEK ausente tem duas causas opostas, e confundi-las custa caro:

    - o cofre nunca foi montado — erro de setup, tem que estourar alto;
    - a DEK foi apagada por um crypto shredding — estado ESPERADO, e o processo
      precisa continuar subindo. Um backend que não reinicia depois de um
      shredding transforma um recurso de privacidade em incidente de
      disponibilidade.

    A distinção é feita pela existência de qualquer outra DEK no cofre. No caso
    do shredding devolvemos um keyId inexistente, para o mapa continuar
    bem-formado: sem ele o campo perderia auto-encryption e passaria a devolver
    ciphertext em silêncio, que parece bug em vez de chave apagada.
    """
    if nome in _deks_cache:
        return _deks_cache[nome]
    cofre = key_vault_collection()
    documento = cofre.find_one({"keyAltNames": nome})
    if documento is None:
        if cofre.count_documents({}, limit=1) == 0:
            raise RuntimeError(
                f"Cofre vazio: a DEK '{nome}' não existe. Rode scripts/criar-cofre.py."
            )
        # Cofre não vazio mas ESTA DEK específica sumiu: pode ser shredding
        # intencional, mas também pode ser índice corrompido, replicação
        # parcial ou nome de DEK digitado errado após deploy. Silenciar os
        # dois casos do mesmo jeito escondia o segundo — loga um warning para
        # dar pista de correlação sem impedir o boot.
        logger.warning(
            "DEK ausente no cofre (nome=%s) com cofre não vazio — tratando como "
            "crypto shredding esperado; se não foi intencional, verifique o "
            "keyAltName e a saúde da replicação do keyVault.",
            nome,
        )
        return Binary(_UUID_AUSENTE, UUID_SUBTYPE)
    _deks_cache[nome] = documento["_id"]
    return documento["_id"]


_UUID_AUSENTE = b"\x00" * 16


def limpar_cache_deks() -> None:
    _deks_cache.clear()


def encrypted_fields() -> dict:
    """encryptedFieldsMap da coleção cifrada, cada campo com sua DEK."""
    return {
        f"{settings.mongo_db}.{colecao}": {"fields": _campos(colecao)}
        for colecao in COLECOES_CIFRADAS
    }


# ── Provedor de KMS ──────────────────────────────────────────────────────────
def kms_providers() -> dict:
    """Credenciais do KMS ativo. A chave local é lida do disco, nunca do .env."""
    if settings.kms_provider == "aws":
        return {
            "aws": {
                "accessKeyId": settings.aws_access_key_id,
                "secretAccessKey": settings.aws_secret_access_key,
            }
        }
    caminho = Path(settings.local_master_key_path)
    if not caminho.exists():
        raise RuntimeError(
            "Chave mestra local ausente. Rode scripts/gerar-master-key.py e "
            "aponte QE_LOCAL_MASTER_KEY_PATH para o arquivo gerado."
        )
    material = caminho.read_bytes()
    if len(material) != 96:
        raise RuntimeError(f"Chave mestra local precisa ter 96 bytes; o arquivo tem {len(material)}.")
    return {"local": {"key": material}}


def master_key_ref() -> dict:
    """Referência à CMK usada ao criar uma DEK. Vazia no modo local."""
    if settings.kms_provider == "aws":
        return {"region": settings.aws_kms_region, "key": settings.aws_kms_key_arn}
    return {}


def descricao_kms() -> dict:
    """O que a tela do módulo 01 mostra sobre o provedor — sem material de chave."""
    if settings.kms_provider == "aws":
        return {
            "provedor": "aws",
            "configurado": settings.aws_configurado,
            "regiao": settings.aws_kms_region,
            "cmk": settings.aws_kms_key_arn or None,
            "producao": True,
            "aviso": None,
        }
    caminho = settings.local_master_key_path
    return {
        "provedor": "local",
        "configurado": bool(caminho) and Path(caminho).exists(),
        "regiao": None,
        "cmk": f"arquivo local ({Path(caminho).name})" if caminho else None,
        "producao": False,
        "aviso": (
            "KMS local não é para produção: a chave mestra fica em disco ao lado da "
            "aplicação, o que anula boa parte do modelo de ameaça. Em produção use "
            "AWS KMS, Azure Key Vault, GCP KMS ou KMIP."
        ),
    }


# ── Clientes ─────────────────────────────────────────────────────────────────
_lock = threading.Lock()
_cliente_claro: MongoClient | None = None
_cliente_cifrado: MongoClient | None = None

# URI local somente evita que a importação masque uma configuração ausente.
# O readiness continua indisponível até MONGO_URI ser configurada.
def _uri() -> str:
    return settings.mongo_uri or "mongodb://127.0.0.1:27017"


def _timeouts() -> dict:
    return {
        "serverSelectionTimeoutMS": settings.mongo_timeout_ms,
        "connectTimeoutMS": settings.mongo_timeout_ms,
        "socketTimeoutMS": max(settings.mongo_timeout_ms * 2, 10_000),
    }


def cliente_claro() -> MongoClient:
    """A visão do DBA. Read-only por contrato desta PoV."""
    global _cliente_claro
    with _lock:
        if _cliente_claro is None:
            _cliente_claro = MongoClient(
                _uri(), appname=f"{APP_NAME}-claro", connect=False, **_timeouts()
            )
        return _cliente_claro


def _auto_encryption_opts() -> AutoEncryptionOpts:
    return AutoEncryptionOpts(
        kms_providers=kms_providers(),
        key_vault_namespace=settings.key_vault_ns,
        encrypted_fields_map=encrypted_fields(),
        # required=True é obrigatório aqui: sem ele o driver cai silenciosamente
        # para o mongocryptd, que sobe um processo órfão em :27020 e falha depois
        # de um jeito que parece problema de rede. Falhar no boot é melhor.
        crypt_shared_lib_path=settings.crypt_shared_path or None,
        crypt_shared_lib_required=True,
    )


def cliente_cifrado() -> MongoClient:
    """A aplicação. Cifra na saída, decifra na volta, transparente."""
    global _cliente_cifrado
    if _cliente_cifrado is not None:
        return _cliente_cifrado
    if not settings.crypt_shared_disponivel:
        raise RuntimeError(
            "crypt_shared não encontrada. Rode scripts/instalar-crypt-shared.sh "
            "e aponte CRYPT_SHARED_PATH para a biblioteca."
        )
    # As opções são montadas FORA do lock de propósito. Montá-las lê o cofre —
    # `encrypted_fields()` resolve o keyId de cada campo — e ler o cofre usa o
    # cliente claro, que disputa este mesmo lock. Com um Lock não reentrante
    # isso é deadlock: o processo para a 0% de CPU, sem exceção e sem timeout,
    # e a cara do sintoma é problema de rede.
    opcoes = _auto_encryption_opts()
    with _lock:
        if _cliente_cifrado is None:
            _cliente_cifrado = MongoClient(
                _uri(),
                appname=f"{APP_NAME}-cifrado",
                connect=False,
                auto_encryption_opts=opcoes,
                **_timeouts(),
            )
        return _cliente_cifrado


def reiniciar_cliente_cifrado() -> None:
    """Descarta o cliente cifrado e o cache de DEK que ele carrega.

    O driver mantém a DEK decifrada em memória (padrão de 60 s). Depois de um
    crypto shredding, sem isso o documento continua abrindo e a demo parece
    falhar — quando na verdade é um cache se comportando corretamente. O módulo
    05 mostra essa limpeza como um passo visível da linha do tempo.
    """
    global _cliente_cifrado
    with _lock:
        antigo, _cliente_cifrado = _cliente_cifrado, None
    if antigo is not None:
        antigo.close()


def fechar_clientes() -> None:
    global _cliente_claro, _cliente_cifrado
    with _lock:
        for cliente in (_cliente_claro, _cliente_cifrado):
            if cliente is not None:
                cliente.close()
        _cliente_claro = None
        _cliente_cifrado = None


# ── Cofre ────────────────────────────────────────────────────────────────────
def client_encryption() -> ClientEncryption:
    """Handle explícito do cofre: criar DEK, rotacionar, cifrar valor avulso."""
    return ClientEncryption(
        kms_providers=kms_providers(),
        key_vault_namespace=settings.key_vault_ns,
        key_vault_client=cliente_claro(),
        codec_options=cliente_claro().codec_options,
    )


def key_vault_collection():
    db_name, col_name = settings.key_vault_ns.split(".", 1)
    return cliente_claro()[db_name][col_name]


def resumo_dek(documento: dict) -> dict:
    """Documento de DEK seguro para a tela: sem keyMaterial completo."""
    material = documento.get("keyMaterial")
    if isinstance(material, bytes):
        amostra = base64.b64encode(material[:12]).decode()
        tamanho = len(material)
    else:
        amostra, tamanho = None, None
    return {
        "id": str(documento.get("_id")),
        "nomes": list(documento.get("keyAltNames", [])),
        "criada_em": documento.get("creationDate").isoformat() if documento.get("creationDate") else None,
        "atualizada_em": documento.get("updateDate").isoformat() if documento.get("updateDate") else None,
        "provedor": (documento.get("masterKey") or {}).get("provider"),
        "material_bytes": tamanho,
        "material_amostra": f"{amostra}…" if amostra else None,
        "material_nota": "cifrado pela CMK — o MongoDB nunca vê este material em claro",
    }


def readiness() -> tuple[bool, str]:
    if not settings.mongo_uri:
        return False, "MONGO_URI não configurada"
    try:
        cliente_claro().admin.command("ping")
        return True, "MongoDB conectado"
    except Exception as exc:  # detalhes completos só nos logs do backend
        # erro_do_servidor() extrai code/codeName do MongoDB quando existem —
        # é a diferença entre "cluster fora do ar", "sem permissão" e "IP fora
        # da allowlist" no selo, em vez de só o nome genérico da exceção.
        detalhe = erro_do_servidor(exc)
        codigo = f" (code={detalhe['codigo']})" if "codigo" in detalhe else ""
        return False, f"MongoDB indisponível: {detalhe['tipo']}{codigo}: {detalhe['mensagem']}"


def versao_servidor() -> tuple[int, int, str]:
    """Queryable Encryption exige 7.0+; `range` só é GA a partir do 8.0."""
    info = cliente_claro().admin.command("buildInfo")
    versao = info.get("version", "0.0.0")
    partes = versao.split(".")
    maior = int(partes[0]) if partes and partes[0].isdigit() else 0
    menor = int(partes[1]) if len(partes) > 1 and partes[1].isdigit() else 0
    return maior, menor, versao
