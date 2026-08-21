# Atlas Queryable Encryption — arquitetura e princípios

> Primeiro dos três prompts que eu uso pra levantar essa PoV do zero. Os seis módulos, a arquitetura de chaves, os dois clientes MongoDB, a segurança do backend e a operação. Coleções, `encryptedFields` e pipelines em `02-mongodb.md`; tela e roteiro em `03-interface-fluxos.md`.

---

## O que eu quero construir

Uma PoV que prova, contra um cluster de verdade, que **dado cifrado com chave do cliente continua consultável** — e que o servidor nunca vê o plaintext em momento algum: nem em repouso, nem em trânsito, nem em uso, nem em memória, nem no log, nem no backup.

**Sem LLM nenhum aqui.** Essa é a reunião com o time de segurança, com o DPO ou com o auditor do Bacen. Eles não querem ouvir sobre IA; querem ver o campo na tela e não conseguir ler.

| # | Módulo | O que ele tem que provar |
|---|---|---|
| 01 | Cofre de chaves | CMK no KMS, DEK no `keyVault`, e a hierarquia inteira visível |
| 02 | Duas visões | o mesmo `find`, dois clientes: um lê CPF, o outro lê `Binary(subtype 6)` |
| 03 | Consulta sobre cifrado | igualdade e faixa filtrando ciphertext, com o `explain` provando que o servidor não decifrou |
| 04 | Fronteiras | o que **não** funciona sobre campo cifrado, dito antes de o cliente descobrir sozinho |
| 05 | Crypto shredding | apagar a DEK torna o documento matematicamente irrecuperável — o direito ao esquecimento sem `delete` |
| 06 | Preço da privacidade | overhead medido de storage e de latência, cifrado contra claro, lado a lado |

**Os módulos 02 e 04 são o par que sustenta a PoV.** O 02 é o que impressiona; o 04 é o que faz o cliente confiar no que eu digo. Uma demo de criptografia que só mostra o que funciona é a demo que perde o segundo encontro, porque o arquiteto do cliente vai testar `sort` em campo cifrado na segunda-feira e concluir que eu escondi alguma coisa. Diga primeiro.

## Queryable Encryption, não CSFLE

Essa PoV é sobre **Queryable Encryption (QE)**, disponível a partir do MongoDB 7.0, com `range` em GA desde 8.0. **Não é CSFLE**, e a diferença é a coisa mais importante a explicar na primeira tela:

- **CSFLE** (Client-Side Field Level Encryption, desde 4.2) só consulta campo cifrado de forma **determinística** — o mesmo plaintext produz sempre o mesmo ciphertext. Isso permite igualdade, e vaza frequência: quem tem o dump vê qual CPF aparece mais, qual salário se repete, qual é o valor mais comum de um campo de status. Contra um campo de baixa cardinalidade (sexo, UF, status) isso é praticamente plaintext.
- **QE** é randomizado. O mesmo CPF cifrado duas vezes produz dois ciphertexts diferentes, e mesmo assim continua consultável, por igualdade e por faixa. O servidor navega estruturas de metadados cifradas (`enxcol_.esc`, `enxcol_.ecoc`) que ele consegue usar sem conseguir interpretar.

Se alguém no cliente disser "isso é igual ao pgcrypto", a resposta é: pgcrypto obriga a decifrar a coluna inteira para filtrar, ou a guardar um hash determinístico ao lado — que é exatamente o vazamento de frequência acima. Não existe equivalente a QE em Postgres, Oracle, SQL Server ou DynamoDB. Em SQL Server, Always Encrypted with secure enclaves chega perto e depende de hardware específico e de enclave confiável no servidor; QE não depende de enclave nenhum.

Mantenha CSFLE mencionado na tela como comparação histórica. Nunca implemente CSFLE nesta PoV: dois modelos de criptografia no mesmo código confundem quem lê e dobram a superfície de erro.

## Arquitetura

