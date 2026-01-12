# tasks.py
from celery import Celery
import time
import random

# Configure Celery
celery_app = Celery(
    'tasks',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/0'
)

@celery_app.task(name='tasks.process_data')
def process_data(user_id, data):
    """
    Simulates a long-running task
    In real app: image processing, email sending, report generation, etc.
    """
    print(f"🔄 Starting task for user {user_id}...")
    
    # Simulate processing (3-10 seconds)
    processing_time = random.randint(3, 10)
    time.sleep(processing_time)
    
    result = {
        'user_id': user_id,
        'data': data,
        'processing_time': processing_time,
        'status': 'completed'
    }
    
    print(f"✅ Task completed for user {user_id} in {processing_time}s")
    return result

@celery_app.task(name='tasks.send_email')
def send_email(email, subject, message):
    """
    Simulates sending email
    """
    print(f"📧 Sending email to {email}...")
    time.sleep(2)  # Simulate email sending
    print(f"✅ Email sent to {email}")
    return {'email': email, 'status': 'sent'}

@celery_app.task(name='tasks.generate_report')
def generate_report(user_id):
    """
    Simulates report generation
    """
    print(f"📊 Generating report for user {user_id}...")
    time.sleep(5)  # Simulate report generation
    print(f"✅ Report generated for user {user_id}")
    return {'user_id': user_id, 'report': 'monthly_report.pdf'}