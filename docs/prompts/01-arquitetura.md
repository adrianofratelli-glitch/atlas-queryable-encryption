# Atlas Queryable Encryption — arquitetura e princípios

> Primeiro dos três prompts que eu uso pra levantar essa PoV do zero. O argumento único, os dois clientes MongoDB, a segurança do backend e a operação. Coleção, `encryptedFields` e cofre em `02-mongodb.md`; tela e roteiro em `03-interface-fluxos.md`.

---

## O que eu quero construir

Uma tela que responda, contra um cluster de verdade, à pergunta que todo time de segurança faz: **quem consegue ler o CPF dos meus clientes hoje?** Na maioria das arquiteturas a resposta é o DBA, o time de infraestrutura, quem tem o backup e o provedor de nuvem — porque criptografia em repouso e em trânsito exige que o banco decifre para trabalhar.

**Sem LLM nenhum aqui.** É deliberado. Essa é a conversa de conformidade, e ela se ganha mostrando `Binary(subtype 6)` no painel do DBA enquanto a aplicação lê o valor em claro. Um agente conversando no meio disso só rouba atenção do que importa.

O argumento é **um só**, e ele cabe em trinta segundos:

> O servidor executa a busca sem conseguir ler o dado. Por igualdade **e** por faixa.

Tudo que não serve para provar isso fica de fora. Essa regra é a decisão estrutural mais importante do projeto — veja "A tentação de crescer", no fim.

## Arquitetura

```
React 18 + Vite (:5300) --fetch--> FastAPI (:8300)
                                      |
                                      |-- MongoClient CIFRADO (AutoEncryptionOpts + crypt_shared) --> Atlas
                                      |-- MongoClient CLARO   (a "visão do DBA")                   --> Atlas
                                      \-- KMS local (arquivo) ou AWS KMS (CMK)
```

O dev server do Vite proxia `/api` pro backend **removendo o prefixo**.

**Os dois `MongoClient` de `backend/encryption.py` são o artefato de demonstração, não um detalhe de implementação.** O painel dividido da tela é literalmente os dois lado a lado. Se você entender só uma coisa deste documento, que seja essa: a PoV inteira é a diferença entre dois clientes.

- O **cifrado** é construído com `AutoEncryptionOpts`, o `encryptedFieldsMap` e a `crypt_shared`. Ele cifra na escrita, cifra o valor da busca e decifra na leitura — tudo dentro do processo da aplicação.
- O **claro** é um `MongoClient` comum, com **a mesma URI e as mesmas credenciais de banco**. Não é um usuário capado: é o acesso que o DBA já tem hoje. O que falta a ele é a chave.

**Um router só**, `backend/routers/demo.py`, com dois endpoints. Não é preguiça — é a mesma regra do argumento único: um segundo router seria a primeira aba de volta.

| Endpoint | O que faz |
|---|---|
| `GET /demo/buscar` | igualdade sobre `cpf`, faixa sobre `salario`, ou `uf` como controle. Roda o **mesmo filtro nos dois clientes** e devolve os dois resultados |
| `GET /demo/exemplos` | quatro titulares reais da base, para a tela oferecer em vez de exigir que alguém decore um CPF |
| `GET /demo/par-repetido` | dois titulares com o mesmo CPF e ciphertexts distintos — o argumento anti-CSFLE |

### Por que `uf` está lá

`uf` é um campo em claro, e com ele os dois painéis devolvem a mesma quantidade de documentos. É o **controle do experimento**. Sem ele, alguém na sala pode achar que o painel vazio do cliente comum é falta de acesso à coleção. Com ele, o mesmo cliente que achou 5 documentos por UF acha 0 por CPF, e aí não sobra outra explicação.

## Segurança do backend

Dois middlewares, os mesmos do resto do portfólio, e os dois com motivo prático:

- **`MutationGuardMiddleware`** — bloqueia mutação vinda de fora do loopback quando não há `DEMO_ADMIN_TOKEN` válido. Compara com `hmac.compare_digest`, não com `==`. Valida também o `Origin` contra `ALLOWED_ORIGINS`.
- **`ApiHardeningMiddleware`** — limite de corpo por `MAX_REQUEST_BYTES` e `Cache-Control: no-store` em tudo.

Nesta PoV o `no-store` deixa de ser higiene e vira requisito: as respostas carregam CPF e salário **decifrados**, e nenhuma delas pode entrar em cache de proxy.

Três regras que não se negociam:

1. **O log nunca imprime plaintext de campo cifrado.** O handler global de exceção devolve só `request_id`. Um `logger.info(documento)` bem-intencionado anula a demo inteira.
2. **Nenhum endpoint devolve chave mestra, DEK decifrada ou `keyMaterial` completo.**
3. **A chave mestra local não fica no `.env`.** Ela vive em `backend/secrets/`, com modo 0600, fora do git. `.env` guarda o *caminho*, nunca o valor.

## Preflight

`GET /preflight` checa `MONGO_URI`, alcance do cluster, versão do servidor, `range` GA, presença da `crypt_shared`, o cofre, a coleção e o modo da guarda de mutação. A tela mostra o resultado como um selo permanente.

Ele existe por um motivo específico: **num cluster em versão errada, o erro que aparece é de comando desconhecido e não menciona criptografia em lugar nenhum.** Sem o preflight, você perde dez minutos de reunião debugando a coisa errada.

## Armadilhas

Essas custaram tempo de verdade. Estão aqui para não custarem de novo.

