# MTN MoMo Record Keeper - Flask Backend with MySQL

from flask import Flask, request, render_template, session, redirect, url_for, send_file
from datetime import datetime
import mysql.connector
from mysql.connector import Error
import csv
import io
from functools import wraps
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# MySQL Configuration
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'mtn_momo_db'
}

# Demo agents (replace with real user management)
AGENTS = {
    'agent1': {'password': 'pass123', 'name': 'Agent One'},
    'agent2': {'password': 'pass123', 'name': 'Agent Two'},
}

def init_db():
    """Initialize MySQL database with records table."""
    try:
        conn = mysql.connector.connect(
            host=MYSQL_CONFIG['host'],
            user=MYSQL_CONFIG['user'],
            password=MYSQL_CONFIG['password']
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_CONFIG['database']}")
        cursor.close()
        conn.close()
        
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                date DATETIME NOT NULL,
                phone VARCHAR(20) NOT NULL,
                type VARCHAR(20) NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                agent VARCHAR(50) NOT NULL,
                reference VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        cursor.close()
        conn.close()
        print("MySQL database initialized successfully")
    except Error as e:
        print(f"Database error: {e}")

def get_db():
    """Get MySQL database connection."""
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        return conn
    except Error as e:
        print(f"Connection error: {e}")
        return None

def login_required(f):
    """Decorator to require login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============ AUTH ROUTES ============
@app.route('/')
def index():
    """Redirect to login or dashboard."""
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and handler."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if username in AGENTS and AGENTS[username]['password'] == password:
            session['username'] = username
            session['agent_name'] = AGENTS[username]['name']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout handler."""
    session.clear()
    return redirect(url_for('login'))

# ============ DASHBOARD & RECORDS ============
@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard with records list."""
    search = request.args.get('search', '').strip()
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    agent_filter = request.args.get('agent', '')
    
    conn = get_db()
    if not conn:
        return "Database connection error", 500
    
    cursor = conn.cursor(dictionary=True)
    
    query = 'SELECT * FROM records WHERE 1=1'
    params = []
    
    if agent_filter:
        query += ' AND agent = %s'
        params.append(agent_filter)
    
    if from_date:
        query += ' AND DATE(date) >= %s'
        params.append(from_date)
    
    if to_date:
        query += ' AND DATE(date) <= %s'
        params.append(to_date)
    
    if search:
        query += ' AND (phone LIKE %s OR reference LIKE %s OR agent LIKE %s)'
        search_term = f'%{search}%'
        params.extend([search_term, search_term, search_term])
    
    query += ' ORDER BY date DESC'
    cursor.execute(query, params)
    records = cursor.fetchall()
    
    # Get unique agents for filter dropdown
    cursor.execute('SELECT DISTINCT agent FROM records ORDER BY agent')
    agents = [row['agent'] for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    
    return render_template('dashboard.html',
                         agent_name=session.get('agent_name'),
                         records=records,
                         agents=agents,
                         search=search,
                         from_date=from_date,
                         to_date=to_date,
                         agent_filter=agent_filter)

@app.route('/add-record', methods=['GET', 'POST'])
@login_required
def add_record():
    """Add new record."""
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        amount = request.form.get('amount', '0')
        type_ = request.form.get('type', 'deposit')
        reference = request.form.get('reference', '').strip()
        
        if not phone or float(amount) <= 0:
            return render_template('add_record.html', error='Invalid input'), 400
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO records (date, phone, type, amount, agent, reference)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (datetime.now(), phone, type_, float(amount), session['username'], reference))
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('dashboard'))
        except Error as e:
            print(f"Error: {e}")
            return render_template('add_record.html', error=f'Database error: {e}'), 500
    
    return render_template('add_record.html')

@app.route('/delete-record/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    """Delete a record."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM records WHERE id = %s', (record_id,))
        conn.commit()
        cursor.close()
        conn.close()
    except Error as e:
        print(f"Error: {e}")
    
    return redirect(url_for('dashboard'))

# ============ REPORTS ============
@app.route('/reports')
@login_required
def reports():
    """Reports page."""
    conn = get_db()
    if not conn:
        return "Database connection error", 500
    
    cursor = conn.cursor(dictionary=True)
    
    # Get unique agents for filter
    cursor.execute('SELECT DISTINCT agent FROM records ORDER BY agent')
    agents = [row['agent'] for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    
    return render_template('reports.html', agents=agents)

@app.route('/api/report-summary')
@login_required
def get_report_summary():
    """Get report summary stats."""
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    agent_filter = request.args.get('agent', '')
    
    conn = get_db()
    if not conn:
        return {}, 500
    
    cursor = conn.cursor(dictionary=True)
    
    query = 'SELECT type, COUNT(*) as count, SUM(amount) as total FROM records WHERE 1=1'
    params = []
    
    if agent_filter:
        query += ' AND agent = %s'
        params.append(agent_filter)
    
    if from_date:
        query += ' AND DATE(date) >= %s'
        params.append(from_date)
    
    if to_date:
        query += ' AND DATE(date) <= %s'
        params.append(to_date)
    
    query += ' GROUP BY type'
    cursor.execute(query, params)
    summary = {row['type']: {'count': row['count'], 'total': row['total']} for row in cursor.fetchall()}
    
    cursor.close()
    conn.close()
    
    return summary

@app.route('/export-csv')
@login_required
def export_csv():
    """Export records as CSV."""
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    agent_filter = request.args.get('agent', '')
    
    conn = get_db()
    if not conn:
        return "Database connection error", 500
    
    cursor = conn.cursor(dictionary=True)
    
    query = 'SELECT * FROM records WHERE 1=1'
    params = []
    
    if agent_filter:
        query += ' AND agent = %s'
        params.append(agent_filter)
    
    if from_date:
        query += ' AND DATE(date) >= %s'
        params.append(from_date)
    
    if to_date:
        query += ' AND DATE(date) <= %s'
        params.append(to_date)
    
    query += ' ORDER BY date DESC'
    cursor.execute(query, params)
    records = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    if not records:
        return "No records found", 404
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'date', 'phone', 'type', 'amount', 'agent', 'reference'])
    
    for row in records:
        writer.writerow([
            row['id'],
            row['date'],
            row['phone'],
            row['type'],
            row['amount'],
            row['agent'],
            row['reference'] or ''
        ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'momo-report-{datetime.now().strftime("%Y%m%d")}.csv'
    )

if __name__ == '__main__':
    init_db()
    print("Starting MTN MoMo Record Keeper Flask app...")
    print("Open http://127.0.0.1:5000/ in your browser")
    print("MySQL Configuration: host=localhost, user=root, password=root")

    app.run(debug=True, host='127.0.0.1', port=5000)
