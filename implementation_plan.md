# Atlas Queryable Encryption — prompt de construção

> Esse é o briefing que eu entrego **antes de existir uma linha de código**. Não é documentação do que existe: é o que eu daria pra alguém (ou pro Claude) subir a PoV inteira do zero.

Uma PoV que responde uma pergunta só, e responde com evidência na tela: **dá pra consultar dado que o servidor nunca consegue ler?** Seis módulos sobre Queryable Encryption em um cluster real — cofre de chaves, o contraste entre a visão do DBA e a visão da aplicação, consulta de igualdade e de faixa sobre ciphertext, as fronteiras do recurso, crypto shredding e o preço medido da privacidade. Backend FastAPI em `:8300`, frontend Vite/React em `:5300`, database `cofre`.

**Sem LLM nenhum aqui**, pelo mesmo motivo do Atlas Showcase: essa é a conversa de segurança e conformidade, e ela se ganha com `Binary(subtype 6)` na tela, não com narrativa.

**A tese comercial em uma frase:** MongoDB é o único banco de dados de propósito geral no mercado em que um campo pode ficar cifrado com chave do cliente e ainda assim ser filtrado por igualdade e por faixa — sem que o servidor, o DBA, o operador do Atlas ou quem levar o backup consiga ler o plaintext.

| Arquivo | O que responde |
|---|---|
| [`docs/prompts/01-arquitetura.md`](docs/prompts/01-arquitetura.md) | os seis módulos, os dois clientes MongoDB, o `crypt_shared`, KMS local × AWS KMS, segurança do backend, armadilhas, ordem de trabalho |
| [`docs/prompts/02-mongodb.md`](docs/prompts/02-mongodb.md) | `encryptedFieldsMap`, as coleções `enxcol_.*`, o cofre de chaves, o que dá e o que não dá em índice/pipeline, seed e limpeza |
| [`docs/prompts/03-interface-fluxos.md`](docs/prompts/03-interface-fluxos.md) | as duas regras de tela, o painel dividido DBA × aplicação, roteiro de demo em 8 minutos |

Se for ler só um: o **01**. A ordem de trabalho importa mais aqui do que em qualquer outra PoV do portfólio — errar o `encryptedFields` de um campo `range` obriga a recriar a coleção inteira, e isso vira meia hora perdida.

## Estado

Escrito com o cluster desligado. Toda a estrutura, código, seed, testes e roteiro estão prontos; **nenhum número de latência ou de storage nesta PoV foi medido ainda**. Todo lugar que espera medição está marcado com `A MEDIR` — não substitua por estimativa, e não apresente estimativa como medição. Isso é o mesmo contrato de honestidade das outras PoVs do portfólio: o valor da demo está em o número ser real.
