from psycopg.errors import Error as PsycopgError


def format_pg_error(e: Exception) -> str:
    """
    Extract detailed, human-readable PostgreSQL error information.
    Compatible with psycopg v3.
    """
    if isinstance(e, PsycopgError):
        parts = []

        # SQLSTATE
        if getattr(e, "sqlstate", None):
            parts.append(f"SQLSTATE: {e.sqlstate}")

        # Primary error message
        if getattr(e, "message", None):
            parts.append(f"message: {e.message}")

        # Diagnostic fields (similar to psycopg2.diag)
        diag = getattr(e, "diag", None)
        if diag:
            for field in [
                "message_primary",
                "message_detail",
                "message_hint",
                "schema_name",
                "table_name",
                "column_name",
                "constraint_name",
                "context",
            ]:
                value = getattr(diag, field, None)
                if value:
                    parts.append(f"{field}: {value}")

        return " | ".join(parts)

    return str(e)
