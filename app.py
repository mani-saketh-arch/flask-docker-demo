from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import psycopg2.extras
import os
import time
from tasks import process_data, send_email, generate_report  # Import tasks
from celery.result import AsyncResult
from tasks import celery_app

app = Flask(__name__)

# Configuration
class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-CHANGE-THIS')
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:password@db:5432/flaskdb')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    
app.config.from_object(Config)

# Database connection with retry
def get_db():
    max_retries = 5
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(app.config['DATABASE_URL'])
            return conn
        except psycopg2.OperationalError as e:
            if attempt < max_retries - 1:
                print(f"⏳ Database not ready (attempt {attempt + 1}/{max_retries}). Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                print(f"❌ Failed to connect after {max_retries} attempts")
                raise e

# Initialize database
def init_db():
    print("🔄 Initializing database...")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Database initialized!")

# Health check endpoint (for monitoring)
@app.route('/health')
def health():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        conn.close()
        return {
            'status': 'healthy',
            'database': 'connected',
            'environment': app.config['FLASK_ENV']
        }, 200
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e)
        }, 503

@app.route('/')
def home():
    if 'username' in session:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT COUNT(*) as total_users FROM users')
        stats = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return render_template('dashboard.html', 
                             username=session['username'],
                             total_users=stats['total_users'])
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        cursor = conn.cursor()
        try:
            hashed_password = generate_password_hash(password)
            cursor.execute('INSERT INTO users (username, password) VALUES (%s, %s)', 
                         (username, hashed_password))
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            cursor.close()
            conn.close()
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            conn.rollback()
            flash('Username already exists', 'error')
        finally:
            cursor.close()
            conn.close()
    
    return render_template('register.html')

@app.route('/users')
def users():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute('SELECT id, username, created_at FROM users ORDER BY created_at DESC')
    all_users = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('users.html', users=all_users)

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))



# Add this new route for background tasks demo
@app.route('/tasks-demo')
def tasks_demo():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('tasks.html', username=session['username'])

@app.route('/start-task', methods=['POST'])
def start_task():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    task_type = request.json.get('task_type', 'process_data')
    username = session['username']
    
    # Start background task
    if task_type == 'process_data':
        task = process_data.delay(username, {'sample': 'data'})
    elif task_type == 'send_email':
        task = send_email.delay(f'{username}@example.com', 'Hello', 'Test message')
    elif task_type == 'generate_report':
        task = generate_report.delay(username)
    else:
        return jsonify({'error': 'Invalid task type'}), 400
    
    return jsonify({
        'task_id': task.id,
        'status': 'started',
        'message': f'{task_type} started in background'
    })

@app.route('/task-status/<task_id>')
def task_status(task_id):
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    task = AsyncResult(task_id, app=celery_app)
    
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'status': 'Task is waiting to be processed...'
        }
    elif task.state == 'STARTED':
        response = {
            'state': task.state,
            'status': 'Task is being processed...'
        }
    elif task.state == 'SUCCESS':
        response = {
            'state': task.state,
            'status': 'Task completed!',
            'result': task.result
        }
    elif task.state == 'FAILURE':
        response = {
            'state': task.state,
            'status': 'Task failed',
            'error': str(task.info)
        }
    else:
        response = {
            'state': task.state,
            'status': str(task.info)
        }
    
    return jsonify(response)


@app.route('/about')
def about():
    return render_template('about.html')
    
# Only run init_db in development or when explicitly needed
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
else:
    # Running with Gunicorn
    init_db()