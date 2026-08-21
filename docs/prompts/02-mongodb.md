# Atlas Queryable Encryption — modelagem, cofre e coleções

> Segundo dos três prompts. `encryptedFieldsMap`, as coleções de metadados, o cofre de chaves, o que o servidor consegue e não consegue fazer sobre ciphertext, seed e limpeza. Arquitetura em `01-arquitetura.md`; tela e roteiro em `03-interface-fluxos.md`.

---

## Databases e coleções

Um database só, `cofre`. Não há motivo pra separar — diferente do Atlas Showcase, aqui não existem módulos concorrendo por dataset.

| Coleção | O que é |
|---|---|
| `clientes` | a coleção cifrada; é a PoV |
| `clientes_claro` | **o mesmo dataset, sem criptografia**; existe só para o módulo 06 comparar |
| `__keyVault` | o cofre: um documento por DEK, `keyMaterial` cifrado pela CMK |
| `enxcol_.clientes.esc` | metadados de estado do campo cifrado, criados e mantidos pelo servidor |
| `enxcol_.clientes.ecoc` | compactação dos metadados, idem |

As duas `enxcol_.*` são criadas automaticamente junto com `clientes` e **não devem ser tocadas por nada nesta PoV** — nem lidas para lógica, nem escritas, nem indexadas. Elas aparecem na tela, no módulo 01 e no 06, como evidência e como custo. Só isso.

`clientes_claro` existe por um motivo e é bom ser honesto sobre ele: um comparativo de storage e de latência não vale nada sem o controle. E ela é também o passivo: deixe visível na tela que **essa é a coleção que qualquer banco de dados do mercado teria**, e é exatamente ela que aparece legível no dump. Ela não é um artefato de teste; ela é o antes.

## `encryptedFieldsMap` — congele isso antes de escrever código

É imutável depois do `create_collection`. Mudar qualquer coisa aqui significa dropar a coleção e recriar. Decida uma vez.

```python
ENCRYPTED_FIELDS = {
    "cofre.clientes": {
        "fields": [
            {"path": "cpf",            "bsonType": "string", "queries": {"queryType": "equality", "contention": 8}},
            {"path": "email",          "bsonType": "string", "queries": {"queryType": "equality", "contention": 8}},
            {"path": "salario",        "bsonType": "int",    "queries": {"queryType": "range", "contention": 4,
                                                                          "min": 0, "max": 1_000_000, "sparsity": 1}},
            {"path": "score_credito",  "bsonType": "int",    "queries": {"queryType": "range", "contention": 4,
                                                                          "min": 0, "max": 1000, "sparsity": 1}},
            {"path": "observacoes",    "bsonType": "string"},
        ]
    }
}
```

O racional de cada escolha, que é o que eu quero poder defender numa reunião:

- **`cpf` e `email` são `equality`.** Ninguém busca CPF por faixa. `equality` é mais barato em metadados que `range`, e o custo de metadados é o que aparece no módulo 06.
- **`salario` e `score_credito` são `range`.** São eles que provam o argumento que ninguém espera. `min`/`max` declarados com folga de negócio, não com o máximo do seed: subir o `max` depois obriga a recriar a coleção.
- **`observacoes` não tem `queries`.** É campo cifrado **não consultável**, e ele existe de propósito na PoV: mostra que nem todo campo cifrado precisa pagar o custo de metadados. Se o negócio nunca filtra por aquele campo, deixe-o sem `queries` e economize. Essa é uma decisão de modelagem que dá pra vender.
- **`contention` 8 em campos de escrita frequente, 4 nos de faixa.** É o botão entre concorrência de escrita e velocidade de leitura: mais partições de metadados aliviam contenção de escrita e obrigam a leitura a varrer mais partições. Também imutável.
- **Campos fora da lista continuam em claro**: `nome`, `cidade`, `uf`, `cadastro_em`, `tenant_id`, `faixa_salarial`. Criptografia é por campo, e ver campo legível ao lado de campo cifrado no mesmo documento desarma o medo de perder o banco inteiro.

### O campo derivado, que é a resposta do módulo 04

`faixa_salarial` (`"5k-10k"`, `"10k-15k"`, …) fica **em claro, no mesmo documento**, derivada do `salario` cifrado no momento da escrita, pela aplicação.

Ele existe porque o módulo 04 vai provar que `$group`/`$sum` não funcionam sobre campo cifrado, e a pergunta seguinte do cliente é sempre "então como eu faço meu relatório?". A resposta já está modelada no seed: você não agrega o valor exato; você agrega a faixa, com a granularidade que o time de privacidade aceitar. Grosso o bastante pra não reidentificar, fino o bastante pro relatório servir.

Deixe isso explícito na tela. É a diferença entre "não dá" e "dá assim".

## Índices

`clientes` recebe índice comum só em campo **não cifrado**: `tenant_id`, `cadastro_em`, `uf`. Índice comum sobre campo cifrado é recusado pelo servidor — e o módulo 04 tenta criar um de propósito, pra mostrar o erro real.

