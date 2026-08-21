"""O único endpoint da demo. Se ele mentir, a PoV inteira mente.

Os testes aqui protegem três coisas que quebram sem fazer barulho: que o filtro
por campo cifrado seja montado como o driver espera, que os dois clientes recebam
exatamente o mesmo filtro, e que a resposta nunca prometa "campo cifrado" quando
o filtro foi por campo em claro — é essa etiqueta que a tela usa para explicar
por que o painel do DBA voltou vazio.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import demo


class ColecaoFalsa:
    """Registra o filtro que recebeu e devolve o que mandarem."""

    def __init__(self, documentos):
        self.documentos = documentos
        self.filtros = []

    def find(self, filtro, projecao=None):
        self.filtros.append(filtro)
        return self

    def sort(self, *_a, **_kw):
        return self

    def limit(self, n):
        return list(self.documentos)[:n]

    def __iter__(self):
        return iter(self.documentos)


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
    """Pelo HTTP, não chamando a função: é o único jeito de os defaults de
    `Query` valerem, e é assim que o frontend chama."""
    app = FastAPI()
    app.include_router(demo.router)
    return TestClient(app)


def test_igualdade_monta_filtro_e_marca_campo_cifrado(colecoes, cliente):
    cifrada, _ = colecoes
    resposta = cliente.get("/demo/buscar", params={"cpf": "999.437.501-62"}).json()

    # A pontuação tem que sumir: o valor cifrado no seed são só dígitos, e um
    # ponto a mais faz a busca voltar vazia sem erro nenhum.
    assert cifrada.filtros == [{"cpf": "99943750162"}]
    assert resposta["campo_cifrado"] is True
    assert resposta["aplicacao"]["encontrados"] == 1
    assert resposta["dba"]["encontrados"] == 0


def test_os_dois_clientes_recebem_o_mesmo_filtro(colecoes, cliente):
    """O contraste só vale se for a mesma query. Filtros divergentes
    transformariam a evidência em coincidência."""
    cifrada, clara = colecoes
    cliente.get("/demo/buscar", params={"salario_min": 8000, "salario_max": 15000})
    assert cifrada.filtros == clara.filtros


def test_faixa_vira_gte_lte(colecoes, cliente):
    cifrada, _ = colecoes
    cliente.get("/demo/buscar", params={"salario_min": 8000, "salario_max": 15000})
    assert cifrada.filtros == [{"salario": {"$gte": 8000, "$lte": 15000}}]


def test_faixa_aberta_de_um_lado_so(colecoes, cliente):
    cifrada, _ = colecoes
    cliente.get("/demo/buscar", params={"salario_min": 8000})
    assert cifrada.filtros == [{"salario": {"$gte": 8000}}]


def test_uf_nao_e_campo_cifrado(colecoes, cliente):
    """`uf` é o controle do experimento: os dois lados acham os mesmos
    documentos. Marcá-lo como cifrado faria a tela explicar um zero que não
    aconteceu."""
    resposta = cliente.get("/demo/buscar", params={"uf": "sp"}).json()
    assert resposta["campo_cifrado"] is False
    assert "claro" in resposta["leitura"]


def test_uf_e_normalizada(colecoes, cliente):
    cifrada, _ = colecoes
    cliente.get("/demo/buscar", params={"uf": "sp"})
    assert cifrada.filtros == [{"uf": "SP"}]


def test_busca_sem_criterio_e_recusada(colecoes, cliente):
    assert cliente.get("/demo/buscar").status_code == 422


def test_par_ausente_falha_em_vez_de_afirmar_o_contrario(monkeypatch, cliente, tmp_path):
    """O modo de falha perigoso: sem os dois documentos, o conjunto de hexes tem
    tamanho 0 ou 1, `distintos` vira falso e a tela afirma "ciphertexts iguais" —
    exatamente o oposto do que a PoV existe para provar."""
    seeds = tmp_path / "demo_seeds.json"
    seeds.write_text('{"cpf_repetido": ["6a88642d52a60188aa9827fb", "6a88642d52a60188aa9827fc"]}')
    monkeypatch.setattr(demo, "SEEDS", seeds)
    vazia = ColecaoFalsa([])
    monkeypatch.setattr(demo, "_colecao", lambda _cliente: vazia)
    monkeypatch.setattr(demo, "cliente_cifrado", lambda: vazia)
    monkeypatch.setattr(demo, "cliente_claro", lambda: vazia)

    resposta = cliente.get("/demo/par-repetido")
    assert resposta.status_code == 503
    assert "seed" in resposta.json()["detail"].lower()


def test_exemplos_nao_repete_cpf_do_par_plantado(monkeypatch, cliente):
    """O par plantado divide o mesmo CPF. Oferecer os dois como opções distintas
    faria a mesma busca trazer dois titulares antes de a tela explicar por quê."""
    docs = [
        {"_id": "1", "nome": "Natália", "cpf": "99925626170", "salario": 16119, "uf": "CE"},
        {"_id": "2", "nome": "Helena", "cpf": "99925626170", "salario": 19174, "uf": "MG"},
        {"_id": "3", "nome": "Rafael", "cpf": "99944894613", "salario": 13586, "uf": "PR"},
    ]
    colecao = ColecaoFalsa(docs)
    monkeypatch.setattr(demo, "_colecao", lambda _c: colecao)
    monkeypatch.setattr(demo, "cliente_cifrado", lambda: colecao)

    titulares = cliente.get("/demo/exemplos").json()["titulares"]
    assert [t["cpf"] for t in titulares] == ["99925626170", "99944894613"]


def test_exemplos_respeita_a_quantidade_pedida(monkeypatch, cliente):
    # A folga que compensa o par plantado não pode vazar para a resposta.
    docs = [{"_id": str(i), "nome": f"T{i}", "cpf": f"999{i:08d}", "salario": 1, "uf": "SP"}
            for i in range(10)]
    colecao = ColecaoFalsa(docs)
    monkeypatch.setattr(demo, "_colecao", lambda _c: colecao)
    monkeypatch.setattr(demo, "cliente_cifrado", lambda: colecao)

    assert len(cliente.get("/demo/exemplos", params={"quantos": 4}).json()["titulares"]) == 4


def test_exemplos_exclui_o_par_plantado_da_consulta(monkeypatch, cliente, tmp_path):
    """Oferecer metade do par como titular padrão faz a primeira busca da demo
    devolver dois documentos para um CPF — antes de a tela ter explicado o par.
    Parece defeito, e é a primeira impressão que o cliente tem."""
    seeds = tmp_path / "demo_seeds.json"
    seeds.write_text('{"cpf_repetido": ["6a88642d52a60188aa9827fb", "6a88642d52a60188aa9827fc"]}')
    monkeypatch.setattr(demo, "SEEDS", seeds)
    colecao = ColecaoFalsa([{"_id": "9", "nome": "T", "cpf": "99911122233", "salario": 1, "uf": "SP"}])
    monkeypatch.setattr(demo, "_colecao", lambda _c: colecao)
    monkeypatch.setattr(demo, "cliente_cifrado", lambda: colecao)

    cliente.get("/demo/exemplos")
    assert "_id" in colecao.filtros[0]
    assert len(colecao.filtros[0]["_id"]["$nin"]) == 2
