# Mapa do código — atlas-queryable-encryption

> Também conhecida como: **Queryable Encryption**. Portas: frontend 5300 / backend 8300. Em uma frase: o mesmo filtro sai por dois clientes contra a mesma coleção (a aplicação, com auto-encryption, acha o documento; o "DBA", com cliente comum, recebe `Binary(subtype 6)` e zero resultados), provando que o servidor busca sem conseguir ler o dado.

Detalhes de arquitetura, queries e telas já estão em [briefing/architecture.md](briefing/architecture.md), [briefing/queries.md](briefing/queries.md) e [briefing/ui-flows.md](briefing/ui-flows.md). Este mapa só aponta onde abrir.

## 1. Árvore anotada

```
backend/
  main.py             app FastAPI: middlewares, handlers de erro, /, /health/*, /preflight, /stats
  settings.py         lê as env vars uma vez (dataclass Settings); trava de escrita em bancos que não terminam em _test
  encryption.py       o coração: cliente_cifrado(), cliente_claro(), mapa encryptedFields, cofre de DEKs, captura do comando enviado
  security.py         MutationGuardMiddleware (mutação só de localhost/token) e ApiHardeningMiddleware (headers, limite de corpo)
  seed_data.py        gera dados sintéticos e grava pelo cliente cifrado; cria a coleção cifrada
  routers/
    demo.py           TODAS as rotas /demo/* (buscar, buscar-string, exemplos, par-repetido) + preflight_checks()
    _comum.py         serializa Binary(6) para a tela e limpa mensagem de erro do servidor (sem host/URI)
  tests/              pytest sem cluster (Mongo é stub), mais um teste live opcional
frontend/
  src/App.jsx         a tela inteira (uma página só, sem rotas)
  src/lib/apresentacao.js  regras puras do que a tela afirma (legendas, destaque do trecho, máscara, total da busca parcial)
  tests/              node --test das regras de apresentação e do contrato tela × backend (npm test)
  src/components/     Cifra.jsx (hex do ciphertext), Documento.jsx (documento com ordem fixa), QueryDetails.jsx (comando que chegou ao servidor)
  src/hooks/useApi.js fetch com timeout e evento de erro global; manda X-Demo-Token se houver
  vite.config.js      porta 5300 e proxy /api -> backend 8300
scripts/
  reset_demo.py       reset único: limpa, recria cofre/DEKs/coleção, semeia, cria índices e verifica
  criar-cofre.py      índice único do keyVault + uma DEK por campo cifrado
  limpar-cofre.py     dropa clientes, enxcol_.* e (opcional) o cofre
  gerar-master-key.py chave mestra local (96 bytes, fora do git)
  instalar-crypt-shared.sh  baixa a biblioteca crypt_shared para backend/lib/
  bench_qe.py         mede overhead de QE x coleção em claro, buscas de string e storage antes/depois do compact (só em banco *_test)
start.sh              sobe backend (8300) e frontend (5300)
docs/briefing/        architecture, queries, ui-flows
docs/adr/             decisões; docs/screenshots, docs/material: apoio
```

Não há `frontend/src/pages/`: a tela é `frontend/src/App.jsx`.

## 2. "Apertei o botão X, o que roda?"

Todas as chamadas passam por `useApi.js` (`fetch('/api' + rota)`; o Vite remove `/api` e encaminha ao 8300).

