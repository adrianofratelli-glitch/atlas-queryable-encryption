import seed_data


def test_seed_e_deterministico():
    a, par_a = seed_data.gerar(50)
    b, par_b = seed_data.gerar(50)
    # _id é gerado por ObjectId e muda; o conteúdo não pode mudar.
    campos = ("nome", "cpf", "salario", "score_credito", "uf", "faixa_salarial")
    assert [{c: d[c] for c in campos} for d in a] == [{c: d[c] for c in campos} for d in b]
    assert len(par_a) == len(par_b) == 2


def test_par_de_cpf_repetido_e_plantado():
    # Sem plantar, achar um par assim no palco é sorte.
    documentos, par = seed_data.gerar(50)
    assert documentos[0]["cpf"] == documentos[1]["cpf"]
    assert par == [documentos[0]["_id"], documentos[1]["_id"]]


def test_cpf_tem_digito_verificador_valido():
    documentos, _ = seed_data.gerar(200)
    for documento in documentos:
        cpf = documento["cpf"]
        assert len(cpf) == 11 and cpf.isdigit()
        base = [int(d) for d in cpf[:9]]
        for esperado in cpf[9:]:
            peso = len(base) + 1
            soma = sum(d * (peso - i) for i, d in enumerate(base))
            resto = (soma * 10) % 11
            digito = 0 if resto == 10 else resto
            assert digito == int(esperado)
            base.append(digito)


def test_cpf_fica_em_faixa_nao_emitida():
    # Ele vai aparecer em screenshot; ele não pode pertencer a ninguém.
    documentos, _ = seed_data.gerar(200)
    assert all(documento["cpf"].startswith("999") for documento in documentos)


def test_faixa_salarial_cobre_toda_a_escala():
    assert seed_data.faixa_salarial(1_500) == "0-5k"
    assert seed_data.faixa_salarial(9_999) == "5k-10k"
    assert seed_data.faixa_salarial(12_400) == "10k-15k"
    assert seed_data.faixa_salarial(90_000) == "40k+"


def test_salarios_caem_dentro_da_faixa_declarada():
    # Valor fora do min/max de `encryptedFields` é rejeitado na escrita.
    documentos, _ = seed_data.gerar(500)
    assert all(0 <= d["salario"] <= 1_000_000 for d in documentos)
    assert all(0 <= d["score_credito"] <= 1_000 for d in documentos)


def test_ha_massa_nas_faixas_que_a_demo_consulta():
    # Uma faixa que devolve zero documento no palco parece falha.
    documentos, _ = seed_data.gerar(1_000)
    na_faixa = [d for d in documentos if 8_000 <= d["salario"] <= 15_000]
    assert len(na_faixa) > 100


def test_dois_tenants_para_o_modulo_de_shredding():
    documentos, _ = seed_data.gerar(50)
    assert len({d["tenant_id"] for d in documentos}) == 2
