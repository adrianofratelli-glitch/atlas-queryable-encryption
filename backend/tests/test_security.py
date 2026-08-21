"""Guarda de mutação — mesmo contrato do resto do portfólio.

Nesta PoV o `no-store` deixa de ser higiene e vira requisito: várias respostas
carregam CPF e salário decifrados, e nenhuma delas pode entrar em cache de proxy.
"""

import dataclasses

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import security
from security import ApiHardeningMiddleware, MutationGuardMiddleware


@pytest.fixture
def app():
    aplicacao = FastAPI()
    aplicacao.add_middleware(ApiHardeningMiddleware)
    aplicacao.add_middleware(MutationGuardMiddleware)

    @aplicacao.get("/leitura")
    def leitura():
        return {"ok": True}

    @aplicacao.post("/mutacao")
    def mutacao():
        return {"ok": True}

    return aplicacao


def _com(monkeypatch, **campos):
    """`Settings` é uma dataclass congelada de propósito: a configuração é lida
    uma vez no boot e não muda em runtime. Para o teste, troque o objeto inteiro."""
    monkeypatch.setattr(security, "settings", dataclasses.replace(security.settings, **campos))


def test_leitura_passa_sem_token(app):
    assert TestClient(app).get("/leitura").status_code == 200


def test_resposta_nunca_entra_em_cache(app):
    resposta = TestClient(app).get("/leitura")
    assert resposta.headers["Cache-Control"] == "no-store"
    assert resposta.headers["X-Content-Type-Options"] == "nosniff"
    assert resposta.headers["X-Frame-Options"] == "DENY"


def test_origem_desconhecida_e_recusada(app):
    resposta = TestClient(app).post("/mutacao", headers={"Origin": "http://exemplo.invalid"})
    assert resposta.status_code == 403


def test_token_errado_e_recusado(app, monkeypatch):
    _com(monkeypatch, demo_admin_token="token-certo")
    resposta = TestClient(app).post("/mutacao", headers={"X-Demo-Token": "token-errado"})
    assert resposta.status_code == 401


def test_token_certo_passa(app, monkeypatch):
    _com(monkeypatch, demo_admin_token="token-certo")
    resposta = TestClient(app).post("/mutacao", headers={"X-Demo-Token": "token-certo"})
    assert resposta.status_code == 200


def test_corpo_grande_e_recusado(app, monkeypatch):
    _com(monkeypatch, max_request_bytes=10)
    resposta = TestClient(app).post("/mutacao", json={"campo": "x" * 100})
    assert resposta.status_code == 413
