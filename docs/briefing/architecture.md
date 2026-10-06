# Arquitetura — Atlas Queryable Encryption

> Se o gestor perguntar "como isso é montado", a resposta está aqui. Queries e índices reais estão em `queries.md`; telas e fluxo de uso em `ui-flows.md`. Não há agente de IA nesta PoV — ver seção "Sem LLM" no fim.

## O que esta PoV prova

Uma tela só, com um argumento só: **o servidor executa buscas sem conseguir ler o dado, por igualdade, faixa e padrões de string selecionáveis.** As buscas por prefixo, sufixo e trecho usam Queryable Encryption para strings e requerem MongoDB 9.0+ (a PoV chegou a ter 6 módulos e foi reduzida a 1 — ver o histórico deste briefing).

A pergunta que ela responde numa reunião de segurança: **quem no seu time hoje consegue ler o CPF de um cliente?** Resposta honesta na maioria dos stacks: o DBA, a infra, quem tem o backup, o provedor de nuvem — porque criptografia em repouso/trânsito exige que o banco decifre para trabalhar. Queryable Encryption tira essa capacidade do servidor sem tirar a capacidade de consulta.

## Stack

| Camada | Tecnologia | Porta |
|---|---|---|
| Frontend | React 18 + Vite | `:5300` |
| Backend | FastAPI + PyMongo (`pymongo[encryption]`) | `:8300` |
| Banco | MongoDB Atlas, **M10+ obrigatório** (Queryable Encryption exige 7.0+; consulta por faixa é GA no 8.0+; busca QE por padrão de string exige 9.0+) | — |
| KMS | Arquivo local de 96 bytes (dev) ou AWS KMS (produção) | — |

O dev server do Vite proxia `/api` para `http://localhost:8300`, removendo o prefixo `/api` na saída.

## Diagrama de componentes e fluxo de dados

```
┌──────────────────────┐   fetch /api/*   ┌─────────────────────────────┐
│ React 18 + Vite       │ ───────────────▶│ FastAPI (backend/main.py)   │
│ frontend/src/App.jsx  │◀─────────────── │  :8300                      │
└──────────────────────┘   JSON            └───────────┬─────────────────┘
                                                         │
                                    ┌────────────────────┼────────────────────┐
                                    │                     │                    │
                          MongoClient CIFRADO   MongoClient CLARO      ClientEncryption
                          (AutoEncryptionOpts    (mesma URI, mesmas     (cofre: criar/
                           + crypt_shared)        credenciais — a        rotacionar DEK)
                                    │              "visão do DBA")               │
                                    ▼                     ▼                      ▼
                              ┌─────────────────────────────────────────────────────┐
                              │              MongoDB Atlas (database `cofre`)        │
                              │  coleção `clientes` (cifrada) + `cofre.__keyVault`   │
                              │  + `enxcol_.clientes.esc` / `.ecoc` (metadados,       │
                              │    mantidos pelo servidor)                           │
                              └─────────────────────────────────────────────────────┘
                                    ▲
                                    │
                          KMS local (arquivo em backend/secrets/)
                          ou AWS KMS (CMK) — nunca visto pelo MongoDB em claro
```

**Fluxo das buscas por igualdade/faixa/UF** (`GET /demo/buscar`):
1. Frontend monta um filtro (CPF, faixa de salário, ou UF) e chama `/api/demo/buscar`.
2. O backend roda o **mesmo filtro em paralelo** (`ThreadPoolExecutor`, 2 workers) contra os dois `MongoClient`.
3. O cliente cifrado cifra o valor de busca com a DEK do campo e manda o ciphertext; o servidor casa contra estruturas de metadados (`enxcol_.*`) sem conseguir interpretar o valor.
4. O cliente claro manda o mesmo filtro em texto puro; contra um campo cifrado, nunca casa com nada — porque o dado armazenado é `Binary(subtype 6)` randomizado.
5. Os dois resultados voltam lado a lado para o frontend, que renderiza os dois painéis.