```
React 18 + Vite (:5300) --fetch--> FastAPI (:8300) --+-- MongoClient CIFRADO  --> Atlas (M10+)
                                                     |     (AutoEncryptionOpts + crypt_shared)
                                                     |
                                                     +-- MongoClient CLARO    --> Atlas (mesmo cluster)
                                                     |     (sem auto-encryption: é a "visão do DBA")
                                                     |
                                                     \-- KMS local  ou  AWS KMS (CMK)
```

O dev server do Vite proxia `/api` pro backend **removendo o prefixo**, igual ao resto do portfólio.

**Os dois clientes são a PoV inteira.** Não é um detalhe de implementação: é o artefato de demonstração. Um `MongoClient` configurado com `AutoEncryptionOpts` cifra na saída e decifra na volta, transparente pra aplicação. Um segundo `MongoClient`, sem nada disso, apontado pro mesmo cluster e pela mesma URI, é literalmente o que um DBA com credencial de leitura enxerga. A tela mostra os dois resultados um ao lado do outro, da mesma query, no mesmo instante.

Um router por módulo em `backend/routers/`, pelo mesmo motivo do Atlas Showcase: eu preciso poder mexer no módulo de custo sem risco de quebrar o cofre de chaves cinco minutos antes de uma reunião.

## `crypt_shared`, não `mongocryptd`

Auto-encryption precisa da biblioteca de criptografia do lado do cliente. Existem dois caminhos e **só um deles deve ser usado aqui**:

- **`crypt_shared`** — biblioteca dinâmica (`.dylib`/`.so`) carregada no processo. Sem processo extra, sem porta, sem ciclo de vida pra gerenciar. **É o caminho desta PoV.**
- **`mongocryptd`** — binário separado que o driver sobe sozinho, escutando em `:27020`. Funciona, e adiciona um processo órfão que sobrevive ao backend, ocupa porta no workspace e falha de um jeito que parece problema de rede.

Aponte `CRYPT_SHARED_PATH` para a `.dylib` e passe `crypt_shared_lib_required=True` nas `AutoEncryptionOpts`. **Esse `required=True` não é opcional**: sem ele o driver cai silenciosamente pro `mongocryptd`, e você descobre isso semanas depois vendo um processo estranho no `lsof`. Falhar alto no boot é melhor.

A `crypt_shared` vem no pacote Enterprise/Atlas — o `scripts/instalar-crypt-shared.sh` baixa a versão correta pra plataforma e deixa em `backend/lib/`. Ela não vai pro git.

## Hierarquia de chaves

Três níveis, e explicar os três é metade da reunião:

1. **CMK (Customer Master Key)** — vive no KMS, **nunca sai de lá**. Em produção: AWS KMS, Azure Key Vault, GCP KMS ou KMIP. Na demo local: um arquivo de 96 bytes.
2. **DEK (Data Encryption Key)** — uma por conjunto de campos, guardada **cifrada pela CMK** na coleção `cofre.__keyVault`. O documento da DEK fica no próprio MongoDB, e isso é seguro precisamente porque ele está cifrado por uma chave que o MongoDB não tem.
3. **Campo** — cifrado pela DEK, no cliente, antes de sair pela rede.

A demo tem que ter **os dois provedores de KMS**, com a mesma tela funcionando nos dois:

- **`local`** — chave mestra de 96 bytes em arquivo, gerada por `scripts/gerar-master-key.py`. É o modo padrão, roda em qualquer notebook sem conta de nuvem, e serve pra reunião em que ninguém quer mexer em IAM. **Deixe escrito na tela, em vermelho, que KMS local não é para produção** — a chave mestra em disco ao lado da aplicação anula boa parte do modelo de ameaça.
- **`aws`** — CMK de verdade no AWS KMS. É o que o cliente vai usar, e é o que permite dizer "o rollback da chave é uma política de IAM, não um deploy". Quando as credenciais não estiverem no `.env`, o módulo 01 renderiza um painel de "não configurado" com as instruções — nunca inventa, nunca quebra, mesma disciplina de degradação das colunas de Kafka/ASP do Atlas Showcase.

