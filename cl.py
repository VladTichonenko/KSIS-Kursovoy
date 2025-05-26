from flask import Flask, render_template, request, redirect, url_for
import socket
import threading
import sys

app = Flask(__name__)

# Глобальные переменные для соединения
client_socket = None
username = ""
connected = False
received_messages = []

def receive():
    global client_socket, connected, received_messages
    while connected:
        try:
            message = client_socket.recv(1024).decode("utf-8")
            if not message:
                print("\nСоединение с сервером разорвано")
                connected = False
                break
            print(f"\nПолучено сообщение: {message}")
            received_messages.append(message)
        except (ConnectionResetError, ConnectionAbortedError):
            print("\nСоединение с сервером разорвано")
            connected = False
            break
        except Exception as e:
            print(f"\nОшибка получения сообщения: {e}")
            connected = False
            break

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        return redirect(url_for('connect'))
    return render_template('index.html')

@app.route('/connect', methods=['POST'])
def connect():
    global client_socket, username, connected

    username = request.form.get('username', '').strip()
    ip = request.form.get('server_ip', '127.0.0.1')
    server_port = int(request.form.get('server_port', 8080))
    client_ip = request.form.get('client_ip', '127.0.0.1')
    tcp_port = int(request.form.get('tcp_port', 0))

    if not username:
        return render_template('index.html', error="Имя пользователя не может быть пустым!")

    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        client_socket.bind((client_ip, tcp_port))
        client_socket.connect((ip, server_port))
        client_socket.send(username.encode('utf-8'))
        connected = True

        threading.Thread(target=receive, daemon=True).start()
        return redirect(url_for('chat'))

    except Exception as e:
        return render_template('index.html', error=f"Ошибка подключения: {e}")

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    global connected, username
    if not connected:
        return redirect(url_for('index'))

    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if message:
            try:
                client_socket.send(message.encode('utf-8'))
            except Exception as e:
                return render_template('chat.html', username=username, error=f"Ошибка отправки: {e}")

    return render_template('chat.html', username=username, messages=received_messages)

@app.route('/disconnect', methods=['POST'])
def disconnect():
    global client_socket, connected
    if connected:
        try:
            client_socket.close()
        except:
            pass
        connected = False
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)