**Fluxo de busca parcial** (`GET /demo/buscar-string`): a aplicação executa `$encStrStartsWith`, `$encStrEndsWith` ou `$encStrContains` por um dos três campos configurados para string. O cliente claro não tenta repetir a busca QE: ele busca os mesmos `_id` e exibe os valores como ciphertext. A API aceita apenas os IDs `prefixo`, `sufixo` e `trecho`; a UI não oferece entrada de texto livre.

## Componentes do backend

| Arquivo | Responsabilidade |
|---|---|
| `backend/main.py` | app FastAPI, CORS, middleware de request-id, handlers de exceção, endpoints de operação (`/`, `/health/live`, `/health/ready`, `/preflight`, `/stats`) |
| `backend/settings.py` | `dataclass(frozen=True)` que lê env vars **uma vez**. `settings.qe_configured` exige URI + `crypt_shared` + KMS configurados |
| `backend/encryption.py` | os dois `MongoClient`, o `encryptedFieldsMap`, o cofre de DEKs, `reiniciar_cliente_cifrado()`, `resumo_dek()` |
| `backend/security.py` | `MutationGuardMiddleware` (bloqueia mutação remota sem token) + `ApiHardeningMiddleware` (headers de segurança, limite de corpo) |
| `backend/routers/demo.py` | busca comparativa (`/demo/buscar`), busca QE por string (`/demo/buscar-string`), par de CPF (`/demo/par-repetido`), `/demo/exemplos` e `preflight_checks()` |
| `backend/routers/_comum.py` | serialização segura de `Binary(subtype 6)` e de erros crus do servidor |
| `backend/seed_data.py` | gerador determinístico de dados sintéticos, grava pelo cliente cifrado |
| `scripts/criar-cofre.py` | cria o índice único do keyVault + as DEKs para todos os campos cifrados |
| `scripts/gerar-master-key.py`, `scripts/instalar-crypt-shared.sh`, `scripts/limpar-cofre.py` | setup e limpeza de ambiente |
| `scripts/reset_demo.py` | reset único: limpa coleções e `enxcol_.*` (e o cofre, com `--recriar-chaves`), garante índice do keyVault e DEKs, recria a coleção com `encryptedFields`, semeia, cria índices e **verifica** (contagem, par plantado, `Binary(subtype 6)` em todo campo cifrado lido sem chave, igualdade cifrada) |
| `scripts/bench_qe.py` | overhead medido de QE contra a mesma massa em claro indexada (igualdade, faixa, insert, storage) e prova de rede; só roda em banco `*_test` e apaga o que cria |

### Guarda do banco da demo

`settings.exigir_permissao_de_escrita()` é chamada por `seed_data.py`, `criar-cofre.py`, `limpar-cofre.py` e `reset_demo.py`. Se `QE_DB` **ou** o banco de `QE_KEY_VAULT_NS` não terminar em `_test`, o script recusa sem `ALLOW_DEMO_DB_WRITE=1`. O banco de teste usa o próprio cofre (`<QE_DB>_test.__keyVault`): um cofre de teste apontando para o cofre da demo também é recusado. Os metadados do seed (`backend/data/demo_seeds.<QE_DB>.json`) são por banco, para o seed de teste não trocar o par plantado da demo.

### O comando que chega ao servidor

O cliente cifrado é criado com um `CommandListener` (`encryption.py:CapturaDeComando`). O PyMongo publica o `CommandStartedEvent` **depois** da auto-encryption, então o listener vê exatamente o que vai pela rede. `executar_capturando()` arma a captura por thread (`threading.local`), só para o `find` sobre `clientes` — os `find` internos do driver no cofre são ignorados — e `resumir_comando_enviado()` troca cada `Binary(subtype 6)` por `<Binary subtype 6 · N B · ciphertext>` e remove `lsid`, `$clusterTime`, `$db` e `encryptionInformation` (schema com `keyId`, sem material de chave). É o que o drawer "Ver query / comando que chegou ao servidor" mostra.

### Erros e logs sem plaintext

- Entrada inválida vira `422` antes de tocar no banco; falha do driver vira `502` com a mensagem do servidor passada por `mensagem_segura()` (`routers/_comum.py`): sem `full error`, sem URI, sem hostname `*.mongodb.net`, até 400 caracteres.
- O access log do uvicorn gravaria `GET /demo/buscar?cpf=999…`; o filtro `SemQueryStringNoAccessLog` (`main.py`) troca a query string por `?<omitida>`.
- O handler global de exceção loga só `request_id` e o tipo da exceção.

