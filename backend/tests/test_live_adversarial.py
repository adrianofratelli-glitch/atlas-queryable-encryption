"""Adversarial contra o cluster real, num banco `*_test` já resetado.

Pulado por padrão (CI não tem cluster). Para rodar:

    QE_LIVE=1 QE_DB=<banco>_test QE_KEY_VAULT_NS=<banco>_test.__keyVault \\
        backend/venv/bin/python -m pytest backend/tests/test_live_adversarial.py

Pré-requisito: `scripts/reset_demo.py` no mesmo banco `_test`. Os testes que
escrevem apagam o que inseriram; o reset seguinte deixa tudo como estava.
"""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import bson
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

import encryption
import settings as settings_mod

LIVE = os.getenv("QE_LIVE") == "1"
pytestmark = pytest.mark.skipif(
    not LIVE or not settings_mod.banco_de_teste(settings_mod.settings.mongo_db)
    or not settings_mod.banco_de_teste(settings_mod.settings.key_vault_ns.split(".", 1)[0]),
    reason="exige QE_LIVE=1 e QE_DB/QE_KEY_VAULT_NS terminados em _test",
)


@pytest.fixture(scope="module")
def api():
    import main
    with TestClient(main.app) as cliente:
        yield cliente


@pytest.fixture(scope="module")
def titulares(api):
    corpo = api.get("/demo/exemplos", params={"quantos": 8}).json()
    assert len(corpo["titulares"]) == 8
    return corpo["titulares"]


@pytest.fixture
def cifrada():
    return encryption.cliente_cifrado()[settings_mod.settings.mongo_db][encryption.COLECAO_CIFRADA]


@pytest.fixture
def clara():
    return encryption.cliente_claro()[settings_mod.settings.mongo_db][encryption.COLECAO_CIFRADA]


# ── O servidor só vê ciphertext ──────────────────────────────────────────────
def test_preflight_verde(api):
    corpo = api.get("/preflight").json()
    assert corpo["ready"], {k: v for k, v in corpo["checks"].items() if not v["ok"]}


def test_dba_le_binary6_e_nunca_plaintext(api, titulares):
    alvo = titulares[0]["cpf"]
    corpo = api.get("/demo/buscar", params={"cpf": alvo}).json()
    assert corpo["aplicacao"]["encontrados"] == 1
    assert corpo["dba"]["encontrados"] == 0 and corpo["dba"]["origem"] == "por_id"
    dba = corpo["dba"]["documentos"]
    assert dba, "a leitura por _id tem de trazer o documento cifrado"
    for doc in dba:
        for campo in ("cpf", "email", "salario"):
            assert doc[campo]["__cifrado__"] is True and doc[campo]["subtype"] == 6
    assert alvo not in json.dumps(dba)


def test_comando_que_chega_ao_servidor_nao_tem_o_cpf(api, titulares):
    alvo = titulares[1]["cpf"]
    enviado = api.get("/demo/buscar", params={"cpf": alvo}).json()["query_details"]["sent_to_server"]
    assert enviado["find"] == "clientes"
    assert alvo not in json.dumps(enviado)
    assert "Binary subtype 6" in json.dumps(enviado["filter"])


def test_bson_do_comando_capturado_nao_contem_os_bytes_do_cpf(cifrada, titulares):
    alvo = titulares[2]["cpf"]
    _, enviado = encryption.executar_capturando("find", "clientes", lambda: list(cifrada.find({"cpf": alvo}).limit(1)))
    assert enviado is not None
    assert alvo.encode() not in bson.encode(enviado)


def test_faixa_chega_cifrada(api):
    corpo = api.get("/demo/buscar", params={"salario_min": 12345, "salario_max": 23456}).json()
    filtro = json.dumps(corpo["query_details"]["sent_to_server"]["filter"])
    assert "12345" not in filtro and "23456" not in filtro
    assert "Binary subtype 6" in filtro
    assert corpo["aplicacao"]["encontrados"] >= 1 and corpo["dba"]["encontrados"] == 0


def test_controle_em_claro_casa_dos_dois_lados(api):
    corpo = api.get("/demo/buscar", params={"uf": "SP"}).json()
    assert corpo["aplicacao"]["encontrados"] == corpo["dba"]["encontrados"] == 5


