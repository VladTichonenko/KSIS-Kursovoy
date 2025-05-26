from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import socket
import threading
import uuid
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'replace_with_secure_key'

clients = {}  # client_id -> {'socket': socket, 'messages': [str]}
lock = threading.Lock()

def log(msg):
    """Вывод сообщения с временной меткой"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def listen_for_messages(client_id):
    sock = clients[client_id]['socket']
    name = clients[client_id].get('name', 'unknown')
    log(f"Starting listener for {name} (client_id: {client_id})")
    
    while True:
        try:
            data = sock.recv(1024)
            if not data:
                log(f"Empty data received for {name}, closing listener")
                break
            msg = data.decode('utf-8')
            log(f"Received message for {name}: {msg}")
            with lock:
                clients[client_id]['messages'].append(msg)
        except Exception as e:
            log(f"Error in listener for {name}: {e}")
            break

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        name = request.form.get('name')
        source_ip = request.form.get('source_ip')
        server_ip = request.form.get('server_ip')
        
        if not all([name, source_ip, server_ip]):
            log("Missing form data")
            return "All fields are required", 400
            
        client_id = str(uuid.uuid4())
        session['client_id'] = client_id
        session['name'] = name

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind((source_ip, 0))
            sock.connect((server_ip, 5001))
            sock.sendall(name.encode('utf-8'))
            log(f"Connected to server {server_ip}:5001 as {name}")
        except Exception as e:
            log(f"Connection error: {e}")
            return f"Connection error: {e}", 500

        with lock:
            clients[client_id] = {'socket': sock, 'messages': [], 'name': name}

        threading.Thread(target=listen_for_messages, args=(client_id,), daemon=True).start()
        return redirect(url_for('chat'))
    
    return render_template('login.html')

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    client_id = session.get('client_id')
    if not client_id or client_id not in clients:
        log("Unauthorized access to chat")
        return redirect(url_for('index'))

    if request.method == 'POST':
        text = request.form.get('text')
        if text:
            log(f"Sending message: {text}")
            sock = clients[client_id]['socket']
            try:
                sock.sendall(text.encode('utf-8'))
            except Exception as e:
                log(f"Error sending message: {e}")
        return ('', 204)
    
    return render_template('index.html', name=session.get('name'))

@app.route('/messages')
def messages():
    client_id = session.get('client_id')
    if not client_id or client_id not in clients:
        log("Unauthorized access to messages")
        return jsonify([])
    
    with lock:
        msgs = list(clients[client_id]['messages'])
    log(f"Returning {len(msgs)} messages for client {client_id}")
    return jsonify(msgs)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')