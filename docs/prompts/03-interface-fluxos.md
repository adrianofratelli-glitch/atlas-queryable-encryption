# Atlas Queryable Encryption — interface e fluxos

> Terceiro dos três prompts. A tela, os componentes, o que a UI nunca faz e o roteiro da demo. Arquitetura em `01-arquitetura.md`; coleção, cofre e seed em `02-mongodb.md`.

---

## As duas regras de tela

1. **Nada aparece sem procedência.** Ciphertext é rotulado como ciphertext, com o tamanho real em bytes e a DEK que o cifrou ao lado. Nunca um texto ilustrativo, nunca um valor inventado para preencher o layout.
2. **Não mostre número que não foi medido.** Se algo não rodou contra o cluster, o estado correto da tela é dizer que não rodou. Estimativa apresentada como medição é o único jeito de perder essa reunião de forma irrecuperável.

## A tela

Uma página. Sem navegação lateral, sem roteamento, sem `src/pages/`. `src/App.jsx` é a tela inteira.

```
┌─────────────────────────────────────────────────────────┐
│ Queryable Encryption                    ✓ pré-voo ok    │
│ o servidor executa a busca sem conseguir ler o dado     │
├─────────────────────────────────────────────────────────┤
│ Titulares na base — escolha um, ou digite outro CPF:    │
│ [Rafael Nogueira] [Leandro J.] [Rafael F.] [Diego C.]   │
│                                                          │
│ CPF [99944894613]  ⏵ Buscar por igualdade                │
│ salário ≥[8000] ≤[15000]  ⏵ Buscar por faixa            │
│                            ⏵ Buscar por UF (em claro)   │
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
        ├─ "Por que isso não é o que você já tem" (tabela)
        └─ "A prova de que é randomizado" (o par plantado)
```

### Por que a lista de titulares existe

Ninguém decora um CPF que existe na coleção. E digitar um que não existe devolve **zero** — o mesmo zero que a demo usa como evidência de que o cliente comum não casa valor em claro com ciphertext. A primeira impressão passaria a ser ambígua exatamente no ponto que a tela precisa deixar inequívoco.

`/demo/exemplos` resolve isso: quatro titulares reais, lidos pelo cliente cifrado, com nome, CPF formatado, UF e salário. Três detalhes que essa lista exigiu:

- **O par plantado sai da lista.** O CPF dele aparece em dois titulares.
- **A consulta ordena por `_id`.** `find` sem `sort` não promete ordem nenhuma; duas chamadas devolviam conjuntos diferentes, e com o duplo disparo do React em modo estrito a lista renderizada vinha de uma resposta e o CPF selecionado de outra.
- **O campo só é preenchido se estiver vazio.** Uma resposta atrasada não pode trocar o titular que já está selecionado.

### O painel dividido

`ORDEM` de campos **fixa e igual nos dois lados**. Se cada painel renderizar na ordem que o BSON devolveu, as linhas desalinham e o efeito de "mesmo documento, duas leituras" — que é a tela inteira — desaparece.

O componente `Cifra` é onde mora a regra da procedência. E ele tem uma sutileza que já foi um defeito grave:

> **A amostra de hex tem que sair do PAYLOAD, nunca do começo do blob.** Os 17 primeiros bytes de um `Binary(subtype 6)` são 1 byte de tipo + o UUID de 16 bytes da DEK, e são **idênticos** em todo valor daquele campo. Exibi-los faz dois CPF distintos aparecerem com o mesmo hex — e o par plantado passa a provar o oposto do que existe para provar.

Por isso a tela rotula os 17 bytes iniciais como **chave** (a DEK), e mostra a amostra do payload separada.

### A tabela das alternativas

Fica na própria tela, não só na fala. É o que responde "por que MongoDB e não o que já temos":

| | | |
|---|---|---|
| TDE · disco cifrado | cifra em repouso; quem tem credencial de leitura vê tudo em claro | ✗ |
| CSFLE determinístico | permite igualdade porque o mesmo valor vira o mesmo ciphertext — e é isso que vaza frequência no dump | ⚠ |
| pgcrypto / cifrar na aplicação | protege o valor, mas o banco deixa de conseguir filtrar por ele | ✗ |
| **Queryable Encryption** | **ciphertext randomizado E consultável: igualdade e faixa, com a chave fora do servidor** | ✓ |

