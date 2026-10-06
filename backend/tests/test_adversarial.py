"""Uso hostil da API, sem cluster: entradas inválidas, injeção, falha de driver.

A regra: entrada ruim vira 422 legível, falha do banco vira 502 legível, e nada
disso devolve plaintext, hostname do cluster ou o `full error` do driver.
"""

import logging
import threading
from dataclasses import replace

import pytest
from bson.binary import Binary
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

import encryption
import main
import settings as settings_mod
from routers import demo
from tests.test_demo import ColecaoFalsa


@pytest.fixture
def colecoes(monkeypatch):
    cifrada = ColecaoFalsa([{"_id": "1", "cpf": "99943750162"}])
    clara = ColecaoFalsa([])
    monkeypatch.setattr(demo, "_colecao", lambda cliente: cliente)
    monkeypatch.setattr(demo, "cliente_cifrado", lambda: cifrada)
    monkeypatch.setattr(demo, "cliente_claro", lambda: clara)
    return cifrada, clara


@pytest.fixture
def cliente():
    app = FastAPI()
    app.include_router(demo.router)
    return TestClient(app)


@pytest.mark.parametrize("cpf", [
    "abcdefghijk",            # 11 caracteres, zero dígitos: virava busca por ""
    "999abc45678",            # mistura
    '{"$gt": ""}xx',          # operador como texto
    "9994375016​2",      # zero-width no meio
    "٩٩٩٤٣٧٥٠١٦٢",            # dígitos arábicos: isdigit() aceita, o seed não tem
    "999437501622",           # 12 dígitos
])
def test_cpf_invalido_e_422_sem_tocar_no_banco(colecoes, cliente, cpf):
    cifrada, clara = colecoes
    resposta = cliente.get("/demo/buscar", params={"cpf": cpf})
    assert resposta.status_code == 422
    assert cifrada.filtros == [] and clara.filtros == []


def test_cpf_com_pontuacao_continua_valido(colecoes, cliente):
    assert cliente.get("/demo/buscar", params={"cpf": "999.437.501-62"}).status_code == 200


@pytest.mark.parametrize("params", [
    {"cpf[$ne]": "x"},                          # operador em query string é ignorado → sem critério
    {"salario_min": "1e3"},
    {"salario_min": "abc"},
    {"salario_min": -1},
    {"salario_max": 1_000_001},                 # acima do max do encryptedFields
    {"salario_min": 20_000, "salario_max": 10_000},
    {"uf": "S"},
    {"uf": "1A"},
    {"uf": "çã"},
    {"uf": "😀"},
    {"uf": "$w"},
    {"uf": "SP", "limite": 0},
    {"uf": "SP", "limite": 11},
])
def test_parametros_hostis_viram_422(colecoes, cliente, params):
    cifrada, _ = colecoes
    assert cliente.get("/demo/buscar", params=params).status_code == 422
    assert cifrada.filtros == []


def test_uf_minuscula_vira_maiuscula(colecoes, cliente):
    cifrada, _ = colecoes
    cliente.get("/demo/buscar", params={"uf": "sp"})
    assert cifrada.filtros[0] == {"uf": "SP"}


@pytest.mark.parametrize("tipo", ["", "prefixo|sufixo", "prefixo ", "$where", "../etc"])
def test_busca_string_so_aceita_opcoes_fechadas(cliente, tipo):
    assert cliente.get("/demo/buscar-string", params={"tipo": tipo}).status_code == 422


def test_query_string_gigante_e_recusada(colecoes, cliente):
    assert cliente.get("/demo/buscar", params={"cpf": "9" * 60_000}).status_code == 422


def test_falha_do_driver_vira_502_sem_host_nem_full_error(monkeypatch, cliente):
    class Quebrada(ColecaoFalsa):
        def limit(self, n):
            raise ServerSelectionTimeoutError(
                "ac-abc-shard-00-01.xyz12.mongodb.net:27017: timed out, full error: {'ok': 0, '$clusterTime': 1}"
            )

    quebrada = Quebrada([])
    monkeypatch.setattr(demo, "_colecao", lambda c: c)
    monkeypatch.setattr(demo, "cliente_cifrado", lambda: quebrada)
    monkeypatch.setattr(demo, "cliente_claro", lambda: quebrada)
    resposta = cliente.get("/demo/buscar", params={"cpf": "99943750162"})
    assert resposta.status_code == 502
    corpo = resposta.text
    assert "mongodb.net" not in corpo and "full error" not in corpo and "clusterTime" not in corpo
    assert resposta.json()["detail"]["tipo"] == "ServerSelectionTimeoutError"


