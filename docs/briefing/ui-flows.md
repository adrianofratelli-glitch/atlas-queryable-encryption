# UI e fluxos — Atlas Queryable Encryption

> Telas, componentes e roteiro de demo. Arquitetura de backend em `architecture.md`; queries e Queryable Encryption em `queries.md`.

## A tela é uma só

Sem roteamento, sem `src/pages/`. `frontend/src/App.jsx` é a tela inteira. A decisão estrutural: a PoV chegou a ter 6 módulos (cofre, duas visões, consultas, fronteiras, crypto shredding, custo) e foi reduzida a 1, porque seis abas são muita superfície para um argumento que se prova em 30 segundos. O material cortado virou fala do apresentador (seção "Perguntas frequentes" no fim).

## As duas regras de tela (não negociáveis)

1. **Nada aparece sem procedência.** Ciphertext é sempre rotulado como ciphertext, com tamanho real em bytes e a DEK que o cifrou ao lado — nunca um texto ilustrativo.
2. **Não mostra número que não foi medido.** Se algo não rodou contra o cluster real, a tela diz que não rodou. Estimativa apresentada como medição perde a reunião de forma irrecuperável.

## Layout da tela (modo palco)

```
┌─────────────────────────────────────────────────────────┐
│ Queryable Encryption                    ✓ pré-voo ok    │
│ o servidor executa a busca sem conseguir ler o dado     │
├─────────────────────────────────────────────────────────┤
│ Titulares na base — selecione um exemplo para buscar:   │
│ [Rafael Nogueira] [Leandro J.] [Rafael F.] [Diego C.]   │
│                                                          │
│ Titular selecionado ⏵ Buscar por igualdade              │
│ [Faixa 5–15 mil] [Faixa 15–25 mil] [Faixa 25–40 mil]   │
│                            ⏵ Buscar por UF (em claro)   │
│ Buscar e-mail cifrado por trecho:                       │
│ [Começa com] [Termina com] [Contém]                    │
├──────────────────────────┬──────────────────────────────┤
│ SUA APLICAÇÃO            │ O DBA · O BACKUP · A NUVEM   │
│ MongoClient + AutoEncr.  │ MongoClient comum, mesma URI │
│ 1 documento · 387 ms     │ 0 documentos · 444 ms        │
│                          │                              │
│ cpf   99944894613        │ ✓ zero — o valor em claro    │
│ nome  Rafael Nogueira    │   não casa com nada          │
│ sal.  13586              │                              │
└──────────────────────────┴──────────────────────────────┘
        │
        └─ "Provas adicionais" (recolhido): tabela de alternativas + par de CPF repetido
```

Screenshot de referência: `docs/screenshots/01-equality.png`.

## Componentes (`frontend/src/`)

| Arquivo | Função |
|---|---|
| `App.jsx` | tela inteira: estado da busca, lista de titulares e opções fixas de faixa e busca parcial, selo de preflight, toast de erro global, painel duplo, seção "Provas adicionais" |
| `components/Cifra.jsx` | renderiza um valor de campo respeitando a regra de procedência: se `__cifrado__` for `true`, mostra hex do **payload** (nunca do início do blob) + bytes reais + prefixo da DEK; senão, mostra o valor puro |
| `components/Documento.jsx` | renderiza um documento inteiro com `ORDEM` de campos **fixa e idêntica** nos dois painéis — se cada lado renderizasse na ordem que o BSON devolveu, as linhas desalinhariam e o efeito "mesmo documento, duas leituras" desapareceria |
| `components/QueryDetails.jsx` | `<details>` recolhível "Ver query / comando que chegou ao servidor". Mostra o comando `find` **como o servidor o recebeu**, capturado por `CommandListener` depois da auto-encryption (`query_details.sent_to_server` em `/demo/buscar`, `enviado_ao_servidor` em `/demo/buscar-string`): o valor buscado aparece como `<Binary subtype 6 · N B · ciphertext>`. Valores em claro sob chaves sensíveis são mascarados em qualquer profundidade (regex `authorization\|password\|secret\|token\|uri\|cpf\|cnpj\|email\|salario\|score\|keymaterial\|key`); o rótulo de ciphertext nunca é mascarado, porque é a prova |
| `hooks/useApi.js` | `call()` com timeout (30s padrão, configurável), `AbortController`, e o evento customizado `api-error` que alimenta o toast global |