@pytest.mark.parametrize("tipo", ["prefixo", "sufixo", "trecho"])
def test_busca_string_chega_cifrada(api, tipo):
    corpo = api.get("/demo/buscar-string", params={"tipo": tipo}).json()
    assert corpo["aplicacao"]["encontrados"] >= 1
    enviado = json.dumps(corpo["enviado_ao_servidor"])
    assert corpo["valor"] not in enviado
    assert all(doc[corpo["campo"]]["__cifrado__"] for doc in corpo["dba"]["documentos"])


def test_par_plantado_tem_ciphertexts_distintos(api):
    corpo = api.get("/demo/par-repetido").json()
    assert corpo["ciphertexts_distintos"] is True
    assert corpo["aplicacao"][0]["cpf"] == corpo["aplicacao"][1]["cpf"]


def test_explain_nao_expoe_plaintext(cifrada, titulares):
    alvo = titulares[3]["cpf"]
    try:
        plano = cifrada.find({"cpf": alvo}).explain()
    except Exception as exc:  # explain pode não ser suportado; o erro não pode vazar o valor
        assert alvo not in str(exc)
        return
    assert alvo not in json.dumps(plano, default=str)


def test_log_do_backend_nao_tem_plaintext(api, titulares, caplog):
    """Inclui o log DEBUG do PyMongo: o comando do cliente cifrado sai cifrado e
    a resposta é logada antes de o driver decifrar. O httpx é o lado do cliente
    de teste.

    A exceção documentada é o controle do DBA: o cliente comum manda o MESMO
    filtro, com o CPF que o "DBA" digitou, em claro — é o que um insider sem
    chave faria. Esse valor chega ao servidor (e ao profiler) porque o DBA o
    enviou, não porque a aplicação o vazou. O teste prova as duas coisas.
    """
    alvo = titulares[4]["cpf"]
    with caplog.at_level(logging.DEBUG):
        api.get("/demo/buscar", params={"cpf": alvo})
        api.get("/demo/buscar", params={"cpf": "abc"})
    id_claro = str(encryption.cliente_claro()._topology_settings._topology_id)
    id_cifrado = str(encryption.cliente_cifrado()._topology_settings._topology_id)
    do_backend = [r for r in caplog.records if not r.name.startswith("httpx")]
    do_cifrado = [r for r in do_backend if id_cifrado in r.getMessage()]
    assert any(r.name == "pymongo.command" for r in do_cifrado)
    assert all(alvo not in r.getMessage() for r in do_cifrado)
    vazados = [r for r in do_backend if alvo in r.getMessage()]
    assert vazados and all(id_claro in r.getMessage() for r in vazados)


def test_ne_e_in_sao_suportados_e_vao_cifrados(cifrada, titulares):
    """QE equality aceita $ne/$in/$nin — e o valor também sai cifrado."""
    alvo = titulares[5]["cpf"]
    _, enviado = encryption.executar_capturando(
        "find", "clientes", lambda: list(cifrada.find({"cpf": {"$in": [alvo]}}, {"_id": 1}).limit(1)))
    assert alvo.encode() not in bson.encode(enviado)
    assert cifrada.count_documents({"cpf": {"$ne": alvo}, "uf": "SP"}, limit=3) == 3


# ── Operadores que o QE não suporta: erro legível, sem plaintext ─────────────
@pytest.mark.parametrize("filtro", [
    {"cpf": {"$regex": "^999"}},
    {"cpf": {"$gt": "99900000000"}},
    {"salario": {"$gte": 2_000_000}},          # fora do max do encryptedFields
    {"salario": {"$gte": "5000"}},             # tipo errado em campo range
    {"cpf": 99943750162},                      # tipo errado em campo equality
    {"observacoes": "cliente desde a abertura da conta digital"},  # cifrado sem queries
])
def test_operador_nao_suportado_em_campo_cifrado_falha_legivel(cifrada, filtro):
    with pytest.raises(Exception) as erro:
        list(cifrada.find(filtro).limit(1))
    mensagem = str(erro.value)
    assert mensagem.strip()
    assert "99943750162" not in mensagem


def test_trecho_maior_que_strMaxQueryLength_e_recusado(cifrada):
    filtro = {"$expr": {"$encStrContains": {"input": "$email_substring", "substring": "ular0@ex"}}}
    with pytest.raises(Exception) as erro:
        list(cifrada.find(filtro).limit(1))
    assert "ular0@ex" not in str(erro.value)


