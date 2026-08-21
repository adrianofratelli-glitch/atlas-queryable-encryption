# Consulta sobre dado que o servidor não consegue ler

Quem no seu time consegue ler o CPF dos seus clientes hoje? Na maioria das arquiteturas a
resposta é: o DBA, o time de infraestrutura, quem tem acesso ao backup e o provedor de nuvem.
Criptografia em repouso e em trânsito não muda isso — nos dois casos o banco decifra para
poder trabalhar.

**MongoDB Queryable Encryption** cifra o campo com a chave do cliente e ainda assim o filtra,
por igualdade e por faixa, sem que o servidor veja plaintext em momento nenhum: nem em repouso,
nem em trânsito, nem em uso, nem no log, nem no backup.

## A demo

Uma tela. Você digita um CPF, e o mesmo filtro sai ao mesmo tempo por **dois clientes contra o
mesmo cluster**: a sua aplicação, com auto-encryption, e um cliente comum — o DBA, o operador
do Atlas, quem levar o backup.

A aplicação acha o documento e lê o CPF. O cliente comum recebe `Binary(subtype 6)` e, ao
filtrar pelo mesmo valor, **acha zero**.

![A busca por CPF nos dois clientes](docs/screenshots/demo.png)

Há três botões, e cada um responde a uma objeção:

| Botão | O que prova |
|---|---|
| **Buscar por igualdade** | filtro por campo cifrado funciona — sem ciphertext determinístico |
| **Buscar por faixa** | `$gte`/`$lte` sobre campo cifrado, o que ninguém espera que funcione (GA no 8.0) |
| **Buscar por UF** | o controle do experimento: campo em claro, os dois lados acham o mesmo |

E o botão **Mostrar o par** exibe dois titulares diferentes com o **mesmo CPF** produzindo
ciphertexts distintos. É o que separa Queryable Encryption do resto: se fossem iguais, quem
tem o dump contaria repetições e reidentificaria.

## Por que não é o que você já tem

| | |
|---|---|
| TDE, disco cifrado | cifra em repouso; quem tem credencial de leitura vê tudo em claro |
| CSFLE determinístico | permite igualdade porque o mesmo valor vira o mesmo ciphertext — e é isso que vaza frequência |
| `pgcrypto`, cifrar na aplicação | protege o valor, mas o banco deixa de conseguir filtrar por ele |
| **Queryable Encryption** | **ciphertext randomizado e consultável: igualdade e faixa, com a chave fora do servidor** |

## Requisitos

- **MongoDB 7.0+**, no Atlas **M10 ou superior**. Não roda em Flex nem no tier gratuito.
  Consulta por faixa é GA a partir do **8.0**.
- Python 3.11+, Node 20+.
- Um provedor de KMS: arquivo local (demo) ou AWS KMS (produção).

## Setup

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # preencha MONGO_URI
cd ..

# Chave mestra e biblioteca de criptografia
python scripts/gerar-master-key.py     # 96 bytes em backend/secrets/, modo 0600
./scripts/instalar-crypt-shared.sh     # biblioteca → backend/lib/

# Cofre e dados
python scripts/criar-cofre.py          # índice do keyVault + as DEKs da demo
python backend/seed_data.py            # 5.000 titulares nas duas coleções

# Frontend
cd frontend && npm install && cd ..
```

## Executar

```bash
./start.sh --foreground     # backend :8300 + frontend :5300
curl http://localhost:8300/preflight
```

O preflight checa `MONGO_URI`, alcance do cluster, versão do servidor, presença da
`crypt_shared`, o cofre, as duas coleções e o modo da guarda de mutação. Ele existe porque, sem
ele, um cluster em versão errada falha com "comando desconhecido" — uma mensagem que não
menciona criptografia em lugar nenhum.

## Como funciona

```
React (frontend/, :5300) ──fetch──> FastAPI (backend/, :8300)
                                        │
                                        ├── MongoClient CIFRADO (AutoEncryptionOpts) ──> Atlas
                                        ├── MongoClient CLARO  (a "visão do DBA")    ──> Atlas
                                        └── KMS local ou AWS KMS
```

**Os dois clientes de `backend/encryption.py` são a PoV inteira**, não um detalhe de
implementação: o painel dividido da tela é literalmente os dois lado a lado.

A coleção `clientes` é a cifrada; `clientes_claro` guarda os mesmos documentos com os mesmos
`_id`, em claro, para o contraste. O driver cifra o valor da busca com a mesma DEK e envia o
ciphertext; o servidor casa contra estruturas de metadados (`enxcol_.*`) que ele mantém sem
conseguir interpretar.

## Testes

```bash
pytest                        # nenhum precisa de cluster, de crypt_shared ou de KMS
ruff check backend scripts
```

## Segurança

- A chave mestra local **não fica no `.env`**: fica em `backend/secrets/`, com modo 0600, fora
  do controle de versão. KMS local é para demonstração — em produção use AWS KMS, Azure Key
  Vault, GCP KMS ou KMIP.
- Nenhum endpoint devolve chave mestra, DEK decifrada ou `keyMaterial` completo.
- **Nunca aponte esta PoV para nada além de um cluster de demonstração descartável.**
- O dataset é sintético. Os CPF têm dígito verificador válido e prefixo `999`, uma faixa não
  emitida: eles não pertencem a ninguém.

## Licença

MIT.