| Tela / ação | Componente | Chamada HTTP | Handler | Função de negócio | Onde toca o MongoDB |
|---|---|---|---|---|---|
| Abrir a página: selo "pré-voo" | `App.jsx:45` `SeloPreflight` | `GET /preflight` | `backend/main.py:124` `preflight` (-> `_preflight_sem_cache` :146, cache de 8 s) | `routers/demo.py::preflight_checks` (:400) e `encryption.py::readiness` (:430) | `ping`/`buildInfo` (`encryption.py:434,447`), `list_collection_names` (`main.py:184`), `estimated_document_count` + `find` no keyVault (`demo.py:408-409`) |
| Abrir a página: chips de titulares | `App.jsx:143` `carregarTitulares` | `GET /demo/exemplos` | `demo.py:305` `exemplos` | mesma função | `demo.py:322` `find` pelo cliente cifrado, collection `clientes` |
| "Buscar por igualdade" (CPF do chip) | `App.jsx:195` -> `buscar` (:137) | `GET /demo/buscar?cpf=` | `demo.py:170` `buscar` | `demo.py::_executar` (:86) | `find` nos dois clientes (`demo.py:102`, `:106`) + leitura por `_id` do DBA (`:128`), `clientes` |
| "Faixa: 5–15 / 15–25 / 25–40 mil" | `App.jsx:212` -> `buscarFaixa` (:138) | `GET /demo/buscar?salario_min=&salario_max=` | `demo.py:170` `buscar` (monta `$gte/$lte` em `salario`) | `_executar` | igual à igualdade, `clientes` |
| "Buscar por UF (campo em claro)" | `App.jsx:217` -> `buscarFaixa` | `GET /demo/buscar?uf=SP` | `demo.py:170` `buscar` | `_executar` (controle: dois lados devolvem o mesmo) | `find` nos dois clientes, `clientes` |
| "Começa com / Termina com / Contém" | `App.jsx:240` -> `buscarTexto` (:139) | `GET /demo/buscar-string?tipo=prefixo\|sufixo\|trecho` | `demo.py:251` `buscar_string` | mesma função; operador vem de `BUSCAS_STRING` (:234) | `server_info` (:254, exige 9.0), `find` com `$expr` + `$encStrStartsWith/EndsWith/Contains` no cifrado (:272), leitura por `_id` no claro (:278) |
| Painel `QueryDetails` ("Ver query / comando que chegou ao servidor") | `components/QueryDetails.jsx` | sem chamada: usa `query_details` / `enviado_ao_servidor` da resposta | montado em `_executar` (:75) e `buscar_string` | `encryption.py::executar_capturando` (:260) e `resumir_comando_enviado` (:276) | listener de comandos (`CapturaDeComando`, `encryption.py:239`), não é query nova |
| "Provas adicionais" > "Mostrar o par" | `App.jsx:297` | `GET /demo/par-repetido` | `demo.py:352` `par_repetido` | mesma função (+ `_ids_do_par` :63) | `find` por `_id` nos dois clientes (`demo.py:369-370`), `clientes` |
| "Provas adicionais" > tabela de alternativas | `App.jsx:272-284` (`ALTERNATIVAS`) | nenhuma (conteúdo estático) | n/a | n/a | n/a |
| "Recarregar titulares" / "Revalidar conexão" | `App.jsx:191` / `:49` | repetem `/demo/exemplos` / `/preflight` | idem | idem | idem |

Não existe botão de reset na UI. Reset é por linha de comando (`scripts/reset_demo.py`).

## 3. Onde estão as queries MongoDB

Briefing: [briefing/queries.md](briefing/queries.md).

| O que faz | arquivo::função (linha) | Operador / pipeline principal | Collection |
|---|---|---|---|
| Busca cifrada (igualdade, faixa, UF) | `routers/demo.py::_executar` (:102) | `find` com filtro `cpf` / `salario $gte-$lte` / `uf`, cliente com AutoEncryption | `clientes` |
| Mesmo filtro como o DBA | `demo.py::_executar` (:106) | `find` idêntico, cliente comum (volta 0 nos campos cifrados) | `clientes` |
| Leitura crua pelo DBA | `demo.py::_executar` (:128) | `find {_id: {$in: ids}}` | `clientes` |
| Busca parcial no e-mail | `demo.py::buscar_string` (:272) | `find` com `$expr` e `$encStrStartsWith` / `$encStrEndsWith` / `$encStrContains` | `clientes` |
| DBA lê os mesmos registros | `demo.py::buscar_string` (:278) | `find {_id: {$in}}` | `clientes` |
| Titulares de exemplo | `demo.py::exemplos` (:322) | `find` com `_id $nin` do par plantado | `clientes` |
| Par de CPF repetido | `demo.py::par_repetido` (:369, :370) | `find {_id: {$in}}` nos dois clientes | `clientes` |
| Checagem do cofre | `demo.py::preflight_checks` (:408-409) | `estimated_document_count` + `find` por `keyAltNames` | `__keyVault` (`QE_KEY_VAULT_NS`) |
| Estado do cluster | `main.py::_preflight_sem_cache` (:181), `main.py::stats` (:200); `encryption.py::readiness` (:434), `versao_servidor` (:447) | `list_collection_names`, `estimated_document_count`, `ping`, `buildInfo` | `clientes`, admin |
| Achar DEK por nome | `encryption.py::dek_id` (:138) | `find_one({keyAltNames})` | `__keyVault` |
| Mapa de campos cifrados | `encryption.py::_campos` (:78) | `queryType` equality (`cpf`, `email`), prefix/suffix/substring (`email_*`), range (`salario`, `score_credito`), `observacoes` só cifrado | `clientes` |
| Criar coleção cifrada | `seed_data.py::criar_colecoes_cifradas` (:126, `create_collection` em :130) | `create_collection(encryptedFields=)` | `clientes` + `enxcol_.*` |
| Inserir dados | `seed_data.py::main` (`insert_many` :174) | `insert_many` pelo cliente cifrado | `clientes` |
| Índices em claro | `seed_data.py::main` (:180-182) | `create_index` em `tenant_id`, `uf`, `cadastro_em` | `clientes` |
| Dropar | `seed_data.py::dropar` (:118) e `scripts/limpar-cofre.py` (:48, :54) | `drop_collection` | `clientes`, `enxcol_.*`, cofre |
| Cofre e DEKs | `scripts/criar-cofre.py::main` (índice :38, DEK :52) | `create_index` único + `create_data_key` | `__keyVault` |
| Verificação pós-reset | `scripts/reset_demo.py::verificar` (:46) | `count_documents`, `find_one` | `clientes` |
| Benchmark | `scripts/bench_qe.py` (:62-143) | `collStats`, `find` | cópia `*_test` |

