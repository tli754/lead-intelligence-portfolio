"""RQ worker entrypoint. Run with:
    .venv/bin/python -m app.worker
Processes jobs for every queue this repository has adopted RQ for.
Crawling was first (Task 017); discovery is second (Task 020). Add a
queue name here when extraction adopts RQ per ADR 0004 — one queue
name per module, added to this same list, not a second worker script.
"""

from rq import Worker

from app.queue import get_redis_connection

QUEUE_NAMES = ["crawling", "discovery"]

if __name__ == "__main__":
    Worker(QUEUE_NAMES, connection=get_redis_connection()).work()
