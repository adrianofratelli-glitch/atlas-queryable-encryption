from bson import Binary, ObjectId

from routers._comum import CABECALHO_BYTES, SUBTIPO_CIFRADO, erro_do_servidor, serializar


def test_binary_subtype_6_e_rotulado_como_cifrado():
    valor = Binary(b"\x01\x02\x03\x04" * 16, SUBTIPO_CIFRADO)
    saida = serializar(valor)
    assert saida["__cifrado__"] is True
    # O tamanho é informação: é ele que explica o overhead de storage do módulo 06.
    assert saida["bytes"] == 64
    assert len(saida["hex"]) == 32  # 16 bytes truncados


def test_amostra_vem_do_payload_e_nao_do_cabecalho():
    """Dois valores do MESMO campo compartilham os 17 primeiros bytes (tipo +
    UUID da DEK). Amostrar dali fazia ciphertexts distintos aparecerem iguais na
    tela — e o par plantado do módulo 02 provava o oposto do que deve provar."""
    cabecalho = bytes([14]) + b"\xaa" * 16
    a = serializar(Binary(cabecalho + b"\x11" * 40, SUBTIPO_CIFRADO))
    b = serializar(Binary(cabecalho + b"\x22" * 40, SUBTIPO_CIFRADO))
    assert a["chave"] == b["chave"]      # mesma DEK
    assert a["hex"] != b["hex"]          # ciphertexts distintos, visivelmente
    assert a["hex"] == "11" * 16
    assert CABECALHO_BYTES == 17


def test_binary_comum_nao_e_marcado_como_cifrado():
    assert serializar(Binary(b"abc", 0))["__cifrado__"] is False


def test_serializacao_e_recursiva():
    doc = {"_id": ObjectId(), "campos": [Binary(b"xy", SUBTIPO_CIFRADO)], "uf": "SP"}
    saida = serializar(doc)
    assert isinstance(saida["_id"], str)
    assert saida["campos"][0]["__cifrado__"] is True
    assert saida["uf"] == "SP"


def test_erro_do_servidor_preserva_a_mensagem_crua():
    # O módulo 04 depende disso: o valor da tela está em o erro vir do MongoDB,
    # não de um texto nosso.
    class Falha(Exception):
        code = 31_264

    detalhe = erro_do_servidor(Falha("Encrypted field cannot be used in $group"))
    assert detalhe["mensagem"] == "Encrypted field cannot be used in $group"
    assert detalhe["codigo"] == 31_264
