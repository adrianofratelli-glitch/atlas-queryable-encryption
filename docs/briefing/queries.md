# Queries, índices e Queryable Encryption — Atlas Queryable Encryption

> Onde está cada query, o que ela faz, e por quê. Tudo extraído do código real em `backend/` e `scripts/`. Este projeto **não usa aggregation pipelines** — só `find()` e comandos administrativos (`create_collection`, `create_index`, `create_data_key`). Confirmado por grep em `backend/` e `scripts/` por `.aggregate(`, `.find(`, `create_index`, `createIndex`, `encryptedFieldsMap`.

## 1. Queries de leitura (`find`)

### 1.1 Busca comparativa — `GET /demo/buscar`

**Onde:** `backend/routers/demo.py:70-125` (função `_executar`), chamada por `buscar()` em `demo.py:128-175`.

**O que faz em linguagem natural:** (quando o filtro cifrado volta com 0 no cliente claro, lê os mesmos `_id` achados pela aplicação também pelo cliente claro e devolve em `dba.documentos` com `dba.origem = "por_id"`; `dba.encontrados` continua sendo a contagem do filtro) monta um único filtro (igualdade por CPF, faixa por salário, ou UF como controle) e roda **o mesmo filtro em paralelo** nos dois `MongoClient` (cifrado e claro), via `ThreadPoolExecutor` de 2 workers efetivos. É a query que sustenta a tela inteira — o painel duplo é literalmente o resultado desta função.

**Por que existe:** é a prova visual central da PoV. Rodar em paralelo (em vez de sequencial) corta a latência por request pela metade — os dois `MongoClient` são objetos distintos, thread-safe, com pools de conexão próprios.

**Exemplo do filtro (igualdade sobre campo cifrado):**
```python
filtro = {"cpf": "99912345678"}
colecao.find(filtro, {"observacoes": 0}).limit(5)
```

**Exemplo do filtro (faixa sobre campo cifrado):**
```python
filtro = {"salario": {"$gte": 8000, "$lte": 15000}}
colecao.find(filtro, {"observacoes": 0}).limit(5)
```

**Exemplo do filtro (controle, campo em claro):**
```python
filtro = {"uf": "SP"}
colecao.find(filtro, {"observacoes": 0}).limit(5)
```

Os três tipos podem se combinar (CPF + faixa de salário simultâneos). A projeção `{"observacoes": 0}` sempre exclui o campo cifrado sem `queries` (não é buscável, então não há motivo de trazê-lo para a tela). `limite` é validado por `Query(..., ge=1, le=10)` — `LIMITE_MAX = 10` em `demo.py:40`.

**Por que `uf` existe como filtro:** é o controle do experimento. Campo em claro, os dois clientes devolvem a mesma contagem — sem esse controle, alguém pode achar que o cliente "comum" simplesmente não enxerga a coleção, em vez de não conseguir casar ciphertext.

### 1.2 Titulares de exemplo — `GET /demo/exemplos`

**Onde:** `backend/routers/demo.py:178-224`.

**O que faz:** busca N titulares (padrão 4, entre 1 e 8) pelo **cliente cifrado** — a aplicação lendo o próprio dado, como faria em produção — para a tela oferecer escolhas em vez de exigir que alguém decore um CPF sintético.

```python
filtro = {"_id": {"$nin": _ids_do_par()}}  # exclui o par plantado (ver 1.3)
colecao.find(filtro, {"_id": 1, "nome": 1, "cpf": 1, "salario": 1, "uf": 1}) \
       .sort("_id", 1) \
       .limit(quantos + 3)
```

**Por que `sort("_id", 1)`:** `find()` sem `sort` não promete ordem nenhuma — duas chamadas podiam devolver conjuntos diferentes, e no StrictMode do React (que dispara efeitos duas vezes) a lista renderizada vinha de uma resposta e o CPF selecionado de outra.

**Por que exclui o par plantado:** o CPF do par aparece em dois documentos; oferecê-lo como opção normal faz uma busca por igualdade devolver dois resultados antes da tela explicar por quê.

### 1.3 Par de CPF repetido — `GET /demo/par-repetido`

**Onde:** `backend/routers/demo.py:227-272`.

**O que faz:** busca por `_id` (usando os IDs plantados no seed, persistidos em `backend/data/demo_seeds.json`) nos dois clientes, e compara os ciphertexts hex dos dois documentos.

```python
colecao.find({"_id": {"$in": [id1, id2]}}, {"observacoes": 0})
```

**Por que existe:** é o argumento anti-CSFLE. CSFLE determinístico produz o **mesmo ciphertext** para o mesmo valor — o que vaza frequência de dados para quem tem o dump. Queryable Encryption é randomizado: mesmo CPF, dois ciphertexts binários distintos, e ainda assim consultável por igualdade. A rota falha com 503 se não encontrar os dois documentos — do contrário a tela afirmaria "ciphertexts iguais", o oposto exato do que a PoV existe para provar.