A linha do MongoDB é a **conclusão**, não mais um item — ela é destacada visualmente.

## Componentes e hooks

| Arquivo | O que faz |
|---|---|
| `App.jsx` | a tela inteira, o estado da busca, o selo de preflight, o toast de erro |
| `components/Cifra.jsx` | renderiza um valor respeitando a procedência: ciphertext em âmbar, rotulado, com bytes e DEK |
| `components/Documento.jsx` | um documento com a `ORDEM` fixa de campos |
| `components/Bloco.jsx` | JSON cru em `<details>`, para quem quiser conferir |
| `hooks/useApi.js` | `call()` com timeout, abort e o evento `api-error` que alimenta o toast |

**O selo de preflight é permanente**, no topo. Um pré-voo vermelho no palco tem que aparecer **antes** de alguém clicar, não depois.

## Roteiro da demo (5 minutos)

1. **(0:20) A pergunta.** "Quem no seu time consegue ler o CPF dos seus clientes hoje?" Deixe responderem. A resposta honesta é: o DBA, a infra, quem tem o backup, o provedor de nuvem.
2. **(0:40) O que a tela é.** Os dois painéis são **dois clientes contra a mesma coleção**, no mesmo instante. O da direita tem as mesmas credenciais de banco que o DBA já tem hoje. Não é usuário capado — falta a chave, não permissão.
3. **(1:30) Igualdade.** Escolha um titular, busque. Esquerda: 1 documento com o CPF legível. Direita: `Binary(subtype 6)` e **zero resultados**. Diga a frase: *"não é permissão negada, é matemática."*
4. **(2:15) Faixa.** É o que ninguém espera que funcione. `$gte`/`$lte` sobre campo cifrado, cinco documentos na aplicação, zero no cliente comum. Mencione que é GA a partir do 8.0.
5. **(2:45) O controle.** Busque por UF. Agora os dois lados acham a mesma coisa — é campo em claro. Sem esse passo, alguém sai achando que o painel da direita simplesmente não enxerga a coleção.
6. **(3:30) Por que não é o que eles já têm.** A tabela. O ponto que fica: CSFLE e `pgcrypto` determinístico compram igualdade **vendendo frequência**.
7. **(4:15) O par.** Mesmo CPF, dois ciphertexts distintos. É a prova visual de que é randomizado — e é por isso que a linha do CSFLE tem ⚠ em vez de ✓.
8. **(4:45) Fechamento.** Ofereça medir contra o ambiente deles. Vale mais que qualquer número genérico, e é a deixa natural para o próximo encontro.

## Perguntas que sempre vêm, e o que responder

- **"E o que não funciona?"** — `sort`, `regex`, `$search`, `$group`, `$lookup`, índice comum e `$inc` sobre campo cifrado. O caso que importa é o `sort`, que **não falha**: ordena por ciphertext e devolve ordem sem sentido, em silêncio. Um erro do servidor o time descobre no primeiro teste; uma ordenação errada vai para produção.
- **"Então como eu faço relatório?"** — campo cifrado é campo de **filtro e leitura**, não de análise. O que se agrega é a faixa derivada em claro, calculada pela aplicação na escrita — grossa o bastante para não reidentificar, fina o bastante para o relatório servir. `faixa_salarial` está lá para isso.
- **"E o direito ao esquecimento?"** — apagar a DEK torna o campo matematicamente irrecuperável, **inclusive nos backups já feitos**. O registro continua existindo e contabilizável. LGPD art. 18 sem conflito com a retenção do Bacen. Mas a granularidade não é livre: a chave é por campo de uma coleção, nunca por documento. **"Uma DEK por titular" não existe** nessa modelagem — não prometa isso.
- **"Quanto custa?"** — cite o overhead **por documento e por campo**, com o tier ao lado, nunca o múltiplo sozinho. Num M20 com 100.000 titulares deu ~9,5 kB por documento, ~1,9 kB por campo. O múltiplo parecia 63× só porque o documento em claro era pequeno.
- **"A latência não fica ruim?"** — a cifragem acontece **na aplicação**, então depende do hardware de quem apresenta. E cuidado: se o notebook estiver saindo por VPN, o RTT domina tudo e vira "custo da criptografia" na cabeça de quem assiste. Meça a linha de base da rede antes de atribuir qualquer número ao produto.
