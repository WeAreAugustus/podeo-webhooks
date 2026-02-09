import logging
import sys
from logging.handlers import RotatingFileHandler
from os import environ, makedirs, path

LOG_DIR = environ.get("LOG_DIR", "")
LOG_FILE = path.join(LOG_DIR, "flask.log") if LOG_DIR else "flask.log"
LOGGER_NAME = "flask_app"

_FORMAT = "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"


def _create_logger():
    logger = logging.getLogger(LOGGER_NAME)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(_FORMAT)

    # File handler
    if LOG_DIR and not path.isdir(LOG_DIR):
        makedirs(LOG_DIR, exist_ok=True)
    if not path.exists(LOG_FILE):
        open(LOG_FILE, "a").close()
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler (stdout) so processes show in terminal / docker compose logs
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.propagate = False

    return logger


# 🚀 GLOBAL LOGGER INSTANCE
logger = _create_logger()