**A chave mestra local é gerada, nunca commitada, e nunca fica no `.env`.** Fica em arquivo apontado por `QE_LOCAL_MASTER_KEY_PATH`, com o caminho no `.gitignore`. Um `.env` vaza em screenshot com uma facilidade que uma chave de 96 bytes em base64 no meio de uma linha não perdoa.

## Segurança do backend

Dois middlewares, copiados do Atlas Showcase porque o contrato é o mesmo e não vale a pena divergir:

- **`MutationGuardMiddleware`** — bloqueia mutação vinda de fora do loopback sem `DEMO_ADMIN_TOKEN` válido. Compara com `hmac.compare_digest`, não com `==`. Valida `Origin` contra `ALLOWED_ORIGINS`.
- **`ApiHardeningMiddleware`** — teto de corpo + headers `nosniff`, `DENY`, `no-referrer`, `no-store`.

Nesta PoV o `no-store` deixa de ser higiene e passa a ser requisito: várias respostas carregam CPF e salário decifrados. Nenhuma delas pode entrar em cache de proxy.

Três regras próprias desta PoV, que não existem nas outras:

1. **Nenhum endpoint jamais retorna a chave mestra, nem a DEK decifrada, nem o `keyMaterial` cru.** O módulo 01 mostra o documento da DEK com o `keyMaterial` truncado e rotulado como cifrado pela CMK. Se um dia alguém precisar do material completo pra debugar, faz no `mongosh`, não pela API.
2. **O log do backend nunca imprime plaintext de campo cifrado.** Um `logger.info(documento)` em um handler de erro anula a demo inteira e é exatamente o tipo de vazamento que o cliente está pagando pra evitar. O handler global de exceção já devolve só `request_id`; mantenha assim.
3. **A "visão do DBA" é read-only.** O cliente claro nunca escreve. Ele existe pra provar o que o servidor enxerga, e um `insert` por ele plantaria plaintext dentro de uma coleção cifrada — o que produz um documento que a aplicação não consegue mais ler e faz parecer bug do produto.

## Módulo 01 — Cofre de chaves

Mostra a hierarquia inteira, de cima a baixo: o provedor de KMS ativo, a CMK, as DEKs em `cofre.__keyVault` (com `_id`, `keyAltNames`, `creationDate`, `masterKey.provider`) e o mapeamento de qual campo usa qual DEK.

Ações: criar DEK, listar DEKs, adicionar `keyAltName`. **Criar DEK é a única mutação barata desta PoV** — todas as outras (rotação, shredding) são destrutivas.

O painel precisa deixar visível que `cofre.__keyVault` é uma coleção MongoDB comum, consultável pelo cliente claro. Abrir ela na visão do DBA e mostrar que o `keyMaterial` também está cifrado é o momento em que a pergunta "mas e se roubarem o banco inteiro?" morre.

## Módulo 02 — Duas visões

O centro da PoV. Uma tela dividida:

- **Esquerda — a aplicação.** `find` pelo cliente cifrado. CPF, e-mail, salário, tudo legível.
- **Direita — o DBA.** Exatamente o mesmo `find`, pelo cliente claro. Os mesmos documentos, com os campos sensíveis como `Binary(subtype 6)`, exibidos em hexadecimal truncado.

Três coisas que a tela tem que provar sem eu falar:

1. Os `_id` são os mesmos dos dois lados. É o mesmo documento, não dois datasets.
2. **Dois clientes com o mesmo CPF têm ciphertexts diferentes.** Coloque dois documentos assim no seed de propósito e destaque o par na tela. Esse é o argumento anti-CSFLE, e é visual.
3. Os campos não sensíveis (nome da cidade, data de cadastro) aparecem legíveis nos dois lados. Criptografia é por campo, não pela coleção, e ver isso desarma o medo de "então eu perco o banco inteiro".