## 2. Comandos administrativos (não são queries de negócio, mas movem o cluster)

### 2.1 Criação da coleção cifrada — `create_collection(..., encryptedFields=...)`

**Onde:** `backend/seed_data.py:122-128` (`criar_colecoes_cifradas`).

```python
for nome, definicao in encrypted_fields().items():
    colecao = nome.split(".", 1)[1]
    db_cifrado.create_collection(colecao, encryptedFields=definicao)
```

Chama `encrypted_fields()` de `backend/encryption.py:150-155`, que monta o `encryptedFieldsMap` completo (ver seção 3).

### 2.2 Índices comuns (só em campos não cifrados)

**Onde:** `backend/seed_data.py:165-168`.

| Índice | Campo | Tipo | Por que existe |
|---|---|---|---|
| `tenant_id_1` | `tenant_id` | single-field ascendente | multi-tenant sintético da PoV (`banco-alfa`/`banco-beta`); suporta filtro por inquilino se a demo evoluir para isso |
| `uf_1` | `uf` | single-field ascendente | é o campo de **controle** do experimento — sustenta a busca por UF que a tela usa para provar que os dois clientes enxergam a mesma coleção |
| `cadastro_em_1` | `cadastro_em` | single-field ascendente | suporta ordenação/filtro temporal; não usado pela tela hoje, preparado para relatório por data de cadastro |

**Por que só em campos não cifrados:** índice comum sobre campo cifrado é recusado pelo servidor. Campos cifrados são "indexados" pelas coleções auxiliares `enxcol_.<colecao>.esc` e `enxcol_.<colecao>.ecoc`, que o próprio servidor cria e mantém a partir do `encryptedFields` — não existe `create_index` explícito para eles no código.

### 2.3 Índice único do keyVault

**Onde:** `scripts/criar-cofre.py:37-41`.

```python
cofre.create_index(
    "keyAltNames",
    unique=True,
    partialFilterExpression={"keyAltNames": {"$exists": True}},
)
```

**Por que existe:** sem ele, dois documentos de DEK com o mesmo `keyAltName` poderiam coexistir, e a resolução de DEK por nome (`dek_id()` em `encryption.py:97-140`) ficaria não determinística. É um índice único **parcial** — só se aplica a documentos que têm o campo `keyAltNames`.

### 2.4 Criação de DEKs — `create_data_key`

**Onde:** `scripts/criar-cofre.py:46-55`, via `client_encryption()` (`backend/encryption.py:310-317`).

```python
encryption.create_data_key(
    settings.kms_provider,          # "local" ou "aws"
    master_key=master_key_ref() or None,
    key_alt_names=[nome],            # ex.: "dek-clientes-cpf"
)
```

Cria uma DEK por nome em `nomes_dek()` (`encryption.py:61-67`) — cada campo cifrado tem sua própria DEK.

## 3. Queryable Encryption — configuração de campos cifrados

**Onde:** `backend/encryption.py:74-155` (`_campos`, `encrypted_fields`).

### `encryptedFieldsMap` completo

| Campo | Tipo BSON | `queryType` | `contention` | `min` / `max` / `sparsity` | Motivo |
|---|---|---|---|---|---|
| `cpf` | `string` | `equality` | `QE_CONTENTION_FACTOR` (padrão 8) | — | busca principal da demo |
| `email` | `string` | `equality` | `QE_CONTENTION_FACTOR` (padrão 8) | — | segundo campo de igualdade, mostra que `cpf` não é caso especial |
| `email_prefix` | `string` | `prefix` | padrão 8 | consulta de 3–20 caracteres | `$encStrStartsWith` |
| `email_suffix` | `string` | `suffix` | padrão 8 | consulta de 3–30 caracteres | `$encStrEndsWith` |
| `email_substring` | `string` | `substring` | padrão 8 | campo até 40; consulta de 3–6 caracteres | `$encStrContains` |
| `salario` | `int` | `range` | `contention // 2` (padrão 4) | `min=0`, `max=1_000_000`, `sparsity=1` | a consulta que ninguém espera que funcione (GA a partir do MongoDB 8.0) |
| `score_credito` | `int` | `range` | `contention // 2` (padrão 4) | `min=0`, `max=1_000`, `sparsity=1` | segundo campo de faixa, intervalo bem menor — mostra que `min`/`max` são decisão de modelagem por campo |
| `observacoes` | `string` | **nenhum** (`queries` ausente) | — | — | **deliberado**: campo cifrado e não consultável não paga custo de metadados nas `enxcol_.*` |

Cada campo tem seu próprio `keyId`, resolvido via `dek_id(nome_dek(colecao, campo))` (`encryption.py:97-140`) — **uma DEK por campo por coleção**, nunca compartilhada. Não é escolha de modelagem, é exigência do servidor: duas chaves iguais em campos diferentes fazem o `create_collection` falhar com `Duplicate key ids are not allowed` (code `6338401`).

