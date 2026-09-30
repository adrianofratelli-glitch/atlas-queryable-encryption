# Query data the server cannot read

[![CI](https://github.com/adrianofratelli-glitch/atlas-queryable-encryption/actions/workflows/ci.yml/badge.svg)](https://github.com/adrianofratelli-glitch/atlas-queryable-encryption/actions/workflows/ci.yml)

Who can read customer identifiers in a conventional data platform? Frequently,
the answer includes database administrators, infrastructure teams, backup
operators, and the cloud provider. Encryption at rest and in transit does not
change that boundary: the database still decrypts the value to process it.

**MongoDB Queryable Encryption** encrypts a field with a customer-controlled key
while preserving equality, range, prefix, suffix, and substring queries. The server never sees plaintext at
rest, in transit, in use, in logs, or in backups.

This public overview is in English; the PoV interface and presentation-specific
documentation remain in Brazilian Portuguese.

## The PoV

One screen sends the same filter through **two clients against the same
collection**: an application client with automatic encryption and a regular
client representing the database administrator's view.

The encrypted application client finds the document and reads the identifier.
The regular client receives `Binary(subtype 6)` and finds **zero documents** when
filtering by the same plaintext value.

![Side-by-side identifier search through encrypted and regular clients](docs/screenshots/01-equality.png)

### Walkthrough

Captured against a live Atlas cluster (MongoDB 9.0) with synthetic data.

**Range query** — `$gte`/`$lte` over an encrypted salary field:

![Range query over an encrypted field](docs/screenshots/03-range.png)

**String query** — suffix match over an encrypted email; the regular client sees only `BinData`:

![Suffix query over an encrypted email](docs/screenshots/04-string-suffix.png)

**Plaintext control** — on an unencrypted field both clients return the same documents, so the difference above comes from encryption alone:

![Plaintext field control](docs/screenshots/05-plaintext-control.png)

**Randomized ciphertext** — the same identifier encrypts to two different ciphertexts:

![Same value, two distinct ciphertexts](docs/screenshots/06-randomized-pair.png)

Four options address the core objections:

| Action | What it proves |
|---|---|
| **Equality query** | A filter over an encrypted field works without deterministic ciphertext |
| **Range query** | `$gte`/`$lte` work over an encrypted field; range queries are GA in MongoDB 8.0 |
| **String query** | Choose a predefined prefix, suffix, or substring search over an encrypted email; MongoDB 9.0 + PyMongo 4.18+ + `pymongocrypt` 1.19+ |
| **State query** | The experimental control: both clients find the same plaintext field |

The **Show pair** action displays two different customers with the same
identifier and different ciphertexts. That distinction matters: identical
ciphertexts would let anyone holding a dump count repetitions and infer identity.

## How it differs from familiar controls

| Approach | Security and query behavior |
|---|---|
| TDE or encrypted disks | Protect data at rest; users with read credentials still see plaintext |
| Deterministic CSFLE | Enables equality because equal values produce equal ciphertext, which leaks frequency |
| `pgcrypto` or application encryption | Protects the value but removes the database's ability to filter it |
| **Queryable Encryption** | **Randomized, queryable ciphertext for equality, range, and selected string patterns, with keys outside the server** |

## Requirements

- MongoDB 7.0+ on Atlas M10 or above. Flex and free tiers are not supported.
- Prefix, suffix, and substring queries require MongoDB 9.0+, PyMongo 4.18+,
  `pymongocrypt` 1.19+, and the matching `crypt_shared` library.
  Range queries are generally available starting in MongoDB 8.0.
- Python 3.11+ and Node.js 20+.
- A KMS provider: local key file for the demo or AWS KMS for production.

## Setup

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # set MONGO_URI
cd ..

# Master key and crypt_shared library
python scripts/gerar-master-key.py     # 96 bytes in backend/secrets/, mode 0600
./scripts/instalar-crypt-shared.sh     # library → backend/lib/

# Key vault and data
python scripts/criar-cofre.py          # key-vault index and demo DEKs
python backend/seed_data.py            # 5,000 encrypted synthetic customers

# Frontend
cd frontend && npm install && cd ..
```

## Run it

```bash
./start.sh --foreground     # backend :8300 + frontend :5300
curl http://localhost:8300/preflight
```

The preflight checks `MONGO_URI`, cluster reachability, server version,
`crypt_shared`, the key vault, the collection, and the mutation-guard mode. This
prevents an incompatible server version from surfacing only as an unrelated
"unknown command" error. QE string queries require a MongoDB 9.0+ cluster.

The encrypted field map is immutable after collection creation. To add the
three string-query fields to an existing demo dataset, create the missing DEKs
with `python scripts/criar-cofre.py`, then rebuild the disposable demo
collection with `python backend/seed_data.py --drop`. On a cluster shared by
multiple PoVs, give this demo its own `QE_DB` and matching `QE_KEY_VAULT_NS`
instead of dropping an existing collection or reusing another demo's key vault.

## How it works

```text
React (frontend/, :5300) ──fetch──> FastAPI (backend/, :8300)
                                        │
                                        ├── ENCRYPTED MongoClient (AutoEncryptionOpts) ──> Atlas
                                        ├── REGULAR MongoClient (the DBA view)          ──> Atlas
                                        └── Local KMS or AWS KMS
```

The two clients in `backend/encryption.py` are the experiment, not an
implementation detail: the split UI renders their results side by side.

There is only one business collection. Both panels read `clientes`; only the
client changes. The adjacent `enxcol_.*` collections contain server-maintained
metadata that supports matching without revealing the values.

The driver encrypts the query value with the same DEK and sends ciphertext.
Plaintext never crosses the network.

## Tests

```bash
pytest                 # no cluster, crypt_shared, or KMS required
ruff check backend scripts
```

Every pull request runs the backend test suite, Ruff, and a dependency audit,
plus a clean frontend production build and npm audit. The suite uses MongoDB
stubs and requires no Atlas cluster, `crypt_shared` library, or KMS provider.

## Security boundaries

- The local master key is stored under `backend/secrets/` with mode `0600`, not
  in `.env`, and is excluded from version control. Local KMS is for demonstration;
  production deployments should use AWS KMS, Azure Key Vault, GCP KMS, or KMIP.
- No endpoint returns the master key, a decrypted DEK, or complete `keyMaterial`.
- Use a dedicated disposable PoV database and key vault, even when the Atlas
  cluster is shared by multiple demonstrations. Never point it at business data.
- The dataset is synthetic. Identifiers have valid check digits and use the
  non-issued `999` prefix; they do not belong to real people.

## License

MIT.