Nada aqui usa `$search`, `$vectorSearch`, `$merge` nem change stream.

## 4. Compartilhado × só desta PoV

- **`_shared`:** nenhum. Não há import de `_shared` no código (conferido com rg). O backend não usa gateway Grove nem LLM.
- **Variáveis de ambiente** (`backend/.env.example`, lidas em `backend/settings.py`):
  - Locais: `QE_DB`, `QE_KEY_VAULT_NS`, `QE_KMS_PROVIDER`, `QE_LOCAL_MASTER_KEY_PATH`, `CRYPT_SHARED_PATH`, `QE_CONTENTION_FACTOR`, `AWS_KMS_*`, `DEMO_ADMIN_TOKEN`, `ALLOWED_ORIGINS`, `MAX_REQUEST_BYTES`, `MONGO_TIMEOUT_MS`; no frontend, `VITE_DEMO_API_TOKEN` e `VITE_API_PROXY_TARGET`.
  - Comum (cluster): `MONGO_URI`, que vem do cluster compartilhado; no `.env` real é o valor que o `sync_env.py` distribui. Não achei no repo referência direta ao `.env.shared`.
  - `ALLOW_DEMO_DB_WRITE=1` libera scripts de escrita no banco da demo (`settings.py:115-122`).
- **Banco/coleções:** banco `cofre` (padrão de `QE_DB`), coleção `clientes`, cofre `cofre.__keyVault`, mais as `enxcol_.*` que o MongoDB cria. Exclusivos desta PoV; nenhuma outra PoV é citada no código.
- **Chamadas externas:** só o MongoDB (e AWS KMS se `QE_KMS_PROVIDER=aws`, `encryption.py::kms_providers` :176). Sem LLM, Voyage ou Langfuse.

## 5. "Quero mexer em..."

- Texto ou layout da tela -> `frontend/src/App.jsx` (a tela inteira) e `frontend/src/index.css`.
- Faixas de salário dos botões -> `App.jsx:206-210` (array dentro do card "2").
- Exemplos de busca parcial -> `App.jsx` (array de `['prefixo', ...]`, :234-238) e `BUSCAS_STRING` em `backend/routers/demo.py:234` (os dois precisam bater).
- Tabela de alternativas -> constante `ALTERNATIVAS` em `App.jsx:116`.
- Adicionar rota -> `backend/routers/demo.py` (já incluído por `main.py:99`).
- Mudar uma query de busca -> `demo.py::_executar` (:86) ou `buscar_string` (:251).
- Quais campos são cifrados e como -> `encryption.py::_campos` (:78) e `CAMPOS_CIFRADOS` (:43). É imutável: exige `seed_data.py --drop`.
- Fator de contenção -> `QE_CONTENTION_FACTOR` no `backend/.env` (também exige recriar a coleção).
- Dados do seed (quantidade, nomes, par plantado) -> `backend/seed_data.py` (`gerar` :76, `SEMENTE` :35).
- Como o ciphertext aparece na tela -> `frontend/src/components/Cifra.jsx` e `routers/_comum.py::_binario` (:29).
- Máscara/resumo do comando mostrado -> `encryption.py::resumir_comando_enviado` (:276).
- Portas -> `frontend/vite.config.js` (5300), `start.sh` (8300 e 5300), `VITE_API_PROXY_TARGET`.
- Regras de segurança/CORS -> `backend/security.py` e `settings.py` (`allowed_origins`).

## 6. Testes

Comando (README): `backend/venv/bin/python -m pytest` (sem cluster, crypt_shared ou KMS; config em `pyproject.toml`, `testpaths = backend/tests`). Lint: `backend/venv/bin/ruff check backend scripts`.

- `backend/tests/test_demo.py` — o endpoint da demo (buscar, par, exemplos) com Mongo stub.
- `backend/tests/test_encryption.py` — o mapa `encryptedFields` e o cofre de DEKs.
- `backend/tests/test_adversarial.py` — entradas inválidas, injeção, falha de driver.
- `backend/tests/test_live_adversarial.py` — mesmo tema contra cluster real em banco `*_test` (`python -m pytest backend/tests/test_live_adversarial.py`).
- `backend/tests/test_security.py` — guarda de mutação.
- `backend/tests/test_serializacao.py` — serialização de `Binary(6)`.
- `backend/tests/test_seed_data.py` — gerador de dados.
- `backend/tests/test_tese_alternativas.py` — guarda da tabela de alternativas.
- `backend/tests/test_error_logging.py` — log de erro sem vazar segredo.
- `backend/tests/test_bench.py` — partes puras do bench (percentil, termos de string dentro do schema, soma de storage).
- `frontend/tests/apresentacao.test.mjs` — `cd frontend && npm test` (node:test, sem dependência nova): legendas, destaque sem caixa, máscara, contrato dos exemplos com `BUSCAS_STRING`.
