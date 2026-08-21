# Atlas Queryable Encryption — interface e roteiro

> Terceiro dos três prompts. As regras de tela, o painel dividido, o comportamento de rede e o roteiro da demo. Arquitetura em `01-arquitetura.md`; coleções e modelagem em `02-mongodb.md`.

---

## Duas regras de tela

Valem pro portfólio inteiro e aqui elas são mais rígidas, porque o público é o time de segurança:

1. **Nada na tela que não tenha vindo do backend nesta execução.** Sem número gravado, sem ciphertext ilustrativo, sem mensagem de erro escrita à mão. O que a tela mostra é o que o cluster respondeu agora.
2. **A tela diz o que ainda não foi medido.** `A MEDIR` é um estado legítimo e visível. Preencher com estimativa e apresentar como medição é o único jeito de perder essa reunião de forma irrecuperável.

Uma terceira, específica desta PoV: **nenhum campo em claro na tela sem rótulo dizendo de qual cliente veio.** A demo inteira é sobre quem consegue ler o quê; um valor legível sem procedência anula o argumento.

## Stack

React 18 + Vite, sem LeafyGreen (o Atlas Showcase também não usa, e o contrato visual do `POV_UI_DESIGN_SYSTEM.md` é cumprido pelos tokens diretamente). Roteamento por hash, um componente por módulo, `useApi` e `usePolling` copiados do Atlas Showcase sem mudança.

Copie `--bg-primary #001E2B`, `--accent #00ED64`, Outfit / JetBrains Mono. O acento de domínio desta PoV é o **âmbar `#ffc010`** para ciphertext e para os avisos de KMS local — é o único desvio de paleta, e ele é semântico, não decorativo.

`useApi` tem uma pegadinha herdada que importa aqui: o `loading` dele é **uma flag para todas as chamadas daquela instância**. O módulo 02 dispara duas chamadas (cliente cifrado e cliente claro) e quer os dois painéis carregando de forma independente — dê um `useApi()` para cada painel, ou os dois piscam juntos e o efeito de "mesma query, dois resultados" some.

## Módulo 02 — o painel dividido

É a tela que vende. Layout:

```
┌───────────────────────────────┬───────────────────────────────┐
│  ▚ APLICAÇÃO                  │  ▚ DBA / OPERADOR / BACKUP    │
│  MongoClient + AutoEncryption │  MongoClient comum            │
├───────────────────────────────┼───────────────────────────────┤
│  _id      6712…a4             │  _id      6712…a4             │
│  nome     Marina Alves        │  nome     Marina Alves        │
│  cpf      ███.███.███-██  ✓   │  cpf      Binary(6) 02a3f1…   │
│  salario  R$ 12.400        ✓   │  salario  Binary(6) 9c40be…   │
│  uf       SP                  │  uf       SP                  │
└───────────────────────────────┴───────────────────────────────┘
        mesmo _id · mesma query · mesmo instante
```

Detalhes que não são cosméticos:

- Os `_id` iguais **alinhados na mesma linha**, com a legenda embaixo. Se os dois painéis rolarem independentes, o cliente duvida que seja o mesmo documento.
- Ciphertext em mono, âmbar, truncado com o tamanho real em bytes ao lado. O tamanho é informação: é ele que explica o overhead de storage do módulo 06.
- O par de CPF idêntico com ciphertext diferente ganha destaque próprio, com uma frase curta: *mesmo CPF, ciphertexts diferentes — é isso que CSFLE não faz*.
- Campos em claro dos dois lados renderizados **igualmente**, sem realce. O contraste tem que vir do dado, não do CSS.
- Um campo de filtro editável no topo, que reexecuta as duas queries. Sem ele parece resultado gravado.

## Módulo 04 — a tela das fronteiras

Uma lista de tentativas, cada uma com botão próprio. Ao clicar: a operação roda de verdade, e a linha expande com o comando enviado e a resposta crua do servidor.

