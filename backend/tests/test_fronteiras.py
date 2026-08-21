"""O módulo 04 é o que compra credibilidade para o resto.

Estes testes garantem duas coisas que é fácil quebrar sem perceber: que toda
tentativa realmente executa (nada de mensagem escrita à mão) e que o catálogo
não encolhe silenciosamente.
"""

from routers import fronteiras

ESPERADAS = {"sort", "regex", "search", "group", "lookup", "indice", "inc"}


def test_catalogo_completo():
    assert set(fronteiras.TENTATIVAS) == ESPERADAS


def test_toda_tentativa_tem_razao_em_uma_frase():
    # É a razão que o arquiteto do cliente vai repetir para o time depois.
    for chave, (descricao, comando, razao, fn) in fronteiras.TENTATIVAS.items():
        assert descricao and comando and razao, chave
        assert callable(fn), chave
        assert len(razao) < 190, chave


def test_tentar_registra_a_falha_sem_traduzir():
    def falhar():
        raise RuntimeError("Encrypted field cannot be used in $group")

    resultado = fronteiras._tentar("x", "y", "z", falhar)
    assert resultado["funcionou"] is False
    assert resultado["erro"]["mensagem"] == "Encrypted field cannot be used in $group"


def test_sort_e_marcado_como_falha_silenciosa():
    """O pior caso do módulo não é o erro: é a operação que não falha.

    `sort` sobre campo cifrado ordena por ciphertext e devolve ordem sem sentido
    sem aviso nenhum. A tela precisa distinguir isso de um sucesso.
    """
    silencioso = {"__silenciosa__": True, "ordem_devolvida": [3, 1, 2], "esta_ordenada": False}
    resultado = fronteiras._tentar("x", "y", "z", lambda: silencioso)
    assert resultado["funcionou"] is True
    assert resultado["silenciosa"] is True


def test_tentar_registra_o_sucesso():
    # Sucesso e falha são os dois resultados válidos: se um limite deixar de
    # existir numa versão nova do servidor, a tela precisa mostrar isso.
    resultado = fronteiras._tentar("x", "y", "z", lambda: [1, 2])
    assert resultado["funcionou"] is True
    assert resultado["silenciosa"] is False
    assert resultado["erro"] is None
