import logging
import re
import threading
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from encryption import (
    COLECAO_CIFRADA,
    cliente_claro,
    fechar_clientes,
    readiness,
    versao_servidor,
)
from routers import demo
from security import ApiHardeningMiddleware, MutationGuardMiddleware
from settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("qe.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        yield
    finally:
        fechar_clientes()


app = FastAPI(title="Atlas Queryable Encryption", version="1.0.0", lifespan=lifespan)
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

app.add_middleware(ApiHardeningMiddleware)
app.add_middleware(MutationGuardMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Demo-Token", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied_request_id = request.headers.get("x-request-id", "")
    request_id = supplied_request_id if REQUEST_ID_RE.fullmatch(supplied_request_id) else uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail": "Parâmetros inválidos.", "errors": exc.errors()}),
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    # Driver/validation exceptions can embed documents in their message. Keep
    # correlation and exception type without logging plaintext or chained errors.
    logger.error("Falha não tratada request_id=%s type=%s", request_id, type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "Falha interna na demonstração.", "request_id": request_id},
    )


app.include_router(demo.router)


@app.get("/")
def root():
    return {"status": "ok", "poc": "Atlas Queryable Encryption", "version": app.version}


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    ok, message = readiness()
    return JSONResponse(status_code=200 if ok else 503, content={"ready": ok, "message": message})


_PREFLIGHT_CACHE_TTL_S = 8.0
_preflight_cache_lock = threading.Lock()
_preflight_cache: dict | None = None
_preflight_cache_ts: float = 0.0


@app.get("/preflight")
def preflight():
    # O frontend chama /preflight a cada montagem de <SeloPreflight /> (comum em
    # StrictMode e em refresh rápido durante demo), e cada chamada roda buildInfo,
    # list_collection_names e contagens no keyVault — comandos admin baratos
    # isoladamente, mas sem motivo para repetir a cada re-render. TTL curto: cache
    # "morno" o suficiente para não martelar o cluster, curto o suficiente para o
    # selo continuar refletindo o estado real da demo em segundos.
    global _preflight_cache, _preflight_cache_ts
    with _preflight_cache_lock:
        agora = time.monotonic()
        if _preflight_cache is not None and (agora - _preflight_cache_ts) < _PREFLIGHT_CACHE_TTL_S:
            return _preflight_cache

    resposta = _preflight_sem_cache()

    with _preflight_cache_lock:
        _preflight_cache = resposta
        _preflight_cache_ts = time.monotonic()
    return resposta


def _preflight_sem_cache():
    mongo_ok, mongo_message = readiness()
    checks = {
        "mongo_uri": {"ok": bool(settings.mongo_uri), "message": "configurada" if settings.mongo_uri else "ausente"},
        "mongodb": {"ok": mongo_ok, "message": mongo_message},
        "crypt_shared": {
            "ok": settings.crypt_shared_disponivel,
            "message": (
                "carregada" if settings.crypt_shared_disponivel
                else "ausente — rode scripts/instalar-crypt-shared.sh"
            ),
        },
        "mutation_guard": {
            "ok": True,
            "message": "token obrigatório" if settings.demo_admin_token else "somente localhost/origens permitidas",
        },
    }

    if mongo_ok:
        maior, menor, versao = versao_servidor()
        # Sem esta checagem o erro que aparece é de comando desconhecido, e ele
        # não menciona versão nem Queryable Encryption em lugar nenhum.
        checks["versao_servidor"] = {
            "ok": maior >= 7,
            "message": f"MongoDB {versao}" + ("" if maior >= 7 else " — Queryable Encryption exige 7.0+"),
        }
        checks["range_ga"] = {
            "ok": maior >= 8,
            "message": f"MongoDB {versao}" + ("" if maior >= 8 else " — consulta por faixa é GA a partir do 8.0"),
        }
        checks.update(demo.preflight_checks())
        nomes = set(cliente_claro()[settings.mongo_db].list_collection_names())
        for colecao in (COLECAO_CIFRADA,):
            checks[f"collection_{colecao}"] = {
                "ok": colecao in nomes,
                "message": "disponível" if colecao in nomes else "execute seed_data.py",
            }

    # `range_ga` é informativo: em 7.0 a PoV roda com igualdade e o módulo 03
    # degrada a faixa, em vez de reprovar o pré-voo inteiro.
    opcionais = {"range_ga"}
    ready = all(check["ok"] for chave, check in checks.items() if chave not in opcionais)
    return JSONResponse(status_code=200 if ready else 503, content={"ready": ready, "checks": checks})


@app.get("/stats")
def stats():
    db = cliente_claro()[settings.mongo_db]
    return {
        "db": settings.mongo_db,
        "clientes": db[COLECAO_CIFRADA].estimated_document_count(),
        "kms": settings.kms_provider,
        "qe_pronto": settings.qe_configured,
    }
