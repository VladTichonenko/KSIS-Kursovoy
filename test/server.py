import socket
import threading
from datetime import datetime

HOST = '0.0.0.0'
PORT = 5001

clients = {}  # {conn: {'name': str, 'ip': str}}
lock = threading.Lock()

def log(msg):
    """Вывод сообщения с временной меткой"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def handle_client(conn, addr):
    ip = addr[0]
    try:
        name_data = conn.recv(1024)
        if not name_data:
            log(f"Empty name from {ip}, closing connection")
            conn.close()
            return
        name = name_data.decode('utf-8').strip()
        log(f"New connection from {name}@{ip}")
    except Exception as e:
        log(f"Error receiving name from {ip}: {e}")
        conn.close()
        return

    with lock:
        clients[conn] = {'name': name, 'ip': ip}
    
    broadcast(f"*** {name} has joined the chat ***", conn)

    try:
        while True:
            data = conn.recv(1024)
            if not data:
                log(f"Empty data from {name}, closing connection")
                break
            text = data.decode('utf-8')
            sender = clients[conn]['name']
            message = f"[{sender}] {text}"
            log(f"Received message from {sender}: {text}")
            broadcast(message, conn)
    except ConnectionResetError:
        log(f"Connection reset by {name}")
    except Exception as e:
        log(f"Error with {name}: {e}")

    with lock:
        info = clients.pop(conn, None)
    if info:
        log(f"{info['name']} disconnected")
        broadcast(f"*** {info['name']} has left the chat ***", None)
    conn.close()

def broadcast(msg, exclude_conn):
    log(f"Broadcasting: {msg}")
    data = msg.encode('utf-8')
    with lock:
        for c in list(clients.keys()):
            if c != exclude_conn:
                try:
                    c.sendall(data)
                    log(f"Sent to {clients[c]['name']}")
                except Exception as e:
                    log(f"Error sending to {clients[c]['name']}: {e}")
                    c.close()
                    clients.pop(c, None)

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    log(f"Server started on {HOST}:{PORT}")
    try:
        while True:
            conn, addr = server.accept()
            log(f"New connection from {addr[0]}:{addr[1]}")
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        log("Server shutting down...")
    finally:
        server.close()

if __name__ == '__main__':
    start_server()