### `Cifra.jsx` — o componente onde mora a regra de procedência

Um `Binary(subtype 6)` tem 17 bytes de cabeçalho (tipo + UUID da DEK) que são **idênticos** em todo valor de um mesmo campo. Mostrar esses bytes na tela faria dois CPFs distintos aparecerem com o mesmo hex — o oposto do que o "par plantado" (ver abaixo) existe para provar. Por isso o componente rotula os 17 bytes iniciais como "chave" (a DEK) e extrai a amostra visual do **payload**, a partir do byte 17. Isso já foi um defeito grave e silencioso nesta PoV — vale checar sempre que alguém tocar em `Cifra.jsx` ou em `backend/routers/_comum.py`.

## Fluxos de interface

### Fluxo 1 — carregamento inicial

1. `<SeloPreflight/>` chama `GET /preflight` ao montar. Selo vermelho **antes** de qualquer clique — não depois, no meio da demo.
2. `carregarTitulares()` chama `GET /demo/exemplos`, popula os chips de titulares e pré-seleciona o primeiro CPF (só se ainda não houver seleção — uma resposta atrasada não pode roubar a seleção do usuário).

### Fluxo 2 — busca por igualdade (CPF)

1. Usuário seleciona um chip de titular e clica "Buscar por igualdade". A tela não pede CPF digitado.
2. `apiBusca.call('/demo/buscar?cpf=...')` → `GET /demo/buscar`.
3. Painel esquerdo ("SUA APLICAÇÃO"): 1 documento, CPF legível.
4. Painel direito ("O DBA · O BACKUP · A NUVEM"): mostra duas evidências separadas. (a) O mesmo filtro sem a chave devolve 0 — o servidor não casa valor em claro com ciphertext. (b) Lendo direto por `_id` os mesmos documentos que a aplicação achou (`dba.origem == "por_id"`), o DBA vê `cpf` e `salario` como `Binary(subtype 6)`. O zero prova que a busca exige a chave; a leitura por `_id` prova que o disco não vaza o dado.
5. `<QueryDetails/>` recolhido abaixo: o comando que chegou ao servidor, com o CPF buscado como `Binary(subtype 6)`. É a resposta a "mas o valor da busca não vai em claro?" — o filtro em claro que a aplicação montou não é exibido.

### Fluxo 3 — busca por faixa (salário)

Mesma mecânica do Fluxo 2, com `salario_min`/`salario_max`. É a consulta que ninguém espera que funcione sobre dado cifrado — GA a partir do MongoDB 8.0.

### Fluxo 4 — busca por UF (controle do experimento)

Filtro em campo **em claro**. Os dois painéis devolvem a mesma contagem — é o que prova que o painel direito realmente enxerga a coleção, só não consegue casar valor cifrado.

### Fluxo 5 — busca parcial sobre e-mail cifrado

A tela tem três cards independentes (1 igualdade, 2 faixa + UF, 3 texto parcial), cada um com estado e resultado próprios; um resultado nunca aparece no meio de outro bloco. Três botões apresentam exemplos fixos (prefixo `titular0`, sufixo `@exemplo.invalid`, trecho `ular0@`). Não há campo para digitar nem memorizar valor. A aplicação consulta um dos campos QE de string e mostra os documentos decifrados, com o campo buscado (`email_prefix`/`email_suffix`/`email_substring`) visível e o trecho casado marcado em verde (`mark.casou`); o painel DBA busca os mesmos documentos por `_id` e mostra os bytes cifrados. MongoDB 9.0+ e PyMongo 4.18+ são necessários.

### Fluxo 6 — "Provas adicionais" (seção recolhida)

- **Tabela de alternativas**: TDE, CSFLE determinístico, pgcrypto/cifra na aplicação, Queryable Encryption — com veredito (✗/⚠/✓) e a linha do MongoDB destacada como conclusão, não como mais um item.
- **Par de CPF repetido**: botão "Mostrar o par" chama `GET /demo/par-repetido`. Dois titulares com o mesmo CPF, ciphertexts binários diferentes — prova visual de que a criptografia é randomizada (e por isso CSFLE determinístico recebe ⚠, não ✓, na tabela acima).