Botão para reexecutar a query com um filtro digitado pelo operador, para não parecer resultado gravado.

## Módulo 03 — Consulta sobre cifrado

Duas consultas, as duas pelo cliente cifrado:

- **Igualdade** — `{"cpf": "<valor digitado>"}`. O driver cifra o valor da busca com a mesma DEK, manda o ciphertext, o servidor casa contra os metadados cifrados e devolve os documentos.
- **Faixa** — `{"salario": {"$gt": 8000, "$lt": 15000}}`. Esse é o que ninguém espera que funcione, e é o momento mais forte do módulo.

Ao lado, o `explain` da mesma query pelo cliente claro, mostrando que o servidor executou contra estruturas cifradas. E, obrigatoriamente, **o mesmo filtro rodando pelo cliente claro e retornando zero documentos** — porque o valor em claro não casa com nada. Esse zero é evidência, não erro; rotule a tela pra ninguém achar que quebrou.

`contentionFactor` precisa aparecer na tela com uma frase explicando: é o número de partições de metadados por campo, e é o botão de troca entre concorrência de escrita e velocidade de leitura. Padrão 8 nesta PoV. Campo de altíssima escrita quer mais; campo quase estático quer menos. **Ele não pode ser mudado depois sem recriar a coleção.**

## Módulo 04 — Fronteiras

O módulo que eu mais valorizo e que quase ninguém faz. Cada limite com um botão que **realmente tenta a operação e mostra o erro real do servidor**, não um texto escrito à mão:

| Tentativa | O que acontece |
|---|---|
| `sort` por campo `range` cifrado | não ordena por plaintext; ordem de ciphertext não tem significado |
| `regex` / `$text` em campo cifrado | não suportado |
| `$search` (Atlas Search) sobre campo cifrado | o índice não enxerga plaintext |
| `$vectorSearch` com filtro em campo cifrado | mesma coisa |
| `$group` / `$sum` sobre campo cifrado | agregação no servidor precisa do valor |
| `$lookup` casando por campo cifrado | não casa |
| índice comum sobre campo cifrado | recusado |
| `update` com `$inc` em campo `range` | o servidor não faz aritmética sobre ciphertext |

A conclusão que a tela precisa entregar é de **modelagem, não de derrota**: campo cifrado é campo de filtro e de leitura, não de análise. Se o negócio precisa de faixa salarial em relatório, o desenho é uma coluna `faixa_salarial` derivada e não cifrada ao lado da `salario` cifrada, com a granularidade que o time de privacidade aceitar. Mostre esse par no seed, já modelado — a resposta vale mais que o problema.

## Módulo 05 — Crypto shredding

Apagar o documento da DEK em `cofre.__keyVault` torna todo campo cifrado por ela **matematicamente irrecuperável**, inclusive nos backups já feitos e nas réplicas já propagadas.

O fluxo na tela: escolher um titular → mostrar o documento decifrado → apagar a DEK dele → **limpar o cache de DEK do cliente** → reler → o campo agora não decifra, e o driver devolve erro de chave ausente.

**Esse passo do cache é a armadilha número um do módulo.** O driver mantém a DEK decifrada em memória por padrão (60 s, `key_expiration_ms`). Sem recriar o cliente ou zerar o cache, o documento continua abrindo depois do delete e a demo parece falhar. Na PoV o endpoint de shredding recria o cliente cifrado explicitamente. Diga isso em voz alta na demo: é o comportamento correto de um cache, não um furo.

O gancho comercial: LGPD art. 18, direito à eliminação. Uma DEK por titular transforma "apagar os dados de uma pessoa em todos os sistemas, réplicas e backups" — que é um projeto de meses — em um `deleteOne` no cofre. Para clientes de serviços financeiros, some com o conflito clássico entre a retenção obrigatória de Bacen e o direito à eliminação: o registro continua existindo e contabilizável, o conteúdo pessoal não é mais legível por ninguém.

