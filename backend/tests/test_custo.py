from routers import custo


def test_percentis_ordenam_antes_de_cortar():
    amostras = [10.0, 1.0, 5.0, 100.0, 3.0]
    saida = custo._percentis(amostras)
    assert saida["n"] == 5
    assert saida["p50"] == 5.0
    assert saida["p95"] == 100.0


def test_percentis_de_lista_vazia_nao_estoura():
    assert custo._percentis([])["n"] == 0


def test_documento_de_benchmark_respeita_a_faixa_declarada():
    # Valor fora do min/max de `encryptedFields` é rejeitado na escrita, e um
    # benchmark que falha no meio não produz número nenhum.
    for indice in (0, 1, 499, 4_999):
        doc = custo._documento(indice)
        assert 0 <= doc["salario"] <= 1_000_000
        assert 0 <= doc["score_credito"] <= 1_000
        assert doc["benchmark"] is True