- **Queryable Encryption exige MongoDB 7.0+ e, no Atlas, M10+.** Não roda em Flex nem no tier gratuito. Consulta por faixa só é GA no **8.0**.
- **`encryptedFields` é imutável depois do `create_collection`.** Trocar `queryType`, `contention`, `min`/`max`/`precision` ou adicionar campo cifrado exige dropar e recriar a coleção. **É o único erro desta PoV que custa o dataset inteiro.** Decida uma vez. `backend/tests/test_encryption.py` é o alarme.
- **Dropar a coleção cifrada tem que levar junto as `enxcol_.*`.** Metadata órfã faz a recriação falhar com uma mensagem que não menciona isso.
- **DDL de coleção cifrada pega lock.** Um seed anterior travado segura esse lock e o `create_collection` seguinte espera para sempre, a 0% de CPU. Parece problema de rede e não é — garanta um processo só.
- **O cofre tem que existir ANTES do primeiro cliente cifrado.** O `encryptedFieldsMap` precisa do `keyId` no momento em que o cliente é construído. Daí a ordem de trabalho lá embaixo não ser negociável.
- **DEK ausente tem duas causas opostas**, e confundi-las custa caro: o cofre nunca foi montado (erro de setup, tem que estourar alto) ou a DEK foi apagada por crypto shredding (estado esperado, o processo precisa continuar subindo). Um backend que não reinicia depois de um shredding transforma recurso de privacidade em incidente de disponibilidade. A distinção se faz pela existência de qualquer outra DEK no cofre.
- **Cache de DEK de 60 s.** Depois de apagar uma DEK, o documento continua abrindo até o cache expirar. É comportamento correto de cache, não furo.
- **Rotação de CMK recifra as DEKs, não os campos.** Falar isso errado numa reunião de segurança é caro.
- **`pymongo[encryption]`**, não `pymongo`. Sem o `pymongocrypt` o import de `encryption.py` estoura e parece problema de ambiente.
- **A amostra de ciphertext na tela tem que sair do PAYLOAD.** Os 17 primeiros bytes de um `Binary(subtype 6)` são 1 byte de tipo + o UUID de 16 bytes da DEK, e são **idênticos** em todo valor daquele campo. Mostrar o começo do blob faz dois CPF distintos aparecerem com o mesmo hex — e o par plantado passa a provar o oposto do que existe para provar. Esse foi um defeito grave e silencioso.
- **Teste que toca `encrypted_fields()` conecta no banco** se você não stubar o cofre: a resolução do `keyId` é uma consulta. Passa na máquina de quem tem `.env` e falha no CI. Stub obrigatório.

## Ordem de trabalho

Ela importa mais aqui do que nas outras PoVs do portfólio, porque as dependências são duras.

1. `settings.py` congelado e `.env.example` — nada funciona antes de a configuração ser lida uma vez.
2. `scripts/gerar-master-key.py` → 96 bytes em `backend/secrets/`, modo 0600.
3. `scripts/instalar-crypt-shared.sh` → a biblioteca em `backend/lib/`. O driver é configurado com `crypt_shared_lib_required=True`, então **sem ela nada sobe**.
4. `encryption.py`: o `encryptedFieldsMap`, os dois clientes, o cofre. **Pare aqui e decida o mapa** — ele é imutável depois.
5. `scripts/criar-cofre.py` → índice único parcial em `keyAltNames` + uma DEK por campo.
6. `seed_data.py` → a coleção cifrada, com o par de CPF repetido plantado.
7. `routers/demo.py` e o `/preflight`.
8. Frontend.

Pular do 1 direto pro 6 é o caminho mais rápido para dropar e recriar tudo.

## A tentação de crescer

Essa PoV começou com **seis módulos**: cofre de chaves, duas visões, consulta sobre cifrado, fronteiras, crypto shredding e preço da privacidade. Cada um funcionava. Todos foram cortados menos um.

O motivo é que seis abas são muita superfície para um argumento que se prova em trinta segundos. Quem assiste não sai lembrando de seis coisas — sai lembrando de uma, e é melhor escolher qual.

O material cortado não era ruim, e boa parte dele vira **fala do apresentador**:

- **Fronteiras** (`sort`, `regex`, `$search`, `$group`, `$lookup`, índice comum e `$inc` sobre campo cifrado) — o que dizer quando perguntarem "e o que não funciona?". O caso mais valioso é o `sort`, que **não falha**: ordena por ciphertext e devolve ordem sem sentido, em silêncio. Um erro do servidor o time descobre no primeiro teste; uma ordenação errada vai para produção.
- **Crypto shredding** — apagar a DEK torna o campo matematicamente irrecuperável, inclusive nos backups já feitos. LGPD art. 18 sem conflito com a retenção obrigatória do Bacen. A granularidade **não é livre**: com auto-encryption a chave é ligada por campo de uma coleção, nunca por documento. "Uma DEK por titular" não existe nessa modelagem — não prometa isso em reunião.
- **Custo** — o overhead honesto é por documento e por campo, não o múltiplo. Numa medição em M20 com 100.000 titulares deu **~9,5 kB por documento** (~1,9 kB por campo cifrado), o que virava 63× só porque o documento em claro era pequeno. Se for citar número, cite o overhead por campo e diga o tier ao lado.

Se você for ressuscitar algum deles como tela, faça a pergunta antes: **isso prova o argumento único, ou é mais uma aba?**