**Uma DEK por titular tem custo**, e essa PoV não pode escondê-lo: mais documentos no cofre, mais chamadas ao KMS, mais pressão no cache. O desenho intermediário e mais comum é uma DEK por inquilino ou por coorte. Ofereça os dois no seed e deixe a escolha explícita na tela.

O módulo é destrutivo por natureza. Um botão de reseed devolve o titular apagado — o seed é determinístico.

## Módulo 06 — Preço da privacidade

O número que decide se o projeto acontece. Duas coleções com **o mesmo dataset**, uma cifrada e uma em claro, e a comparação medida em três eixos:

- **Storage** — `collStats` das duas, mais o tamanho de `enxcol_.esc` e `enxcol_.ecoc`. As coleções de metadados **contam**; ignorá-las é subestimar e vira surpresa em produção.
- **Latência de escrita** — N inserts em cada, p50 e p95. O custo aqui é local (a cifragem acontece na aplicação, não no servidor) e por isso ele depende do hardware do apresentador, não do cluster. **Diga isso na tela**, senão o cliente atribui ao Atlas.
- **Latência de leitura** — igualdade e faixa nas duas coleções, p50 e p95.

Três armadilhas de medição, todas do mesmo tipo das que eu já paguei no módulo de streaming do Atlas Showcase:

1. **Primeira leitura paga o KMS.** A chamada ao AWS KMS pra decifrar a DEK é rede, e ela entra na primeira medição. Sempre aqueça antes, e reporte a primeira separadamente — ela é uma informação legítima ("quanto custa o cold start"), só não pode ser apresentada como custo por operação.
2. **Cache do WiredTiger frio faz a coleção cifrada parecer muito pior.** Aqueça as duas com o mesmo número de leituras antes de medir.
3. **A comparação só vale com o mesmo dataset e o mesmo número de campos.** Comparar uma coleção cifrada com cinco campos contra uma coleção em claro com dois é comparar nada.

Todo número desta tela precisa carregar o tier do cluster e o tamanho da amostra ao lado. `A MEDIR` até rodar contra o cluster de verdade — **não preencha com estimativa**.

## Configuração

`settings.py` é uma dataclass congelada que lê todas as variáveis de ambiente uma vez, igual ao Atlas Showcase. Um `settings.qe_configured` libera os módulos que dependem de auto-encryption; sem `crypt_shared` presente, os módulos 02–06 aparecem como não configurados em vez de estourar, e o módulo 01 continua funcionando pelo cliente claro (o cofre é uma coleção comum).

Variáveis, todas em `backend/.env`:

- `MONGO_URI`, `QE_DB` (padrão `cofre`), `MONGO_TIMEOUT_MS`.
- `QE_KEY_VAULT_NS` (padrão `cofre.__keyVault`), `QE_KMS_PROVIDER` (`local` | `aws`), `QE_LOCAL_MASTER_KEY_PATH`, `CRYPT_SHARED_PATH`.
- `AWS_KMS_KEY_ARN`, `AWS_KMS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` — só no modo `aws`.
- `QE_CONTENTION_FACTOR` (8), `QE_BENCH_DOCS` (500).
- `DEMO_ADMIN_TOKEN`, `ALLOWED_ORIGINS` (`http://localhost:5300,http://127.0.0.1:5300`), `MAX_REQUEST_BYTES`.

## Armadilhas

Essas são as que custam tempo. Leia antes de escrever código, não depois.

