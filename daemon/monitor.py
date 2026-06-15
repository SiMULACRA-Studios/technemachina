from datetime import datetime, timezone
from brain_router import route
from audit_log import write_event

def check_brain_health(provider: str = "gemini") -> dict:
    started = datetime.now(timezone.utc)

    try:
        response = route(
            "Health check. Reply with exactly: ONLINE",
            provider=provider
        )

        ended = datetime.now(timezone.utc)
        latency_ms = int((ended - started).total_seconds() * 1000)

        healthy = "ONLINE" in response.upper()

        status = "green" if healthy and latency_ms < 5000 else "yellow"

        result = {
            "provider": provider,
            "status": status,
            "latency_ms": latency_ms,
            "detail": response.strip()
        }

        write_event(
            "brain_health_check",
            "success",
            provider=provider,
            detail=f"{status} | {latency_ms}ms"
        )

        return result

    except Exception as e:
        write_event(
            "brain_health_check",
            "failed",
            provider=provider,
            detail=str(e)
        )

        return {
            "provider": provider,
            "status": "red",
            "latency_ms": None,
            "detail": str(e)
        }
