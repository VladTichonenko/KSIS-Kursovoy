from flask import Flask, render_template, request, session, jsonify, redirect, url_for, flash, g
from flask_socketio import SocketIO, emit
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from datetime import datetime
from threading import Lock

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
socketio = SocketIO(app, cors_allowed_origins="*")

# Конфигурация базы данных
DATABASE = 'logiconnect.db'

# Для чата
chat_users = {}
chat_lock = Lock()

# Константы для админ-панели
ADMIN_USERNAME = 'admin'
ADMIN_PIN = '1111'
ONLINE_THRESHOLD_MINUTES = 1  # Исправленная константа

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Создаем таблицу users, если ее нет
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                full_name TEXT NOT NULL UNIQUE,
                pin_code TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP
            )
        ''')
        
        # Создаем таблицу orders, если ее нет
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                cargo_type TEXT NOT NULL,
                weight REAL NOT NULL,
                dimensions TEXT NOT NULL,
                from_location TEXT NOT NULL,
                to_location TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Создаем таблицу chat_messages, если ее нет
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                message TEXT NOT NULL,
                chat_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.before_request
def update_last_activity():
    if 'user_id' in session:
        db = get_db()
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute(
            'UPDATE users SET last_activity = ? WHERE id = ?',
            (current_time, session['user_id'])
        )
        db.commit()

@app.route('/')
def index():
    return render_template('glav.html')

@app.route('/login', methods=['POST'])
def login():
    full_name = request.form.get('fullName')
    pin_code = ''.join([
        request.form.get('pin1', ''),
        request.form.get('pin2', ''),
        request.form.get('pin3', ''),
        request.form.get('pin4', '')
    ])

    if not full_name or len(pin_code) != 4 or not pin_code.isdigit():
        flash('Пожалуйста, заполните все поля корректно', 'error')
        return redirect(url_for('index'))

    if full_name == ADMIN_USERNAME and pin_code == ADMIN_PIN:
        session['admin_logged_in'] = True
        return redirect(url_for('admin_dashboard'))

    db = get_db()
    user = db.execute(
        'SELECT * FROM users WHERE full_name = ? AND pin_code = ?',
        (full_name, pin_code)
    ).fetchone()

    if user is None:
        flash('Неверные ФИО или PIN-код', 'error')
        return redirect(url_for('index'))

    session['user_id'] = user['id']
    session['user_name'] = user['full_name']
    flash('Вы успешно вошли в систему', 'success')
    return redirect(url_for('dashboard'))

@app.route('/register', methods=['POST'])
def register():
    ip_address = request.form.get('ipAddress')
    full_name = request.form.get('fullName')
    pin_code = ''.join([
        request.form.get('pin1', ''),
        request.form.get('pin2', ''),
        request.form.get('pin3', ''),
        request.form.get('pin4', '')
    ])

    if not ip_address or not full_name or len(pin_code) != 4 or not pin_code.isdigit():
        flash('Пожалуйста, заполните все поля корректно', 'error')
        return redirect(url_for('index'))

    db = get_db()
    try:
        existing_user = db.execute(
            'SELECT * FROM users WHERE full_name = ?',
            (full_name,)
        ).fetchone()
        if existing_user:
            flash('Пользователь с таким ФИО уже существует', 'error')
            return redirect(url_for('index'))
        db.execute(
            'INSERT INTO users (ip_address, full_name, pin_code) VALUES (?, ?, ?)',
            (ip_address, full_name, pin_code)
        )
        db.commit()
        flash('Регистрация прошла успешно! Теперь вы можете войти.', 'success')
    except Exception as e:
        flash(f'Ошибка при регистрации: {str(e)}', 'error')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    orders = db.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC',
                        (session['user_id'],)).fetchall()
    return render_template('dashboard.html', user=user, orders=orders)

@app.route('/create_order', methods=['POST'])
def create_order():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    cargo_type = request.form.get('cargo_type')
    weight = request.form.get('weight')
    dimensions = request.form.get('dimensions')
    from_location = request.form.get('from_location')
    to_location = request.form.get('to_location')
    if not all([cargo_type, weight, dimensions, from_location, to_location]):
        flash('Пожалуйста, заполните все поля', 'error')
        return redirect(url_for('dashboard'))
    db = get_db()
    db.execute(
        'INSERT INTO orders (user_id, cargo_type, weight, dimensions, from_location, to_location) VALUES (?, ?, ?, ?, ?, ?)',
        (session['user_id'], cargo_type, weight, dimensions, from_location, to_location)
    )
    db.commit()
    flash('Заказ успешно создан!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    return render_template('profile.html', user=user)

@app.route('/update_ip', methods=['POST'])
def update_ip():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Необходима авторизация'})
    data = request.get_json()
    new_ip = data.get('ip')
    if not new_ip:
        return jsonify({'success': False, 'message': 'Не указан IP-адрес'})
    db = get_db()
    try:
        db.execute(
            'UPDATE users SET ip_address = ? WHERE id = ?',
            (new_ip, session['user_id'])
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/update_pin', methods=['POST'])
def update_pin():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Необходима авторизация'})
    data = request.get_json()
    current_pin = data.get('currentPin')
    new_pin = data.get('newPin')
    if not current_pin or not new_pin or len(new_pin) != 4:
        return jsonify({'success': False, 'message': 'Некорректные данные'})
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user['pin_code'] != current_pin:
        return jsonify({'success': False, 'message': 'Неверный текущий PIN-код'})
    try:
        db.execute(
            'UPDATE users SET pin_code = ? WHERE id = ?',
            (new_pin, session['user_id'])
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы успешно вышли из системы', 'success')
    return redirect(url_for('index'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

@app.context_processor
def inject_user():
    if 'user_id' in session:
        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE id = ?', 
            (session['user_id'],)
        ).fetchone()
        return {'user': user}
    return {}

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('index'))
    db = get_db()
    orders = db.execute('''
        SELECT o.*, u.full_name 
        FROM orders o 
        JOIN users u ON o.user_id = u.id 
        ORDER BY o.created_at DESC
    ''').fetchall()
    threshold_time = (datetime.now() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')
    users = db.execute('''
        SELECT *, 
               CASE WHEN last_activity >= ? THEN 1 ELSE 0 END as is_online
        FROM users
        WHERE full_name != ?
        ORDER BY last_activity DESC
    ''', (threshold_time, ADMIN_USERNAME)).fetchall()
    return render_template('admin_dashboard.html', orders=orders, users=users)

@app.route('/admin/update_order_status', methods=['POST'])
def update_order_status():
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': 'Не авторизован'})
    data = request.get_json()
    order_id = data.get('order_id')
    new_status = data.get('new_status')
    if not order_id or not new_status:
        return jsonify({'success': False, 'message': 'Неверные данные'})
    db = get_db()
    try:
        db.execute(
            'UPDATE orders SET status = ? WHERE id = ?',
            (new_status, order_id)
        )
        db.commit()
        updated_order = db.execute(
            'SELECT o.*, u.full_name FROM orders o JOIN users u ON o.user_id = u.id WHERE o.id = ?',
            (order_id,)
        ).fetchone()
        return jsonify({
            'success': True,
            'order': dict(updated_order),
            'status_text': get_status_text(new_status)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# Новые маршруты для чата
@app.route('/chat/general')
def general_chat():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    return render_template('chatapp.html', 
                         chat_type='general',
                         user=user)


@app.route('/chat/support')
def support_chat():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    return render_template('chatapp.html', 
                         chat_type='support',
                         user=user)


# SocketIO обработчики
@socketio.on('connect')
def handle_connect():
    if 'user_id' not in session:
        return False
    
    with chat_lock:
        chat_users[request.sid] = {
            'username': session.get('user_name'),
            'user_id': session.get('user_id')
        }
    
    emit('user_joined', {
        'username': session.get('user_name'),
        'user_id': session.get('user_id')
    }, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    with chat_lock:
        if request.sid in chat_users:
            user = chat_users.pop(request.sid)
            emit('user_left', {
                'username': user['username'],
                'user_id': user['user_id']
            }, broadcast=True)

@socketio.on('message')
def handle_message(data):
    if 'user_id' not in session:
        return
    
    user = chat_users.get(request.sid)
    if user and 'text' in data:
        message_data = {
            'username': user['username'],
            'user_id': user['user_id'],
            'text': data['text'],
            'timestamp': datetime.now().isoformat(),
            'chat_type': data.get('chat_type', 'general')
        }
        
        # Сохраняем сообщение в БД
        db = get_db()
        db.execute(
            'INSERT INTO chat_messages (user_id, username, message, chat_type, timestamp) VALUES (?, ?, ?, ?, ?)',
            (user['user_id'], user['username'], data['text'], message_data['chat_type'], message_data['timestamp'])
        )
        db.commit()
        
        # Отправляем сообщение всем
        emit('message', message_data, broadcast=True)



# API для получения сообщений
@app.route('/get_messages')
def get_messages():
    if 'user_id' not in session:
        return jsonify([])
    
    chat_type = request.args.get('chat_type', 'general')
    last_timestamp = request.args.get('last', '1970-01-01T00:00:00')
    
    try:
        db = get_db()
        messages = db.execute(
            'SELECT * FROM chat_messages WHERE chat_type = ? AND timestamp > ? ORDER BY timestamp ASC',
            (chat_type, last_timestamp)
        ).fetchall()
        
        return jsonify([{
            'username': msg['username'],
            'user_id': msg['user_id'],
            'text': msg['message'],
            'timestamp': msg['timestamp'],
            'chat_type': msg['chat_type']
        } for msg in messages])
    except sqlite3.OperationalError as e:
        print(f"Database error: {e}")
        return jsonify([])
    


# API для отправки сообщений
@app.route('/send_message', methods=['POST'])
def send_message():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Необходима авторизация'})
    
    message_text = request.form.get('message')
    chat_type = request.form.get('chat_type', 'general')
    
    if not message_text:
        return jsonify({'success': False, 'message': 'Сообщение не может быть пустым'})
    
    try:
        message_data = {
            'username': session['user_name'],
            'user_id': session['user_id'],
            'text': message_text,
            'timestamp': datetime.now().isoformat(),
            'chat_type': chat_type
        }
        
        # Сохраняем в БД
        db = get_db()
        db.execute(
            'INSERT INTO chat_messages (user_id, username, message, chat_type, timestamp) VALUES (?, ?, ?, ?, ?)',
            (session['user_id'], session['user_name'], message_text, chat_type, message_data['timestamp'])
        )
        db.commit()
        
        # Отправляем через SocketIO
        socketio.emit('message', message_data)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    

def get_status_text(status):
    statuses = {
        'pending': 'Ожидает',
        'in_progress': 'В пути',
        'completed': 'Выполнено',
        'cancelled': 'Отменено'
    }
    return statuses.get(status, status)



@app.route('/orders')
def orders():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему', 'error')
        return redirect(url_for('index'))
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    orders = db.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC',
                       (session['user_id'],)).fetchall()
    
    # Convert orders to a list of dictionaries and parse created_at to datetime
    orders_converted = []
    for order in orders:
        order_dict = dict(order)
        # Convert created_at string to datetime
        order_dict['created_at'] = datetime.strptime(order['created_at'], '%Y-%m-%d %H:%M:%S')
        orders_converted.append(order_dict)
    
    return render_template('zakaz.html', user=user, orders=orders_converted)


@app.route('/admin/chat')
def admin_chat():
    if not session.get('admin_logged_in'):
        return redirect(url_for('index'))
    
    db = get_db()
    threshold_time = (datetime.now() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')
    
    # Получаем список пользователей с их статусами
    users = db.execute('''
        SELECT *, 
               CASE WHEN last_activity >= ? THEN 1 ELSE 0 END as is_online
        FROM users
        WHERE full_name != ?
        ORDER BY last_activity DESC
    ''', (threshold_time, ADMIN_USERNAME)).fetchall()
    
    # Добавляем счетчик непрочитанных сообщений (нужно реализовать эту логику)
    users_with_unread = []
    for user in users:
        user_dict = dict(user)
        user_dict['unread_count'] = 0  # Здесь нужно добавить логику подсчета
        users_with_unread.append(user_dict)
    
    return render_template('admin_chat.html', users=users_with_unread)



if __name__ == '__main__':
    # Инициализация базы данных
    if not os.path.exists(DATABASE):
        init_db()
    else:
        # Проверяем существование таблиц
        with app.app_context():
            db = get_db()
            cursor = db.cursor()
            
            # Проверяем существование таблицы chat_messages
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
            if not cursor.fetchone():
                cursor.execute('''
                    CREATE TABLE chat_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        username TEXT NOT NULL,
                        message TEXT NOT NULL,
                        chat_type TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                ''')
                db.commit()
    
    # Запускаем сервер с доступом для всех устройств в сети
    socketio.run(app, host='0.0.0.0', debug=True, port=5000)