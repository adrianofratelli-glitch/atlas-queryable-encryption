# ADR 0002 — Uma DEK por campo, contention e campos de string separados

**Status:** aceito · **Data:** 2026-11-12 (registra o schema vigente desde 2026-10-06)

## Contexto

`encryptedFields` é imutável depois do `create_collection`: mudar `queryType`, `contention`,
limites ou adicionar campo exige dropar e recriar a coleção (e o dataset). Cada campo QE
aceita um tipo de query só.

## Decisão

- **Uma DEK por campo por coleção** (`nome_dek()`): o próprio QE recusa `keyId` repetido
  (`Duplicate key ids are not allowed`, code 6338401).
- `cpf` e `email`: `equality`, `contention` = `QE_CONTENTION_FACTOR` (8).
- `salario` e `score_credito`: `range` (GA no 8.0) com metade do contention e `min`/`max` por campo.
- O mesmo e-mail em três campos — `email_prefix` (3–20), `email_suffix` (3–30) e
  `email_substring` (`strMaxLength` 40, consulta 3–6) —, todos `caseSensitive: false` e
  `diacriticSensitive: false`. Prefixo, sufixo e substring são GA no MongoDB 9.0
  (`$encStrStartsWith`/`EndsWith`/`Contains`); no 8.2 eram Public Preview com nomes
  `*Preview`, incompatíveis com o GA.
- `observacoes`: cifrado e **não** consultável — não gera metadados.

## Consequências (medidas)

- O campo de substring domina o custo: ~207 entradas de metadados por titular na
  `enxcol_.clientes.ecoc` antes do compact, e ciphertext de 9–14 KB por valor (contra
  ~140 B do CPF). Números em [ADR 0004](0004-bench-storage-e-compactacao.md).
- O tamanho do ciphertext de substring varia com o comprimento do texto (9.262 B × 14.270 B
  na mesma tela): é vazamento de tamanho, coerente com a documentação de leakage de range/texto.
- Os exemplos da tela casam vários valores distintos (111, 500 e 50 titulares), para a
  busca parcial não parecer igualdade; o total vem de `count_documents` com o mesmo filtro cifrado.
