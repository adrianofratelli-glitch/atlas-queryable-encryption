#!/bin/sh
set -e

# The image ships the Linux crypt_shared; a CRYPT_SHARED_PATH copied from a
# host .env points to a macOS .dylib or to backend/lib/, which is not in the
# image. Always use the bundled library.
export CRYPT_SHARED_PATH=/opt/mongo-crypt/mongo_crypt_v1.so

cd /app/backend
# One worker only: the preflight cache, the DEK keyId and the search executor
# are in-process state.
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 &
nginx -g 'daemon off;'
