from pythonjsonlogger import jsonlogger
from logging.handlers import RotatingFileHandler
import logging

def setup_logger(name: str = "orchestrator") -> None:
    logger = logging.getLogger(name)
    if logger.handlers:
        return

    logger.setLevel(logging.INFO)

    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(message)s"
    )

    # stdout (как сейчас)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = RotatingFileHandler(
        filename="logs/orchestrator.log",
        maxBytes=10_000_000,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
