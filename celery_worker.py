# celery_worker.py
from tasks import celery_app

# This file is used to start the Celery worker
if __name__ == '__main__':
    celery_app.start()