def test_access_log_nao_grava_query_string():
    registro = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5", "GET", "/demo/buscar?cpf=99943750162", "1.1", 200), None,
    )
    main.SemQueryStringNoAccessLog().filter(registro)
    assert "99943750162" not in registro.getMessage()
    assert "/demo/buscar?<omitida>" in registro.getMessage()


def test_comando_enviado_nao_tem_plaintext_nem_schema():
    comando = {
        "find": "clientes",
        "filter": {"cpf": {"$eq": Binary(b"\x10" + b"\x00" * 200, 6)}},
        "encryptionInformation": {"schema": {"keyId": Binary(b"\x00" * 16, 4)}},
        "lsid": {"id": Binary(b"\x00" * 16, 4)},
        "$db": "x",
        "limit": 5,
    }
    resumo = encryption.resumir_comando_enviado(comando)
    assert resumo == {"find": "clientes", "filter": {"cpf": {"$eq": "<Binary subtype 6 · 201 B · ciphertext>"}},
                      "limit": 5}


def test_captura_de_comando_e_isolada_por_thread():
    """Duas buscas simultâneas não podem trocar o comando capturado uma da outra."""
    ouvinte = encryption.CapturaDeComando()

    class Evento:
        def __init__(self, valor):
            self.command_name = "find"
            self.command = {"find": "clientes", "filter": {"v": valor}}

    resultados, barreira = {}, threading.Barrier(8)

    def rodar(i):
        def operacao():
            barreira.wait()
            ouvinte.started(Evento(i))
            return i
        resultados[i] = encryption.executar_capturando("find", "clientes", operacao)

    threads = [threading.Thread(target=rodar, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(resultados[i][1]["filter"]["v"] == i for i in range(8))


def test_captura_ignora_find_no_cofre():
    ouvinte = encryption.CapturaDeComando()

    class Evento:
        command_name = "find"
        command = {"find": "__keyVault", "filter": {}}

    _, comando = encryption.executar_capturando("find", "clientes", lambda: ouvinte.started(Evento()))
    assert comando is None


@pytest.mark.parametrize("banco,cofre,permitido,recusa", [
    ("demo", "demo.__keyVault", "", True),
    ("demo_test", "demo_test.__keyVault", "", False),
    ("demo_test", "demo.__keyVault", "", True),          # banco de teste, cofre da demo
    ("demo", "demo.__keyVault", "1", False),
    ("demo", "demo.__keyVault", "true", True),            # só "1" libera
])
def test_guarda_de_escrita_no_banco_da_demo(monkeypatch, banco, cofre, permitido, recusa):
    monkeypatch.setenv("ALLOW_DEMO_DB_WRITE", permitido)
    config = replace(settings_mod.settings, mongo_db=banco, key_vault_ns=cofre)
    if recusa:
        with pytest.raises(SystemExit, match="banco da demo"):
            settings_mod.exigir_permissao_de_escrita("teste", config)
    else:
        settings_mod.exigir_permissao_de_escrita("teste", config)


def test_seeds_de_teste_nao_sobrescrevem_os_da_demo():
    assert settings_mod.arquivo_seeds("cofre_test") != settings_mod.arquivo_seeds("cofre")
    assert settings_mod.arquivo_seeds("cofre_test") != settings_mod.SEEDS_LEGADO


def test_mensagem_segura_remove_uri_host_e_full_error():
    from routers._comum import mensagem_segura
    # Montada por concatenação para não disparar o secret scanning do GitHub.
    uri = "mongodb" + "+srv://" + "usuario:senha" + "@cluster0.abcde.mongodb.net/db"
    texto = mensagem_segura(f"falhou em {uri} e ac-1-shard-00-00.abcde.mongodb.net:27017, full error: {{'ok': 0}}")
    assert "senha" not in texto and "mongodb.net" not in texto and "full error" not in texto
    assert len(mensagem_segura("x" * 5000)) <= 401
