# Atlas Queryable Encryption — MongoDB

> Segunda parte do briefing. A coleção, o `encryptedFields`, o cofre de chaves, o seed e a limpeza. Arquitetura e armadilhas gerais em `01-arquitetura.md`; tela e roteiro em `03-interface-fluxos.md`.

---

## Uma coleção, e só uma

Database `cofre`. Uma coleção de negócio:

| Coleção | O que é |
|---|---|
| `clientes` | a coleção cifrada. **Os dois painéis da tela leem ela.** |
| `enxcol_.clientes.esc` | metadados de busca, criados e mantidos **pelo servidor** |
| `enxcol_.clientes.ecoc` | idem |
| `cofre.__keyVault` | o cofre de chaves: uma DEK por campo cifrado |

**Não crie uma cópia em claro dos documentos.** É a tentação óbvia — "assim fica fácil comparar" — e é errada por dois motivos. O contraste da tela vem de **dois clientes**, não de duas coleções: o painel do DBA lê `clientes`, a mesma coleção da aplicação, e a diferença é só ter ou não a chave. E uma cópia em claro coloca cem mil CPF legíveis num projeto cuja tese é que ninguém consegue ler o dado — se alguém abrir o Compass durante a demo e cair nela, você perdeu a reunião.

Uma versão anterior desta PoV tinha `clientes_claro` (para medir overhead de storage) e `clientes_tenant_beta` (coorte com DEK própria, para crypto shredding por inquilino). As duas saíram junto com as telas que as usavam. `scripts/limpar-cofre.py` continua dropando as duas de propósito, porque quem rodou o seed antigo tem esse plaintext parado no cluster.

## `encryptedFields`

**Este mapa é imutável depois do `create_collection`.** Mudar `queryType`, `contention`, `min`/`max`/`precision` ou adicionar campo exige dropar e recriar a coleção — e o dataset vai junto. Decida uma vez.

Cinco campos cifrados, e a escolha de `queries` em cada um é uma decisão de modelagem que a demo vende:

| Campo | Tipo | `queries` | Por quê |
|---|---|---|---|
| `cpf` | string | `equality` | é a busca da demo |
| `email` | string | `equality` | segundo campo de igualdade, mostra que não é caso especial |
| `salario` | int | `range` (`min: 0`, `max: 1_000_000`) | a consulta que ninguém espera que funcione |
| `score_credito` | int | `range` (`min: 0`, `max: 1_000`) | segundo range, faixa bem menor |
| `observacoes` | string | **nenhum** | **de propósito** |

`observacoes` cifrado e **não consultável** é o contraponto que fecha a conversa de custo: campo sem `queries` não paga metadados nas `enxcol_.*`. Nem todo campo sensível precisa ser filtrável, e reconhecer isso é o que separa modelagem de checklist.

Nos campos `range`, declare a faixa com **folga de negócio**, não com o máximo do seed. Subir o `max` depois obriga a recriar a coleção.

Campos que ficam em claro: `nome`, `cidade`, `uf`, `tenant_id`, `faixa_salarial`, `cadastro_em`. `uf` é o controle do experimento na tela. `faixa_salarial` é derivada **pela aplicação** a partir do salário ainda em memória — o servidor recebe a faixa já pronta e o salário já cifrado. É assim que se faz relatório sobre dado cifrado, e é a resposta para "então como eu agrego isso?".

### `contention`

`QE_CONTENTION_FACTOR=8`. Mais partições de metadados por campo aliviam contenção de escrita e obrigam a leitura a varrer mais partições. **Imutável depois do `create_collection`**, como o resto do mapa.

## O cofre

`cofre.__keyVault`, com **uma DEK por campo cifrado** — cinco no total.

Não é escolha de modelagem: o Queryable Encryption **recusa a coleção** se dois campos compartilharem `keyId`. O erro é `Duplicate key ids are not allowed`, code 6338401, e vem da própria `crypt_shared` antes de a requisição sair da máquina.

O `scripts/criar-cofre.py` cria, nesta ordem:

1. **Índice único parcial em `keyAltNames`.** Sem ele, dois `keyAltName` iguais convivem e a busca de DEK por nome fica não determinística.
2. As cinco DEKs, nomeadas `dek-clientes-{campo}`.

