"""O mapa de campos cifrados é imutável depois do create_collection.

Trocar queryType, contention, min/max ou adicionar campo exige dropar e recriar
a coleção — o único erro desta PoV que custa o dataset. Estes testes são o
alarme: se alguém mexer no mapa sem querer, quebra aqui e não em produção.
"""

import encryption
from settings import settings


def _campos():
    ns = f"{settings.mongo_db}.{encryption.COLECAO_CIFRADA}"
    return {campo["path"]: campo for campo in encryption.encrypted_fields()[ns]["fields"]}


def test_cinco_campos_cifrados():
    assert set(_campos()) == set(encryption.CAMPOS_CIFRADOS)


def test_cpf_e_email_sao_equality():
    campos = _campos()
    for path in ("cpf", "email"):
        assert campos[path]["queries"]["queryType"] == "equality"


def test_salario_e_score_sao_range_com_faixa_declarada():
    campos = _campos()
    for path, teto in (("salario", 1_000_000), ("score_credito", 1_000)):
        queries = campos[path]["queries"]
        assert queries["queryType"] == "range"
        # Faixa com folga de negócio, não com o máximo do seed: subir o max
        # depois obriga a recriar a coleção.
        assert queries["min"] == 0 and queries["max"] == teto


def test_observacoes_nao_e_consultavel():
    # De propósito: campo cifrado sem `queries` não paga custo de metadados.
    assert "queries" not in _campos()["observacoes"]


def test_campos_claros_nao_aparecem_no_mapa():
    campos = _campos()
    for path in encryption.CAMPOS_CLAROS:
        assert path not in campos


def test_resumo_dek_nunca_devolve_material_completo():
    documento = {
        "_id": "abc",
        "keyAltNames": ["dek-principal"],
        "keyMaterial": b"\xff" * 120,
        "masterKey": {"provider": "local"},
    }
    resumo = encryption.resumo_dek(documento)
    assert resumo["material_bytes"] == 120
    # Amostra de 12 bytes, nunca os 120.
    assert len(resumo["material_amostra"]) < 30
    assert "keyMaterial" not in resumo


def test_descricao_kms_local_avisa_que_nao_e_producao():
    if settings.kms_provider != "local":
        return
    descricao = encryption.descricao_kms()
    assert descricao["producao"] is False
    assert descricao["aviso"]
