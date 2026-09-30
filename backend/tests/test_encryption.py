"""O mapa de campos cifrados é imutável depois do create_collection.

Trocar queryType, contention, min/max ou adicionar campo exige dropar e recriar
a coleção — o único erro desta PoV que custa o dataset. Estes testes são o
alarme: se alguém mexer no mapa sem querer, quebra aqui e não em produção.
"""

import pytest
from bson import Binary

import encryption
from settings import settings


class CofreFalso:
    """O cofre que `encrypted_fields()` consulta para resolver o keyId de cada
    DEK. Sem este stub o teste abre conexão de verdade: passa na máquina de quem
    tem `.env` apontando para um cluster e falha no CI, que é exatamente o
    inverso do que um teste unitário deve fazer."""

    def find_one(self, filtro):
        nome = filtro["keyAltNames"]
        return {"_id": Binary(nome.encode()[:16].ljust(16, b"\0"), 4)}

    def count_documents(self, _filtro, **_kw):
        return len(encryption.CAMPOS_CIFRADOS)


@pytest.fixture(autouse=True)
def cofre_stubado(monkeypatch):
    monkeypatch.setattr(encryption, "key_vault_collection", CofreFalso)
    encryption.limpar_cache_deks()
    yield
    encryption.limpar_cache_deks()


def _campos():
    ns = f"{settings.mongo_db}.{encryption.COLECAO_CIFRADA}"
    return {campo["path"]: campo for campo in encryption.encrypted_fields()[ns]["fields"]}


def test_oito_campos_cifrados():
    assert set(_campos()) == set(encryption.CAMPOS_CIFRADOS)


def test_cpf_e_email_sao_equality():
    campos = _campos()
    for path in ("cpf", "email"):
        assert campos[path]["queries"]["queryType"] == "equality"


def test_buscas_parciais_de_email_usam_string_query_ga():
    campos = _campos()
    for path, query_type in (("email_prefix", "prefix"), ("email_suffix", "suffix"),
                             ("email_substring", "substring")):
        queries = campos[path]["queries"]
        assert queries["queryType"] == query_type
        assert queries["strMinQueryLength"] == 3
        assert queries["caseSensitive"] is False
        assert queries["diacriticSensitive"] is False
    assert campos["email_substring"]["queries"]["strMaxLength"] == 40
    assert campos["email_substring"]["queries"]["strMaxQueryLength"] == 6


def test_opcoes_string_sao_feitas_e_nao_expoem_texto_livre():
    from routers.demo import BUSCAS_STRING

    assert set(BUSCAS_STRING) == {"prefixo", "sufixo", "trecho"}
    assert {item["operador"] for item in BUSCAS_STRING.values()} == {
        "$encStrStartsWith", "$encStrEndsWith", "$encStrContains"
    }
    assert all(item["valor"] for item in BUSCAS_STRING.values())


def test_busca_string_exibe_resultado_decifrado_e_view_do_dba(monkeypatch):
    from bson import ObjectId, Binary
    from routers import demo

    oid = ObjectId()
    encrypted_doc = {"_id": oid, "nome": "Titular Um", "email_prefix": "titular0@exemplo.invalid"}
    raw_doc = {"_id": oid, "nome": "Titular Um", "email_prefix": Binary(b"x" * 40, 6)}
    filters = []

    class Cursor:
        def __init__(self, docs): self.docs = docs
        def limit(self, _n): return self.docs
        def __iter__(self): return iter(self.docs)

    class Collection:
        def __init__(self, doc): self.doc = doc
        def find(self, filtro, _projection):
            filters.append(filtro)
            return Cursor([self.doc])

    class DatabaseClient:
        def __init__(self, doc): self.doc = doc
        def __getitem__(self, _db): return Database(self.doc)
        def server_info(self): return {"versionArray": [9, 0, 0]}

    class Database:
        def __init__(self, doc): self.collection = Collection(doc)
        def __getitem__(self, _name): return self.collection

    monkeypatch.setattr(demo, "cliente_cifrado", lambda: DatabaseClient(encrypted_doc))
    monkeypatch.setattr(demo, "cliente_claro", lambda: DatabaseClient(raw_doc))
    result = demo.buscar_string("prefixo")

    assert result["aplicacao"]["encontrados"] == result["dba"]["encontrados"] == 1
    assert result["aplicacao"]["documentos"][0]["email_prefix"] == "titular0@exemplo.invalid"
    assert result["dba"]["documentos"][0]["email_prefix"]["__cifrado__"] is True
    assert filters[0]["$expr"]["$encStrStartsWith"]["prefix"] == "titular0"
    assert filters[1] == {"_id": {"$in": [oid]}}


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