O que substitui o índice nos campos cifrados são as `enxcol_.*`, mantidas pelo servidor. Não há o que ajustar nelas, e não há `explain` de plano legível ali dentro: o `explain` no módulo 03 serve pra mostrar **que o servidor executou sem plaintext**, não pra otimizar.

`__keyVault` precisa do índice único parcial que o driver espera:

```javascript
db.__keyVault.createIndex(
  { keyAltNames: 1 },
  { unique: true, partialFilterExpression: { keyAltNames: { $exists: true } } }
)
```

Sem ele, dois `keyAltName` iguais convivem e a busca de DEK por nome fica não determinística. O `scripts/criar-cofre.py` cria esse índice; não deixe isso implícito no seed.

## Seed

`backend/seed_data.py`, determinístico por semente fixa de RNG. Escreve os mesmos documentos nas duas coleções (`clientes` pelo cliente cifrado, `clientes_claro` pelo cliente claro), com o mesmo `_id` dos dois lados — assim o módulo 06 compara documento a documento e o módulo 02 pode provar que é o mesmo dado.

Padrão: 5.000 titulares. `--full` vai a 100.000, para o módulo 06 ter volume de storage que signifique alguma coisa.

O que o seed precisa garantir, e o que cada garantia serve:

- **Dois titulares com o mesmo CPF, de propósito**, com `_id` conhecido e gravado em `backend/data/demo_seeds.json`. É o par que o módulo 02 destaca pra provar que ciphertexts iguais em plaintext saem diferentes. Sem um par plantado, achar um no palco é sorte.
- **Salários espalhados de verdade** entre 1.500 e 45.000, com massa nas faixas que a demo consulta. Uma faixa que devolve zero documento no palco parece falha.
- **CPF sintético com dígito verificador válido, em faixa não emitida.** Ele vai aparecer em screenshot; ele não pode pertencer a ninguém.
- **Pelo menos dois `tenant_id`**, para o módulo 05 poder demonstrar a DEK por coorte sem inventar dado na hora.
- **Idempotência** por `_id` determinístico: rodar duas vezes não duplica. `--drop` recria do zero, e o drop precisa levar junto as `enxcol_.*`.

O seed é o único lugar que escreve em `clientes_claro`. Todo o resto da aplicação a trata como somente leitura.

## Estratégia de DEK no seed

Três DEKs, com `keyAltNames` legíveis, porque a tela do módulo 01 fica muito melhor com nome do que com UUID:

| `keyAltName` | Uso |
|---|---|
| `dek-principal` | todos os campos cifrados da coleção, caso padrão |
| `dek-tenant-<id>` | uma por inquilino, para o módulo 05 demonstrar shredding por coorte |
| `dek-titular-<id>` | uma para um único titular, para o módulo 05 demonstrar o caso extremo |

O contraste é o ponto pedagógico: uma DEK por titular dá o direito ao esquecimento mais limpo que existe, e cobra em documentos no cofre, chamadas ao KMS e pressão de cache. Uma DEK por inquilino é o desenho que a maioria dos clientes acaba adotando. Ter os três na tela ao mesmo tempo transforma a conversa de "qual é o jeito certo" em "qual é o seu caso".

## Consultas dos módulos

**Módulo 02 — a mesma query, dois clientes.** Um `find` só, executado duas vezes:

```python
filtro = {"uf": "SP"}                         # campo em claro, funciona nos dois
cifrado = client_cifrado[db]["clientes"].find(filtro).limit(5)
claro   = client_claro[db]["clientes"].find(filtro).limit(5)
```

Mesmo filtro, mesmos `_id`, resultados diferentes. É a tela inteira.

**Módulo 03 — igualdade e faixa.**

```python
client_cifrado[db]["clientes"].find({"cpf": cpf_digitado})
client_cifrado[db]["clientes"].find({"salario": {"$gte": 8000, "$lte": 15000}})
```

E a contraprova, obrigatória na mesma tela:

```python
client_claro[db]["clientes"].find({"cpf": cpf_digitado})   # → 0 documentos
```

Esse zero é o resultado mais importante do módulo. Rotule como evidência esperada.

**Módulo 04 — as tentativas que falham.** Cada uma roda de verdade e a tela mostra o erro do servidor, sem tradução. Não escreva a mensagem de erro à mão: o valor está em ela vir do MongoDB.

**Módulo 06 — os três eixos.** `collStats` de `clientes`, `clientes_claro`, `enxcol_.clientes.esc` e `enxcol_.clientes.ecoc`; N inserts cronometrados em cada coleção com p50/p95; e as consultas de igualdade e faixa cronometradas nas duas. Aqueça antes, e reporte a primeira leitura (a que paga o KMS) separada do resto.

## Limpeza

`scripts/limpar-cofre.py`, com escopo estrito, e a ordem importa:

1. `clientes` — pelo helper de encryption, para levar junto as `enxcol_.*`.
2. `clientes_claro`.
3. `__keyVault` — **só com `--chaves`.** Apagar o cofre sem querer é o crypto shredding do dataset inteiro; ele precisa de um flag explícito.

O script nunca aceita nome de coleção por parâmetro. Escopo fixo, coleções conhecidas, mesma disciplina do `cleanup-streaming-data.py` do Atlas Showcase.
