import logging
import os
from config import settings


LOG_PATH = os.path.join(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    ),
    "logs",
    "bot.log"
)


def setup_logger():

    os.makedirs(
        os.path.dirname(LOG_PATH),
        exist_ok=True
    )

    logging.basicConfig(
        level=getattr(
            logging,
            settings.LOG_LEVEL.upper(),
            logging.INFO
        ),
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH),
            logging.StreamHandler()
        ]
    )

    return logging.getLogger("VeryRareBot")
