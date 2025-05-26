import socket
import threading
import time
from datetime import datetime

class TCPServer:
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.server_socket = None
        self.clients = {}
        self.messages = {'general': [], 'support': []}
        self.running = False
        self.lock = threading.Lock()

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        
        print(f"[*] Сервер чата запущен на {self.host}:{self.port}")
        accept_thread = threading.Thread(target=self.accept_connections)
        accept_thread.daemon = True
        accept_thread.start()

    def accept_connections(self):
        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()
                client_socket.settimeout(5)  # Таймаут для получения данных
                
                # Получаем информацию о клиенте
                try:
                    data = client_socket.recv(1024).decode('utf-8').strip()
                    if not data or '|' not in data:
                        client_socket.close()
                        continue
                        
                    username, chat_type = data.split('|', 1)
                    chat_type = chat_type.lower()
                    
                    if chat_type not in ['general', 'support']:
                        client_socket.close()
                        continue
                    
                    client_id = f"{username}@{client_address[0]}:{client_address[1]}"
                    
                    # Закрываем старое соединение, если есть
                    with self.lock:
                        if client_id in self.clients:
                            try:
                                self.clients[client_id]['socket'].close()
                            except:
                                pass
                    
                    with self.lock:
                        self.clients[client_id] = {
                            'socket': client_socket,
                            'username': username,
                            'chat_type': chat_type,
                            'address': client_address,
                            'last_activity': time.time(),
                            'active': True
                        }
                    
                    print(f"[+] Подключен: {client_id} ({chat_type})")
                    
                    # Отправляем историю сообщений
                    self.send_history(client_socket, chat_type)
                    
                    # Запускаем поток для клиента
                    threading.Thread(
                        target=self.handle_client,
                        args=(client_id,),
                        daemon=True
                    ).start()
                    
                except socket.timeout:
                    client_socket.close()
                except Exception as e:
                    print(f"[!] Ошибка подключения: {e}")
                    client_socket.close()
                    
            except Exception as e:
                if self.running:
                    print(f"[!] Ошибка accept: {e}")

    def handle_client(self, client_id):
        with self.lock:
            if client_id not in self.clients:
                return
            client = self.clients[client_id]
            client_socket = client['socket']
        
        try:
            while self.running and client['active']:
                try:
                    message = client_socket.recv(1024).decode('utf-8').strip()
                    if not message:
                        break
                    
                    with self.lock:
                        client['last_activity'] = time.time()
                    
                    full_message = f"{client['username']}: {message}"
                    print(f"[{client['chat_type']}] {full_message}")
                    
                    with self.lock:
                        self.messages[client['chat_type']].append(full_message)
                        if len(self.messages[client['chat_type']]) > 100:
                            self.messages[client['chat_type']].pop(0)
                    
                    self.broadcast(full_message, client['chat_type'], exclude=client_id)
                    
                except socket.timeout:
                    continue
                except (ConnectionResetError, ConnectionAbortedError):
                    break
                except Exception as e:
                    print(f"[!] Ошибка клиента {client_id}: {e}")
                    break
                
        finally:
            self.disconnect_client(client_id)

    def broadcast(self, message, chat_type, exclude=None):
        with self.lock:
            targets = [
                cid for cid, client in self.clients.items()
                if client['chat_type'] == chat_type 
                and cid != exclude 
                and client['active']
            ]
            
        for cid in targets:
            with self.lock:
                client = self.clients.get(cid)
            if client:
                try:
                    client['socket'].send(message.encode('utf-8'))
                    print(f"Sent to {cid}: {message}")  # Логирование отправки
                except Exception as e:
                    print(f"Ошибка отправки {cid}: {e}")
                    self.disconnect_client(cid)




    def send_history(self, client_socket, chat_type, limit=20):
        with self.lock:
            history = self.messages.get(chat_type, [])[-limit:]
        
        try:
            for msg in history:
                client_socket.send(msg.encode('utf-8'))
                time.sleep(0.05)  # Небольшая задержка между сообщениями
        except Exception as e:
            print(f"Ошибка отправки истории: {e}")

    def disconnect_client(self, client_id):
        with self.lock:
            if client_id in self.clients:
                client = self.clients[client_id]
                if client['active']:
                    print(f"[-] Отключен: {client_id}")
                    try:
                        client['socket'].close()
                    except:
                        pass
                    client['active'] = False

    def stop(self):
        self.running = False
        with self.lock:
            for client_id in list(self.clients.keys()):
                self.disconnect_client(client_id)
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        print("[*] Сервер чата остановлен")


def handle_client(self, client_id):
    with self.lock:
        if client_id not in self.clients:
            return
        client = self.clients[client_id]
    
    try:
        while self.running and client['active']:
            try:
                message = client['socket'].recv(1024).decode('utf-8').strip()
                if not message:
                    break
                
                # Обработка админских сообщений
                if client['username'] == 'admin' and message.startswith('[ADMIN:'):
                    # Формат: [ADMIN:username] сообщение
                    parts = message.split(']', 1)
                    if len(parts) == 2:
                        target_user = parts[0][7:]  # Извлекаем имя пользователя
                        actual_message = parts[1].strip()
                        self.send_to_user(target_user, actual_message)
                        continue
                
                # Обычные сообщения
                now = datetime.now().strftime("%H:%M")
                full_message = f"{client['username']} [{now}]: {message}"
                
                with self.lock:
                    self.messages[client['chat_type']].append(full_message)
                    if len(self.messages[client['chat_type']]) > 100:
                        self.messages[client['chat_type']].pop(0)
                
                self.broadcast(full_message, client['chat_type'], exclude=client_id)
                
            except socket.timeout:
                continue
            except (ConnectionResetError, ConnectionAbortedError):
                break
            except Exception as e:
                print(f"[!] Ошибка клиента {client_id}: {e}")
                break
    finally:
        self.disconnect_client(client_id)

def send_to_user(self, username, message):
    with self.lock:
        for client_id, client in self.clients.items():
            if client['username'] == username and client['active']:
                try:
                    now = datetime.now().strftime("%H:%M")
                    full_message = f"ADMIN [{now}]: {message}"
                    client['socket'].send(full_message.encode('utf-8'))
                    return True
                except Exception as e:
                    print(f"Ошибка отправки сообщения пользователю {username}: {e}")
        return False
    

if __name__ == "__main__":
    server = TCPServer()
    try:
        server.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()