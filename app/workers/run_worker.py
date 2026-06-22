from __future__ import annotations

import logging

from config.settings import get_settings

logger = logging.getLogger("qualiflow.worker")


def main() -> None:
    settings = get_settings()
    from redis import Redis
    from rq import Worker

    redis_conn = Redis.from_url(settings.redis_url)
    logger.info("Starting RQ worker queue=%s redis=%s", settings.rq_queue_name, settings.redis_url)
    worker = Worker([settings.rq_queue_name], connection=redis_conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
