#!/usr/bin/env bash
# Baixa a biblioteca crypt_shared para backend/lib/.
#
# Auto-encryption precisa da biblioteca de criptografia do lado do cliente.
# Existem dois caminhos e só um é usado aqui:
#
#   crypt_shared  — biblioteca dinâmica carregada no processo. Sem processo
#                   extra, sem porta, sem ciclo de vida. É este.
#   mongocryptd   — binário separado que o driver sobe sozinho em :27020.
#                   Funciona, e deixa um processo órfão que sobrevive ao backend
#                   e falha de um jeito que parece problema de rede.
#
# A URL é RESOLVIDA no feed oficial (downloads.mongodb.org/current.json), nunca
# montada à mão: o nome do arquivo carrega a edição ("-enterprise-") e um palpite
# errado devolve 403 do S3, que não parece "versão inexistente" em nada.
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINO="$BASE/backend/lib"
FEED="${MONGO_DOWNLOADS_FEED:-https://downloads.mongodb.org/current.json}"

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)  ALVO="macos";  ARCH="arm64";   EXT="dylib" ;;
  Darwin-x86_64) ALVO="macos";  ARCH="x86_64";  EXT="dylib" ;;
  Linux-x86_64)  ALVO="rhel93"; ARCH="x86_64";  EXT="so" ;;
  Linux-aarch64) ALVO="rhel93"; ARCH="aarch64"; EXT="so" ;;
  *) echo "❌ Plataforma não mapeada: $(uname -s)-$(uname -m)." >&2; exit 1 ;;
esac

command -v python3 >/dev/null || { echo "❌ python3 não encontrado." >&2; exit 1; }

echo "▶ Resolvendo crypt_shared para ${ALVO}/${ARCH}…"
LEITURA="$(curl --fail --location --silent --show-error --max-time 60 "$FEED" \
  | MONGO_ALVO="$ALVO" MONGO_ARCH="$ARCH" python3 -c '
import json, os, sys
alvo, arch = os.environ["MONGO_ALVO"], os.environ["MONGO_ARCH"]
desejada = os.environ.get("MONGO_CRYPT_VERSION", "")
feed = json.load(sys.stdin)
for versao in feed["versions"]:
    if desejada and versao["version"] != desejada:
        continue
    for download in versao["downloads"]:
        if (download.get("target") == alvo and download.get("arch") == arch
                and download.get("edition") == "enterprise" and download.get("crypt_shared")):
            print(versao["version"], download["crypt_shared"]["url"], download["crypt_shared"]["sha256"])
            raise SystemExit(0)
raise SystemExit("sem crypt_shared publicada para esta plataforma")
')" || { echo "❌ Não achei crypt_shared para ${ALVO}/${ARCH}." >&2; exit 1; }

read -r VERSAO URL SHA256 <<< "$LEITURA"
echo "  versão ${VERSAO}"

mkdir -p "$DESTINO"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

curl --fail --location --progress-bar "$URL" -o "$TMP/crypt.tgz"

# O feed publica o sha256; não confie em download de biblioteca de criptografia
# sem conferir. Um tarball truncado descompacta e a falha só aparece no dlopen.
BAIXADO="$(shasum -a 256 "$TMP/crypt.tgz" | cut -d' ' -f1)"
[[ "$BAIXADO" == "$SHA256" ]] || { echo "❌ sha256 divergente. Esperado $SHA256, obtido $BAIXADO." >&2; exit 1; }
echo "  sha256 conferido"

tar -xzf "$TMP/crypt.tgz" -C "$TMP"
BIBLIOTECA="$(find "$TMP" -name "mongo_crypt_v1.${EXT}" -print -quit)"
[[ -n "$BIBLIOTECA" ]] || { echo "❌ mongo_crypt_v1.${EXT} não veio no pacote." >&2; exit 1; }

cp "$BIBLIOTECA" "$DESTINO/"
echo "✅ $DESTINO/mongo_crypt_v1.${EXT}"
echo "   CRYPT_SHARED_PATH=$DESTINO/mongo_crypt_v1.${EXT}"
