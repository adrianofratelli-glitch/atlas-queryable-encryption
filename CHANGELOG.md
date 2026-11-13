# Changelog

## Unreleased

- Busca parcial: exemplos que casam vários e-mails distintos (prefixo `titular12` = 111, sufixo `7@exemplo.invalid` = 500, trecho `42@exe` = 50) no lugar de `titular0`/`ular0@`, que casavam um documento só; a resposta traz `aplicacao.total` (`count_documents` com o mesmo filtro cifrado, fail-open) e a tela mostra "N documentos casam no total".
- Painel do DBA na mesma ordem da aplicação (`na_ordem_de`) na leitura por `_id`: o lado a lado volta a casar linha a linha.
- Destaque do trecho ignora maiúsculas/minúsculas, como o `caseSensitive: false` do schema.
- Rótulo GA no MongoDB 9.0 para prefixo/sufixo/substring (preflight, tela, README, briefing).
- `scripts/bench_qe.py`: mede prefixo/sufixo/trecho, storage lógico × em disco por coleção (inclui `ecoc.compact`), `compactStructuredEncryptionData` por cliente cifrado dedicado sem timeout de socket (antes e depois), p95 por posto mais próximo, prova de rede também do trecho, ambiente registrado.
- Testes: `frontend/tests/` (`npm test`, node:test, no CI), `backend/tests/test_bench.py`, live com totais exatos, caixa, ordem e rewrap de DEK no cofre `*_test` (KMS local).
- ADRs 0001–0004 em `docs/adr/`.
- Atualiza dependências compatíveis e pisos de segurança; alinha metadados de versão entre aplicação e frontend.

## 1.1.1 — 2026-10-09

- Tabela "Alternativas" (UI e README): pgcrypto deixa de ser apresentado como incapaz de filtrar. O PostgreSQL filtra decifrando no servidor (`pgp_sym_decrypt` no `WHERE`), com a chave na sessão; QE filtra sobre ciphertext sem o servidor receber chave nem plaintext. A diferença é a fronteira de confiança, com links para a doc oficial de pgcrypto e de Queryable Encryption. "Cifra randomizada na aplicação" virou linha própria.
- Docstrings de `routers/demo.py` sem a generalização "pgcrypto determinístico" (as funções PGP usam prefixo aleatório; só as raw `encrypt()` têm IV zero por padrão).
- `backend/tests/test_tese_alternativas.py` impede a afirmação falsa de voltar.

## 1.1.0 — 2026-10-06

- Prova de rede: o drawer "Ver query / comando que chegou ao servidor" mostra o `find` capturado por `CommandListener` depois da auto-encryption, com o valor buscado como `Binary(subtype 6)`; o filtro em claro não é mais exibido.
- Reset único `scripts/reset_demo.py` (cofre, DEKs, coleção com `encryptedFields`, dados, índices e verificação) e guarda `ALLOW_DEMO_DB_WRITE=1` em todo script que escreve fora de banco `*_test`.
- Metadados do seed por banco (`demo_seeds.<QE_DB>.json`): o seed de teste não invalida mais o par plantado da demo.
- Access log sem query string (o CPF buscado não vai mais para o log do backend).
- Entradas hostis viram 422 legível; erros do driver saem sem `full error`, URI ou hostname do Atlas.
- `scripts/bench_qe.py`: overhead medido contra cópia em claro indexada e prova em BSON de que o CPF não sai em claro.
- Suites `test_adversarial.py` (sem cluster) e `test_live_adversarial.py` (cluster real, banco `_test`).
- Dependências: `pymongo` 4.18.2 (4 advisories), `source-map-js` 1.2.2 (GHSA-68fv-2mgg-jv7q).
- UI: ciphertext não vaza do painel em 360 px; componente `Bloco` removido (sem uso).

## 1.0.x — anteriores

- UI: três cards independentes (igualdade, faixa/UF, texto parcial); o painel do DBA mostra o zero do filtro e a leitura por `_id` como `Binary(subtype 6)`; busca por string exibe o campo buscado e destaca o trecho casado.
- API: `/demo/buscar` devolve `dba.origem`; `/demo/buscar-string` devolve `campo`, `valor`, `modo` e `limite`.
- UI: layout MongoDB 2026 "Dark Stage v4" (tokens mais escuros, Special Gothic / Source Code Pro locais, motivos de escada e grade, movimento escalonado).

## 1.0.0 (2026-09-30)

First public release.

- Repository rebuilt with a clean, single-commit history.
- English README and repository description, with screenshots captured against a real Atlas cluster.
- MIT license.
- Internal notes, presentation decks, test-output snapshots, and tooling configuration removed from the repository.
