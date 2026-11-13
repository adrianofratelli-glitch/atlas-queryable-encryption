# ADR 0001 — Uma coleção, dois clientes

**Status:** aceito · **Data:** 2026-11-12 (registra decisão de 2026-10; antes só no briefing)

## Contexto

A PoV precisa provar que o servidor executa a busca sem ler o dado. As primeiras versões
tinham seis módulos e duas coleções extras: `clientes_claro` (cópia em claro, para medir
storage) e `clientes_tenant_beta` (coorte com DEK própria, para crypto shredding).

## Decisão

- Uma coleção de negócio, `clientes`, lida por dois `MongoClient` sobre a mesma URI
  (`backend/encryption.py`): `cliente_cifrado()` com `AutoEncryptionOpts` + `crypt_shared`
  e `cliente_claro()` sem chave, que só lê.
- O mesmo filtro sai pelos dois ao mesmo tempo (`backend/routers/demo.py::_executar`). Quando o
  cliente claro acha zero, a tela mostra os mesmos `_id` lidos direto, na ordem da aplicação
  (`backend/routers/demo.py::na_ordem_de`), para o lado a lado casar linha a linha.
- `uf` (em claro) é o controle: os dois lados acham o mesmo.
- A comparação de storage contra dado em claro mora só no bench (`scripts/bench_qe.py`), que
  cria e apaga a cópia em banco `*_test`.

## Consequências

- Nenhum CPF legível no cluster da demo: abrir o Compass não contradiz a tese.
- O contraste é de cliente, não de destino; não há como "trapacear" escolhendo outra coleção.
- Crypto shredding saiu da tela; `reiniciar_cliente_cifrado()` continua para quem apagar DEK.
