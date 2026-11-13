# ADR 0003 — KMS local na demo; rotação provada só no cofre de teste

**Status:** aceito · **Data:** 2026-11-12

## Contexto

QE aceita AWS KMS, Azure Key Vault, GCP KMS, KMIP e um provedor local (96 bytes em arquivo).
A demo precisa rodar em qualquer notebook, sem conta de nuvem, e o repositório é público.

## Decisão

- `QE_KMS_PROVIDER=local` na demo, com a chave mestra em `backend/secrets/` (modo 0600, fora
  do git e da imagem; montada por volume). `aws` continua suportado por configuração; Azure,
  GCP e KMIP ficam como texto, não como código.
- A tela rotula o KMS local como "não é para produção".
- A frase de reunião "rotação de CMK recifra as DEKs, não os campos" é **provada** por um teste
  live (`backend/tests/test_live_adversarial.py::test_rewrap_recifra_as_deks_e_nao_os_campos`):
  `rewrap_many_data_key` no cofre `*_test` com o KMS local troca o `keyMaterial` da DEK, mantém o
  `_id`, deixa o ciphertext do documento idêntico byte a byte, e a aplicação segue lendo.
- Nenhum teste ou script cria, rotaciona ou apaga chave em KMS de nuvem.

## Consequências

- A demo não depende de credencial de nuvem; a prova de rotação não toca a CMK de ninguém.
- Rotação real de CMK em AWS KMS (com role e `rewrap` para outra chave) fica como passo do
  cliente, documentado, não demonstrado.
