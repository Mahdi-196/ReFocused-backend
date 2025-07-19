from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "refocused",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks"]
)

# Register the data export task
@celery_app.task(bind=True)
def export_user_data_task(self, user_id: int):
    """Celery task wrapper for data export functionality."""
    try:
        from app.tasks.data_export import export_user_data_task_function
        return export_user_data_task_function(user_id)
    except Exception as e:
        # Retry logic for failed tasks
        raise self.retry(exc=e, countdown=60, max_retries=3)



# Optional configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

if __name__ == '__main__':
    celery_app.start() 