## Tratamento de erro e resiliência

- Toast global (`ErroToast`) escuta o evento `api-error`, deduplica erros repetidos por 8s (evita spam de toast em falhas de rede intermitentes), e desaparece sozinho em 6s.
- `useApi.js` distingui cancelamento esperado (troca de tela, StrictMode) de erro real — um `AbortController` cancelado não vira erro exibido ao usuário.
- Falha ao carregar titulares mostra mensagem específica + botão "Recarregar titulares", não trava a tela.
- Entrada inválida vira `422` com mensagem em pt-BR antes de tocar no banco (CPF sem 11 dígitos ASCII, `salario_min > salario_max`, UF fora de 2 letras ASCII, `limite` fora de 1–10, tipo de busca parcial fora da allowlist). Falha do driver vira `502` com o texto do servidor sem `full error`, sem URI e sem hostname do Atlas (`routers/_comum.py:mensagem_segura`).
- `/demo/par-repetido` devolve `503` (não `200` com dado incorreto) se os dois documentos do par plantado não existirem — evita a tela afirmar "ciphertexts iguais" quando na verdade o seed não rodou ou rodou incompleto.

## Roteiro de demo (5 minutos)

1. **(0:20) A pergunta.** "Quem no seu time consegue ler o CPF dos seus clientes hoje?" — deixar responderem.
2. **(0:40) O que a tela é.** Dois clientes contra a mesma coleção, no mesmo instante. O da direita tem as mesmas credenciais de banco que o DBA já tem — falta a chave, não permissão.
3. **(1:30) Igualdade.** Escolher titular, buscar. Esquerda: 1 documento, CPF legível. Direita: `Binary(subtype 6)`, zero resultados. Frase: "não é permissão negada, é matemática."
4. **(2:15) Faixa.** `$gte`/`$lte` sobre campo cifrado — cinco documentos na aplicação, zero no cliente comum. Mencionar GA a partir do 8.0. Abrir "Ver query / comando que chegou ao servidor": os limites da faixa chegaram como `Binary(subtype 6)`.
5. **(2:45) O controle.** Buscar por UF — os dois lados acham o mesmo. Sem esse passo, alguém pode achar que o painel direito não enxerga a coleção.
6. **(3:30) A tabela de alternativas.** CSFLE e pgcrypto determinístico compram igualdade vendendo frequência.
7. **(4:15) O par.** Mesmo CPF, ciphertexts distintos — prova visual da randomização.
8. **(4:45) Fechamento.** Oferecer medir contra o ambiente do cliente.

## Perguntas frequentes (e a resposta)

- **"E o que não funciona?"** — `sort`, `regex`, `$search`, `$group`, `$lookup`, índice comum e `$inc` sobre campo cifrado. O caso que importa é `sort`: não falha, ordena por ciphertext e devolve ordem sem sentido, silenciosamente.
- **"Como faço relatório sobre dado cifrado?"** — campo cifrado é campo de filtro e leitura, não de análise. `faixa_salarial` é derivada em claro pela aplicação (antes de cifrar), grossa o bastante para não reidentificar.
- **"E o direito ao esquecimento?"** — apagar a DEK torna o campo matematicamente irrecuperável, inclusive em backups já feitos. Mas a granularidade é por campo de coleção, nunca por documento — "uma DEK por titular" não existe nessa modelagem.
- **"Quanto custa?"** — citar overhead por documento e por campo, com o tier ao lado, nunca o múltiplo isolado. Referência medida (M20, 100k titulares): ~9,5 kB/documento, ~1,9 kB/campo cifrado.
- **"A latência não fica ruim?"** — a cifragem roda na aplicação; depende do hardware de quem apresenta. Medir a linha de base da rede (RTT/VPN) antes de atribuir qualquer número ao produto.

## Contrato visual do portfólio

Esta UI segue a assinatura MongoDB Dark compartilhada entre os frontends do portfólio (`src/pov-signature.css`, importado depois do stylesheet local). Contêiner raiz com `data-pov-shell`, skip-link `.pov-skip-link` para `#conteudo-principal`. Qualquer mudança na assinatura precisa ser replicada nas demais PoVs e validada em 1440/768/360px.
