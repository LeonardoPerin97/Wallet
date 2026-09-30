from django.db import connection
from django.http import HttpResponse


def healthz(request):
    """Northflank readiness endpoint; verifies the configured database is reachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return HttpResponse("ok", content_type="text/plain; charset=utf-8")
    except Exception:
        return HttpResponse(
            "database non disponibile",
            status=503,
            content_type="text/plain; charset=utf-8",
        )
