# Atlas Queryable Encryption — prompt de construção

> Esse é o briefing que eu entrego **antes de existir uma linha de código**. Não é documentação do que existe: é o que eu daria pra alguém (ou pro Claude) subir a PoV inteira do zero.

Uma tela que prova, contra um cluster de verdade, que **dado cifrado com chave do cliente continua consultável** — por igualdade e por faixa — sem que o servidor, o DBA, o operador do Atlas ou quem levar o backup consiga ler o plaintext. Backend FastAPI em `:8300`, frontend Vite/React em `:5300`, database `cofre`, uma coleção só.

**Sem LLM nenhum aqui.** Essa é a conversa de segurança e conformidade, e ela se ganha com `Binary(subtype 6)` na tela, não com narrativa.

| Arquivo | O que responde |
|---|---|
| [`docs/briefing/01-arquitetura.md`](docs/briefing/01-arquitetura.md) | o argumento único, os dois clientes MongoDB, os dois middlewares, o preflight, as armadilhas que custam o dataset, ordem de trabalho |
| [`docs/briefing/02-mongodb.md`](docs/briefing/02-mongodb.md) | uma coleção e por quê, `encryptedFields` campo a campo, o cofre e as cinco DEKs, as `enxcol_.*`, seed determinístico e o par plantado |
| [`docs/briefing/03-interface-fluxos.md`](docs/briefing/03-interface-fluxos.md) | a tela única, o painel dividido, a lista de titulares, a tabela contra as alternativas, roteiro de demo |

Se for ler só um: o **01**, pela ordem de trabalho. O cofre tem que existir antes do primeiro cliente cifrado, e essa dependência não perdoa.

**A PoV nasceu com seis módulos e foi reduzida a um de propósito.** Seis abas eram muita superfície para um argumento que se prova em trinta segundos. Se ela crescer de novo, que cresça na fala do apresentador — não em aba.
