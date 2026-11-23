"""Logs estructurados en JSON con lista blanca de campos."""

import json
import logging
from datetime import UTC, datetime

# Atributos del `LogRecord` (pasados con `extra=`) que se serializan, además de
# timestamp, level y logger. Todo lo demás se descarta, incluidos el mensaje y la
# excepción: así un log no puede arrastrar datos de la petición por descuido.
LOG_FIELDS = (
    "request_id",
    "method",
    "route",
    "status",
    "duration_ms",
    "traceback",
)


class JsonFormatter(logging.Formatter):
    """Una línea JSON por registro, solo con los campos de la lista blanca."""

    def __init__(self, fields: tuple[str, ...] = LOG_FIELDS) -> None:
        super().__init__()
        self._fields = fields

    def format(self, record: logging.LogRecord) -> str:
        moment = datetime.fromtimestamp(record.created, UTC)
        line: dict[str, object] = {
            "timestamp": moment.strftime("%Y-%m-%dT%H:%M:%S")
            + f".{moment.microsecond // 1000:03d}Z",
            "level": record.levelname,
            "logger": record.name,
        }
        for field in self._fields:
            if hasattr(record, field):
                line[field] = getattr(record, field)
        return json.dumps(line, ensure_ascii=False, default=str)
