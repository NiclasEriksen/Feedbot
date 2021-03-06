import logging
from logging.handlers import RotatingFileHandler
from .helpers import program_path

#Logging
log = logging.getLogger("feedbot")
log.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    "%(levelname)s|%(asctime)s|%(name)s| %(message)s",
    "%Y-%m-%d %H:%M:%S"
)

log_handler = RotatingFileHandler(program_path("debug.log"), maxBytes=8*1024*1024, backupCount=2, encoding="utf-8")
log_handler.setLevel(logging.DEBUG)
log_handler.setFormatter(formatter)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)

log.addHandler(log_handler)
log.addHandler(stream_handler)

from .discord import *