Nada de ✅/❌ sozinho. Cada linha fechada carrega **a razão em uma frase**, porque é ela que o arquiteto do cliente vai repetir pro time depois. E o bloco final da página é a modelagem alternativa — `faixa_salarial` ao lado de `salario` — apresentada como resposta, não como consolo.

## Módulo 05 — a tela do shredding

Destrutiva, e a tela precisa parecer destrutiva: confirmação explícita, nome do titular escrito por extenso, aviso de que o efeito alcança backups e réplicas.

A sequência na tela é uma linha do tempo, não três painéis soltos:

```
1. documento legível        →  2. DELETE da DEK  →  3. cache limpo  →  4. documento ilegível
```

O passo 3 aparece **como passo**, não como detalhe de implementação. É ele que explica por que o documento ainda abriu por alguns segundos, e transformar isso em passo visível é a diferença entre "achei que estava quebrado" e "entendi o cache".

Botão de reseed ao lado, sempre visível. O seed é determinístico, então o titular volta.

## Rede e polling

Nada aqui faz polling: não há execução em andamento pra acompanhar, ao contrário do módulo de streaming do Atlas Showcase. Toda chamada é sob demanda. Mantenha `usePolling` no projeto mesmo assim — o módulo 06 usa `useVisivel` para não deixar um benchmark rodando com a aba escondida.

O benchmark do módulo 06 pode passar de 30 s com `QE_BENCH_DOCS` alto. Passe `timeoutMs` explícito no `useApi` daquela chamada; o padrão de 30 s aborta a medição no meio e o erro parece falha de cluster.

## Roteiro da demo — 8 minutos

Ensaiado nessa ordem. Se sobrar tempo, o 06; se faltar, corte o 06 e o 01, nunca o 02 e o 04.

1. **(0:30) A pergunta.** "Quem no seu time consegue ler o CPF dos seus clientes hoje?" A resposta real é: o DBA, o time de infraestrutura, quem tem acesso ao backup, e o provedor de nuvem. Não avance antes de alguém no cliente concordar com isso.
2. **(1:30) Módulo 02.** Painel dividido. Não explique antes — deixe a tela falar e espere a reação. Aponte os `_id` iguais. Aponte o par de CPF com ciphertexts diferentes.
3. **(2:00) Módulo 03.** Digite um CPF, ache o titular. Depois a faixa salarial. **Esse é o momento que separa a demo de qualquer concorrente** — pare aqui e deixe a pergunta acontecer. Mostre a mesma query pelo cliente claro devolvendo zero.
4. **(1:30) Módulo 04.** Rode duas ou três tentativas que falham, ao vivo. Termine na modelagem alternativa. Essa é a parte que compra credibilidade pro resto.
5. **(1:30) Módulo 05.** Crypto shredding, com a linha do tempo. Amarre em LGPD art. 18 e, se for serviço financeiro, no conflito com a retenção obrigatória do Bacen.
6. **(1:00) Módulo 06.** O número. Se ainda estiver `A MEDIR`, **diga que está** e ofereça medir contra o ambiente deles — isso vale mais que um número genérico, e é a deixa natural pro próximo encontro.

Encerre no módulo 01 se perguntarem sobre governança de chave: quem opera o KMS, o cofre em cluster separado, rotação de CMK sem recifrar campo.

## O que não entra na tela

- Chave mestra, DEK decifrada e `keyMaterial` completo. Nunca, em nenhum painel.
- CPF de pessoa real, em nenhum ambiente, nem em screenshot recortado.
- Nome de cliente, projeto ou cluster do Atlas — mesma regra do resto do portfólio: troque por nome neutro no DOM antes de capturar.
- Comparação nominal com concorrente. Fale "banco relacional tradicional" e deixe o cliente dizer o nome. Uma tabela com logo de concorrente no meio de uma reunião de segurança muda o tom, e nunca pra melhor.
