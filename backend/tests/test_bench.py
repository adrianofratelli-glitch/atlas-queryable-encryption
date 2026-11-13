"""Partes puras do `scripts/bench_qe.py`: percentil e termos das buscas de string.

O bench só roda contra cluster; estas funções decidem O QUE ele reporta, então
são testadas sem cluster. Um p95 que pega a posição errada ou um termo fora de
`strMinQueryLength`/`strMaxQueryLength` faz o README citar número falso.
"""

import importlib.util
import random
import sys
from pathlib import Path

import pytest
from bson import Binary

import encryption
from routers.demo import BUSCAS_STRING
from settings import settings

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("bench_qe", RAIZ / "scripts" / "bench_qe.py")
bench = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("bench_qe", bench)
_spec.loader.exec_module(bench)


class CofreFalso:
    def find_one(self, filtro):
        return {"_id": Binary(filtro["keyAltNames"].encode()[:16].ljust(16, b"\0"), 4)}

    def count_documents(self, _filtro, **_kw):
        return 1


@pytest.fixture
def campos(monkeypatch):
    monkeypatch.setattr(encryption, "key_vault_collection", CofreFalso)
    encryption.limpar_cache_deks()
    ns = f"{settings.mongo_db}.{encryption.COLECAO_CIFRADA}"
    yield {c["path"]: c for c in encryption.encrypted_fields()[ns]["fields"]}
    encryption.limpar_cache_deks()


def test_percentil_nearest_rank():
    amostras = list(range(1, 31))  # 30 inserts: p95 é o 29º valor
    assert bench.percentil(amostras, 95) == 29
    assert bench.percentil(list(range(1, 101)), 95) == 95
    assert bench.percentil([7.0], 95) == 7.0
    assert bench.percentil([3, 1, 2], 50) == 2
    with pytest.raises(ValueError):
        bench.percentil([], 95)


def test_resumo_usa_mediana_e_p95():
    r = bench._resumo([10.0, 20.0, 30.0, 40.0])
    assert r == {"n": 4, "p50_ms": 25.0, "p95_ms": 40.0}


@pytest.mark.parametrize("modo", ["prefixo", "sufixo", "trecho"])
def test_termos_respeitam_limites_do_schema(campos, modo):
    item = BUSCAS_STRING[modo]
    consulta = campos[item["campo"]]["queries"]
    termos = bench.termos_de_string(modo, item["valor"], 200, random.Random(7))
    assert len(termos) == 200
    for termo in termos:
        assert consulta["strMinQueryLength"] <= len(termo) <= consulta["strMaxQueryLength"], termo


@pytest.mark.parametrize("modo", ["prefixo", "sufixo", "trecho"])
def test_todo_termo_existe_na_massa_do_seed(modo):
    """Termo que não acha nada mediria um caminho diferente (lista vazia)."""
    emails = [f"titular{i}@exemplo.invalid" for i in range(5000)]
    item = BUSCAS_STRING[modo]
    for termo in set(bench.termos_de_string(modo, item["valor"], 200, random.Random(7))):
        if modo == "prefixo":
            assert any(e.startswith(termo) for e in emails), termo
        elif modo == "sufixo":
            assert any(e.endswith(termo) for e in emails), termo
        else:
            assert any(termo in e for e in emails), termo


def test_storage_soma_familia_cifrada_inclusive_ecoc_em_compactacao():
    tamanhos = {"clientes": 100, "enxcol_.clientes.esc": 10, "enxcol_.clientes.ecoc": 1,
                "enxcol_.clientes.ecoc.compact": 40}

    class Db:
        def list_collection_names(self):
            return [*tamanhos, "bench_claro", "enxcol_.outra.esc", "__keyVault"]

        def command(self, _cmd, nome):
            base = tamanhos[nome]
            return {"count": 1, "size": base, "storageSize": base // 2, "totalIndexSize": 4}

    r = bench.storage(Db(), "clientes")
    assert set(r["por_colecao"]) == set(tamanhos)
    assert r["logico"] == 151 + 16
    assert r["disco"] == 50 + 5 + 0 + 20 + 16
    assert bench.razao(10, 0) is None
