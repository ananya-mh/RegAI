from backend.ingestion.gdpr import ingest_gdpr, parse_gdpr_html
from backend.ingestion.soc2 import ingest_soc2, parse_soc2_text

__all__ = [
    "ingest_gdpr",
    "ingest_soc2",
    "parse_gdpr_html",
    "parse_soc2_text",
]