**O cofre precisa existir antes do primeiro cliente cifrado.** O `encryptedFieldsMap` resolve o `keyId` de cada campo no momento em que o cliente é construído — é uma consulta ao cofre. Essa dependência define a ordem de trabalho inteira.

### A DEK ausente tem duas causas opostas

E confundi-las custa caro:

- **o cofre nunca foi montado** — erro de setup, tem que estourar alto;
- **a DEK foi apagada** por um crypto shredding — estado **esperado**, e o processo precisa continuar subindo.

Um backend que se recusa a iniciar depois de um shredding transforma um recurso de privacidade em incidente de disponibilidade. A distinção se faz pela existência de qualquer outra DEK no cofre: se há outras, devolva um `keyId` inexistente para o mapa continuar bem-formado. Sem isso o campo perde auto-encryption e passa a devolver ciphertext em silêncio, o que parece bug em vez de chave apagada.

## KMS

`QE_KMS_PROVIDER=local` (padrão) ou `aws`.

O modo local lê uma chave mestra de 96 bytes de um **arquivo**, apontado por `QE_LOCAL_MASTER_KEY_PATH`. Nunca de um valor inline no `.env`. O arquivo fica em `backend/secrets/`, modo 0600, fora do git. É o que faz a PoV rodar em qualquer notebook — e **não é para produção**, o que a tela diz na cara.

Em produção: AWS KMS, Azure Key Vault, GCP KMS ou KMIP. E vale saber dizer certo: **rotação de CMK recifra as DEKs, não os campos.** Errar isso numa reunião de segurança é caro.

## Seed

`backend/seed_data.py`, determinístico (semente fixa), escrevendo em `clientes` **pelo cliente cifrado** — é a aplicação gravando, e o plaintext nunca sai da máquina.

```bash
python backend/seed_data.py            # 5.000 titulares, ~70 s — basta para a demo
python backend/seed_data.py --full     # 100.000; a tela não precisa disso
python backend/seed_data.py --drop     # recria do zero (leva junto as enxcol_.*)
```

O CPF é sintético: dígito verificador válido e **prefixo `999`**, uma faixa não emitida. Não pertence a ninguém, e é isso que permite publicar screenshot.

Índices só em campo **não cifrado** (`tenant_id`, `uf`, `cadastro_em`). Índice comum sobre campo cifrado é recusado pelo servidor — o campo é indexado pelas `enxcol_.*`, que o servidor mantém.

### O par plantado

Dois titulares com o **mesmo CPF**. É o argumento anti-CSFLE, e ele é visual: ciphertext determinístico produziria o mesmo blob duas vezes, e quem tem o dump contaria repetições. Achar esse par no palco por sorte não é opção — ele é plantado pelo seed, e os `_id` vão para `backend/data/demo_seeds.json`.

Três coisas sobre esse arquivo:

1. **Ele só é escrito no FIM do seed.** Um seed interrompido deixa o arquivo anterior no lugar.
2. **Os `_id` mudam a cada `--drop`.** Um `demo_seeds.json` de um seed anterior aponta para documentos que não existem mais.
3. **`/demo/par-repetido` devolve 503 quando não acha os dois documentos.** Sem isso, o conjunto de hexes tem tamanho ≤ 1, a comparação "são distintos?" dá falso e a tela afirma **"ciphertexts iguais"** — o oposto exato do que a PoV prova, no slide mais importante. Falhar alto aqui é obrigatório, e há teste para isso.

O par também é **excluído da lista de titulares** oferecida na tela: o CPF dele aparece em dois documentos, e uma busca por igualdade voltando com dois resultados antes de a tela explicar o par parece defeito.

## Limpeza

```bash
python scripts/limpar-cofre.py           # dropa as coleções, escopo estrito
python scripts/limpar-cofre.py --chaves  # apaga TAMBÉM o cofre — irreversível
```

`--chaves` torna todo ciphertext existente lixo permanente. É literalmente crypto shredding do dataset inteiro.

E a armadilha que aparece na recriação: **dropar a coleção cifrada tem que levar junto as `enxcol_.*`**. Metadata órfã de uma coleção que não existe mais faz o `create_collection` seguinte falhar com uma mensagem que não menciona isso em lugar nenhum.
