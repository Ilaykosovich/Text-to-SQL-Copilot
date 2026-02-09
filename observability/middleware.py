import time
from observability.metrics import  *
from observability.logger import  *
import uuid
from fastapi import Request

from fastapi import APIRouter



router = APIRouter()


@router.middleware("http")
async def metrics_and_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    INFLIGHT.inc()

    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        INFLIGHT.dec()
        elapsed = time.perf_counter() - start

        endpoint = request.url.path
        method = request.method

        REQUESTS_TOTAL.labels(endpoint=endpoint, method=method, status=str(status_code)).inc()
        REQUEST_LATENCY.labels(endpoint=endpoint, method=method).observe(elapsed)
        log = logging.getLogger("orchestrator")
        log.info("request",
                 extra={
                        "request_id": request_id,
                        "method": method,
                        "path": endpoint,
                        "status": status_code,
                        "latency_s": round(elapsed, 4),
                    })