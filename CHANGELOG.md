# Changelog

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