- **Queryable Encryption exige MongoDB 7.0+ e, no Atlas, M10+.** Não roda em Flex nem no tier gratuito, e `range` só é GA a partir do 8.0. Se o preflight não checar a versão do servidor, o erro que aparece é de comando desconhecido e não diz nada.
- **`encryptedFields` é imutável.** Trocar um campo de `equality` pra `range`, mudar `contentionFactor`, mudar `min`/`max`/`precision` de um campo `range`, adicionar um campo cifrado novo — tudo isso exige **dropar e recriar a coleção**. Faça o `encryptedFieldsMap` inteiro de uma vez, no papel, antes do primeiro `create_collection`. Esse é o único erro desta PoV que custa o dataset.
- **Campo `range` numérico precisa de `min`, `max` e `sparsity`; `double`/`decimal128` precisam também de `precision`.** Um valor fora da faixa declarada é rejeitado na escrita. Declare a faixa com folga real de negócio (salário até 1.000.000, não até o maior do seed) — o seed cresce e o `max` não pode acompanhar sem recriar a coleção.
- **Dropar uma coleção cifrada não leva junto as `enxcol_.*`** em todos os caminhos. Use `drop` pelo helper de encryption ou apague as três explicitamente. Metadata órfã de uma coleção que não existe mais faz a recriação falhar com uma mensagem que não menciona isso.
- **O cliente claro nunca pode escrever na coleção cifrada.** Um documento com plaintext onde deveria haver `Binary(subtype 6)` faz o cliente cifrado falhar na leitura daquele documento — e o erro aponta pra criptografia, não pra origem real.
- **`AutoEncryptionOpts` no PyMongo exige `pymongo[encryption]`** (que traz `pymongocrypt`). Instalar só `pymongo` dá um `ImportError` no import do módulo de encryption e parece problema de ambiente.
- **A URI do cliente cifrado e a do key vault são a mesma nesta PoV, e não precisam ser.** Em cliente regulado, o cofre em cluster separado com credencial separada é o desenho: quem tem acesso ao dado não tem acesso à chave. Mencione isso na tela do módulo 01; é um upsell natural e mostra que eu sei o que estou vendendo.
- **Cache de DEK de 60 s** — já descrito no módulo 05. Também afeta rotação: uma chave rotacionada só entra em vigor pro cliente depois do cache expirar.
- **Rotação de CMK não recifra os campos.** Ela recifra as DEKs (via `rewrap_many_data_key`), que é barato e instantâneo. Recifrar os campos exigiria reescrever a coleção. Falar isso errado numa reunião de segurança é caro; a tela do módulo 01 precisa distinguir os dois.
- **Nada de screenshot com CPF real.** O seed é sintético e usa CPF gerado com dígito verificador válido mas fora de qualquer faixa emitida. Vale a mesma regra do resto do portfólio, e aqui com mais peso: essa é a PoV cujo screenshot vazado seria mais constrangedor.
- O `backend/.env` está no gitignore. A chave mestra local **também**, e ela não fica no `.env` — fica em arquivo próprio.

## Ordem de trabalho

Nessa ordem, e não em outra:

1. `scripts/gerar-master-key.py` + `scripts/instalar-crypt-shared.sh`. Sem os dois, nada abaixo roda.
2. `backend/encryption.py` — os dois clientes, o `encryptedFieldsMap`, a criação do cofre. **Congele o `encryptedFieldsMap` aqui.**
3. `scripts/criar-cofre.py` + `backend/seed_data.py`, com as duas coleções (cifrada e em claro) e o mesmo dataset.
4. Módulos 01 e 02. Nesse ponto a PoV já é demonstrável, e isso importa: se a agenda encolher, esses dois sozinhos ganham a reunião.
5. Módulo 03, depois o 04.
6. Módulos 05 e 06 por último. O 06 só produz número real com cluster ligado.
7. Testes, `README.md`, screenshots.

O módulo 06 é o que mais tenta consumir o projeto inteiro, do mesmo jeito que o Streaming consome o Atlas Showcase se vier primeiro. Ele é o último.

## Como rodar

```bash
./start.sh --foreground        # backend :8300 + frontend :5300
curl http://localhost:8300/preflight
```

O preflight checa `MONGO_URI`, alcance do cluster, **versão do servidor ≥ 7.0**, presença da `crypt_shared`, o cofre de chaves, as duas coleções do seed e o modo da guarda de mutação.
