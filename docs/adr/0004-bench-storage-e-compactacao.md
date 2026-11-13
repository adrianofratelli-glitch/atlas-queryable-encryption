# ADR 0004 — O que o bench mede, e por que o compact é opt-in

**Status:** aceito · **Data:** 2026-11-12 · Medido no Atlas MongoDB 9.0.7, banco `*_test`
com 5.000 titulares, notebook com `ping` do driver p50 258 ms.

## Contexto

O README citava "~170×" de storage somando só bytes lógicos (`size` + índices) de
`clientes` + `enxcol_.*`, sem dizer que a `ecoc` nunca tinha sido compactada, e não
media as buscas de string, o recurso GA do 9.0. O p95 usava `int(n*0.95)-1` (com 30
amostras, o 28º valor). Ao tentar `compactStructuredEncryptionData` pelo cliente da
aplicação, o `socketTimeoutMS` de 16 s estourava enquanto o servidor seguia trabalhando:
a `ecoc` virava `ecoc.compact`, que o bench nem contava.

## Medido (2026-11-12)

| Coleção | Docs | Lógico (MiB) | Em disco (MiB) |
|---|---:|---:|---:|
| `clientes` (dados + índices) | 5.000 | 268,4 | 284,6 |
| `enxcol_.clientes.esc` | 1.034.860 | 46,4 | 106,4 |
| `enxcol_.clientes.ecoc` | 1.034.860 | 112,9 | 62,0 |
| cópia em claro indexada | 5.030¹ | 2,4 | 0,8 |

¹ incluía os 30 inserts do bench; a versão atual apaga esses inserts antes de medir.

Latência p50 (QE × claro): igualdade 405 × 259 ms, faixa 381 × 262 ms, insert 453 × 265 ms;
prefixo/sufixo/trecho 410–412 ms (sem par em claro justo). Prova de rede sem CPF nem trecho
em claro no BSON do comando.

Compact, duas tentativas no mesmo banco: (1) cliente da aplicação, `NetworkTimeout` em 16 s
com o servidor seguindo por mais de 10 min e parando com `ecoc.compact` pendente; (2) cliente
dedicado sem timeout de socket: `OperationFailure` — a transação interna excedeu
`transactionLifetimeLimitSeconds` (60 s). A `esc` passou de 1.034.860 para 1.444.833 entradas
e a `ecoc.compact` continuou com 1.034.860.

## Decisão

- O bench mede prefixo, sufixo e trecho contra o `ping`; storage lógico e em disco por
  coleção, incluindo `ecoc.compact`; p95 por posto mais próximo; o ambiente do cliente.
- O compact roda só com `--compactar`, por um cliente cifrado dedicado (o driver precisa
  anexar os compactionTokens) sem timeout de socket, e o resultado (ou o erro) vai para o JSON.
- Não alteramos `transactionLifetimeLimitSeconds`: é parâmetro do cluster, compartilhado
  com outras PoVs; a decisão fica com quem administra o cluster.
- O README cita os números lógico e em disco, a decomposição e a limitação do compact.

## Consequências

- O custo citado é o de uma coleção recém-semeada (pior caso de `ecoc`). Com a massa atual,
  o campo de substring é o que pesa: reduzir `strMaxLength` ou tirar o campo é a alavanca.
- Pendente: medir o compact com `transactionLifetimeLimitSeconds` maior, ou compactando em
  lotes durante o seed (antes de a `ecoc` passar de ~1 M entradas), num cluster dedicado.
