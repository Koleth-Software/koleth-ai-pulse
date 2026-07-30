from __future__ import annotations

import re

from fastapi import FastAPI, HTTPException


def redact_error(value: str) -> str:
    value = re.sub(r"(postgres(?:ql)?://)([^@\s]+)@", r"\1***@", value)
    value = re.sub(r"(Bearer\s+)[A-Za-z0-9_.-]+", r"\1***", value)
    return value[:1000]


try:
    from api.main import app
except Exception as exc:  # pragma: no cover - only used in deployed import failures.
    import_error_type = type(exc).__name__
    import_error_detail = redact_error(str(exc))
    app = FastAPI(title="Koleth AI Pulse API")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "import_error",
            "error_type": import_error_type,
            "detail": import_error_detail,
        }

    @app.get("/{path:path}")
    def import_failed(path: str) -> None:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Koleth AI Pulse API import failed",
                "path": path,
                "error_type": import_error_type,
                "detail": import_error_detail,
            },
        )