def test_unicode_e_emoji_em_campo_de_prefixo_e_trecho(cifrada, clara):
    """Diacrítico-insensível e emoji: o servidor casa sem ver o texto."""
    email = "joão🙂ção@exemplo.invalid"
    doc = {"_id": ObjectId(), "nome": "Teste Unicode", "cpf": "99900000191", "email": email,
           "email_prefix": email, "email_suffix": email, "email_substring": email,
           "salario": 1000, "score_credito": 1, "observacoes": "x", "uf": "SP", "cidade": "São Paulo",
           "tenant_id": "banco-alfa", "faixa_salarial": "0-5k"}
    cifrada.insert_one(doc)
    try:
        ids = lambda f: {d["_id"] for d in cifrada.find(f, {"_id": 1})}  # noqa: E731
        assert doc["_id"] in ids({"$expr": {"$encStrStartsWith": {"input": "$email_prefix", "prefix": "joao"}}})
        assert doc["_id"] in ids({"$expr": {"$encStrContains": {"input": "$email_substring", "substring": "🙂çã"}}})
        bruto = clara.find_one({"_id": doc["_id"]})
        assert isinstance(bruto["email_prefix"], bson.Binary) and bruto["email_prefix"].subtype == 6
    finally:
        clara.delete_one({"_id": doc["_id"]})


def test_email_maior_que_strMaxLength_e_recusado_no_insert(cifrada, clara):
    longo = "a" * 41
    _id = ObjectId()
    try:
        with pytest.raises(Exception) as erro:
            cifrada.insert_one({"_id": _id, "email_substring": longo})
        assert longo not in str(erro.value)
    finally:
        clara.delete_one({"_id": _id})


# ── Concorrência ─────────────────────────────────────────────────────────────
def test_buscas_paralelas_nao_trocam_resultados(api, titulares):
    def buscar(t):
        corpo = api.get("/demo/buscar", params={"cpf": t["cpf"]}).json()
        return t["cpf"], corpo["aplicacao"]["documentos"][0]["cpf"], corpo["query_details"]["sent_to_server"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        respostas = list(pool.map(buscar, titulares * 3))
    assert all(pedido == achado for pedido, achado, _ in respostas)
    assert all(enviado is not None and enviado["find"] == "clientes" for *_, enviado in respostas)


def test_inserts_concorrentes_com_contention(cifrada, clara):
    """Mesmo CPF de várias threads: contention > 0 existe para isso."""
    ids = [ObjectId() for _ in range(24)]

    def inserir(_id):
        cifrada.insert_one({"_id": _id, "nome": "Concorrente", "cpf": "99900000272", "salario": 5000,
                            "uf": "SP", "tenant_id": "banco-alfa"})

    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(inserir, ids))
        assert cifrada.count_documents({"cpf": "99900000272"}) == len(ids)
    finally:
        clara.delete_many({"_id": {"$in": ids}})


# ── Cofre e cluster indisponíveis ────────────────────────────────────────────
@pytest.fixture
def config_trocada(monkeypatch):
    def trocar(**campos):
        nova = replace(settings_mod.settings, **campos)
        monkeypatch.setattr(encryption, "settings", nova)
        encryption.fechar_clientes()
        encryption.limpar_cache_deks()
        return nova
    yield trocar
    monkeypatch.undo()
    encryption.fechar_clientes()
    encryption.limpar_cache_deks()


def test_cofre_vazio_vira_502_legivel(api, config_trocada, titulares):
    config_trocada(key_vault_ns=f"{settings_mod.settings.mongo_db}.__keyVaultInexistente")
    resposta = api.get("/demo/buscar", params={"cpf": titulares[0]["cpf"]})
    assert resposta.status_code == 502
    assert "criar-cofre" in resposta.json()["detail"]["mensagem"]
    assert titulares[0]["cpf"] not in resposta.text


def test_cluster_inacessivel_responde_rapido_e_sem_host(api, config_trocada):
    config_trocada(mongo_uri="mongodb://127.0.0.1:1/", mongo_timeout_ms=300)
    resposta = api.get("/demo/buscar", params={"uf": "SP"})
    assert resposta.status_code == 502
    assert resposta.elapsed.total_seconds() < 5
    pronto = api.get("/health/ready")
    assert pronto.status_code == 503