### Por que o mapa é imutável

`encryptedFields` não pode mudar depois do `create_collection` — trocar `queryType`, `contention`, `min`/`max`/`precision`, ou adicionar um campo cifrado, exige **dropar e recriar a coleção inteira**, dataset junto. É o único erro desta PoV que custa tudo. Há teste dedicado em `backend/tests/test_encryption.py`.

Os três campos `email_*` guardam o mesmo e-mail sintético cifrado. Cada campo QE aceita um tipo de query configurado, por isso há um campo para prefixo, outro para sufixo e outro para substring. A UI oferece opções predefinidas, sem texto livre. `/demo/buscar-string` valida a opção por allowlist, exige MongoDB 9.0+, executa a expressão pelo cliente cifrado (a resposta inclui `campo`, `valor`, `modo` e `limite` para a tela marcar onde o trecho casou) e busca os mesmos `_id` pelo cliente claro para exibir os ciphertexts. Para atualizar uma instalação antiga: crie as DEKs com `python scripts/criar-cofre.py` e recrie a coleção descartável com `python backend/seed_data.py --drop`.

### `contention` — o que é e por que importa

`QE_CONTENTION_FACTOR` (padrão `8`, variável de ambiente, 0–64) controla quantas partições de metadados o servidor mantém por valor cifrado. Mais partições aliviam contenção de escrita (menos threads disputando a mesma partição de metadados ao inserir valores repetidos) mas obrigam a leitura a varrer mais partições na busca. Campos `range` usam metade do contention factor dos campos `equality` (`faixa = max(0, forte // 2)` em `encryption.py:76`), porque faixas normalmente casam mais documentos por busca, e contention muito alto ali penaliza leitura sem necessidade.

### Algoritmo e onde a randomização entra

Queryable Encryption grava valores cifrados como `Binary(subtype 6)`. Ao contrário de CSFLE determinístico (mesmo valor → mesmo ciphertext, o que vaza frequência para quem tem o dump), QE é **randomizado**: o mesmo CPF gerado duas vezes produz dois blobs binários diferentes, e ainda assim é consultável — porque o servidor mantém estruturas de metadados (as coleções `enxcol_.*`) que permitem casar o ciphertext da busca contra o ciphertext armazenado, sem decifrar nenhum dos dois. É esse contraste que `GET /demo/par-repetido` (seção 1.3) prova na tela.

Um `Binary(subtype 6)` tem 17 bytes de cabeçalho (1 byte de tipo de blob + UUID de 16 bytes da DEK) seguidos do payload cifrado. Os 17 bytes iniciais são **idênticos** para todo valor daquele campo — é o endereço da chave, não o segredo — por isso `backend/routers/_comum.py:15-41` extrai a amostra de hex a partir do payload (índice 17 em diante), nunca do início do blob, senão dois valores distintos apareceriam com o mesmo hex na tela.

### KMS (Key Management Service) — configuração, sem expor chave real

**Onde:** `backend/encryption.py:159-210`.

Dois provedores, escolhidos por `QE_KMS_PROVIDER`:

- **`local`** (padrão) — chave mestra de **96 bytes**, lida de um **arquivo** apontado por `QE_LOCAL_MASTER_KEY_PATH`, nunca de valor inline no `.env`. Arquivo vive em `backend/secrets/` (fora do git, modo `0600`). Explicitamente marcado como **não-produção** — a chave fica em disco ao lado da aplicação, o que anula boa parte do modelo de ameaça.
- **`aws`** — usa AWS KMS; credenciais vêm de `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_KMS_KEY_ARN` / `AWS_KMS_REGION` (env vars, nunca hardcoded). Em produção alternativas equivalentes seriam Azure Key Vault, GCP KMS ou KMIP.

**Nenhum endpoint da API expõe a chave mestra, a DEK decifrada, ou o `keyMaterial` completo.** `resumo_dek()` (`encryption.py:325-342`) trunca o material em 12 bytes para exibição — o suficiente para provar que a DEK existe e está cifrada pela CMK, insuficiente para reconstituí-la.

Uma nota operacional importante para reunião de segurança: **rotacionar a CMK recifra as DEKs, não os campos.** Os dados no banco continuam com o mesmo ciphertext; só a camada de proteção da chave de dados muda.

## 4. O que Queryable Encryption **não** suporta (perguntado com frequência)

Não há código para isso no repo; vale registrar por ser pergunta recorrente: `sort`, `regex`, `$search`, `$group`, `$lookup`, índice comum e `$inc` sobre campo cifrado não funcionam. O caso mais perigoso é `sort`: **não falha** — ordena pelo ciphertext e devolve uma ordem sem sentido, silenciosamente.