### Os dois clientes MongoDB — o coração da PoV

Definidos em `backend/encryption.py:232-281`. Não é detalhe de implementação, é o artefato de demonstração inteiro:

- **`cliente_cifrado()`** (`encryption.py:256`) — `MongoClient` com `AutoEncryptionOpts` (`encryption.py:243-253`), `encryptedFieldsMap`, `crypt_shared_lib_required=True`. Cifra valores na escrita e na busca, decifra na leitura, tudo dentro do processo. É "a aplicação".
- **`cliente_claro()`** (`encryption.py:232`) — `MongoClient` comum, **mesma URI, mesmas credenciais de banco**. Não é usuário com permissão reduzida — é exatamente o acesso que o DBA/infra/backup/nuvem já têm hoje. O que falta a ele é a chave, não permissão. É read-only por convenção da PoV (nunca grava na coleção cifrada).

### Decisão de design: por que `required=True` no crypt_shared

Sem `crypt_shared_lib_required=True`, o driver cairia silenciosamente para `mongocryptd` (um processo auxiliar), que sobe órfão na porta `:27020` e falha de um jeito que parece problema de rede. Falhar alto no boot é a escolha deliberada (`encryption.py:248-252`).

### Decisão de design: lock não-reentrante e ordem de montagem

`_auto_encryption_opts()` é montado **fora** do lock (`encryption.py:266-281`) porque montá-lo lê o cofre (resolve `keyId` de cada campo), e ler o cofre usa o cliente claro, que disputa o mesmo lock. Com lock não reentrante isso seria deadlock silencioso — processo parado a 0% CPU, sem exceção, parecendo problema de rede.

### Middlewares de segurança (`backend/security.py`)

- **`MutationGuardMiddleware`** — bloqueia qualquer método não-GET/HEAD/OPTIONS vindo de fora do loopback, a menos que `DEMO_ADMIN_TOKEN` seja enviado e bata via `hmac.compare_digest` (evita timing attack). Também valida `Origin` contra `ALLOWED_ORIGINS`.
- **`ApiHardeningMiddleware`** — `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` em toda resposta, e limite de corpo por `MAX_REQUEST_BYTES`. O `no-store` aqui não é higiene genérica: as respostas carregam CPF e salário **decifrados**, e não podem entrar em cache de proxy.

### `/preflight` — por que existe

`main.py:106-170`. Checa `MONGO_URI`, alcance do cluster, versão do servidor (7.0+ obrigatório, `range` GA só 8.0+), presença da `crypt_shared`, estado do cofre, existência da coleção e modo da guarda de mutação. Cacheado por 8s (`_PREFLIGHT_CACHE_TTL_S`) porque o frontend chama a cada montagem de `<SeloPreflight/>`, e cada chamada roda `buildInfo` + `list_collection_names` + contagens no keyVault — comandos baratos isoladamente, mas sem motivo para repetir a cada re-render.

Motivo de existir: num cluster em versão errada, o erro nativo do driver é "comando desconhecido" e não menciona criptografia em lugar nenhum — sem o preflight, dez minutos de reunião debugando a coisa errada.

## Frontend

`frontend/src/App.jsx` é a tela inteira — sem roteamento, sem `src/pages/`. Detalhes de componentes e fluxos de UI estão em `ui-flows.md`.

## Sem LLM nesta PoV

Confirmado por busca no código-fonte: **não há agente de IA, LLM ou orquestração conversacional nesta PoV**. É deliberado — a tese se prova mostrando `Binary(subtype 6)` na tela, e um agente no meio roubaria atenção do argumento. Por isso não existe `agent-behavior.md` neste briefing.

## Segredos e configuração

Credenciais vivem só em `backend/.env` (fora do git). A chave mestra local **não** fica no `.env` — fica em `backend/secrets/`, arquivo com modo `0600`, fora do git; o `.env` guarda apenas o caminho. Nenhum endpoint da API devolve chave mestra, DEK decifrada, ou `keyMaterial` completo (`resumo_dek()` trunca em 12 bytes — `encryption.py:325-342`).
