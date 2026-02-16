import flet as ft
import hashlib
import base64
import json
import os
import time
import random
import threading
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, auth, firestore, storage
import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
import io
import wave
import tempfile
import uuid
from pathlib import Path
import mimetypes

# Инициализация Firebase
cred = credentials.Certificate("google-services.json")
firebase_admin.initialize_app(cred, {
    'storageBucket': 'ghost-pro-5aa22.firebasestorage.app'
})

db = firestore.client()
bucket = storage.bucket()

# Класс для шифрования
class GhostEncryption:
    def __init__(self):
        self.salt = b'ghost_pro_salt_2026'
    
    def generate_key_from_password(self, password):
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def encrypt_message(self, message, key):
        f = Fernet(key)
        encrypted = f.encrypt(message.encode())
        return encrypted
    
    def decrypt_message(self, encrypted_message, key):
        f = Fernet(key)
        decrypted = f.decrypt(encrypted_message)
        return decrypted.decode()
    
    def encrypt_file(self, file_data, key):
        f = Fernet(key)
        encrypted = f.encrypt(file_data)
        return encrypted
    
    def decrypt_file(self, encrypted_data, key):
        f = Fernet(key)
        decrypted = f.decrypt(encrypted_data)
        return decrypted

# Класс для управления файлами
class FileManager:
    def __init__(self):
        self.bucket = bucket
        self.encryption = GhostEncryption()
        self.temp_dir = tempfile.gettempdir()
    
    def upload_file(self, file_path, user_id, chat_id, file_type):
        """Загрузка файла в Firebase Storage"""
        try:
            # Генерируем уникальное имя файла
            file_ext = Path(file_path).suffix
            file_name = f"{uuid.uuid4()}{file_ext}"
            blob_path = f"chats/{chat_id}/{file_name}"
            
            # Создаем blob
            blob = self.bucket.blob(blob_path)
            
            # Загружаем файл
            blob.upload_from_filename(file_path)
            
            # Делаем файл публичным на время (для демо)
            blob.make_public()
            
            # Получаем URL
            file_url = blob.public_url
            
            # Сохраняем метаданные в Firestore
            file_meta = {
                'file_name': file_name,
                'file_url': file_url,
                'file_type': file_type,
                'file_size': os.path.getsize(file_path),
                'uploaded_by': user_id,
                'chat_id': chat_id,
                'uploaded_at': datetime.now()
            }
            
            doc_ref = db.collection('files').add(file_meta)
            file_meta['id'] = doc_ref[1].id
            
            return file_meta
        except Exception as e:
            print(f"Error uploading file: {e}")
            return None
    
    def download_file(self, file_url, save_path):
        """Скачивание файла"""
        try:
            response = requests.get(file_url)
            with open(save_path, 'wb') as f:
                f.write(response.content)
            return save_path
        except Exception as e:
            print(f"Error downloading file: {e}")
            return None
    
    def get_file_icon(self, file_type):
        """Получить иконку для типа файла"""
        icons = {
            'image': ft.icons.IMAGE,
            'video': ft.icons.VIDEO_LIBRARY,
            'audio': ft.icons.AUDIO_FILE,
            'document': ft.icons.DESCRIPTION,
            'archive': ft.icons.FOLDER_ZIP,
            'default': ft.cons.FILE_PRESENT
        }
        
        if file_type.startswith('image/'):
            return icons['image']
        elif file_type.startswith('video/'):
            return icons['video']
        elif file_type.startswith('audio/'):
            return icons['audio']
        else:
            return icons['default']

# Класс для записи голоса
class VoiceRecorder:
    def __init__(self):
        self.is_recording = False
        self.audio_data = []
        self.temp_file = None
    
    def start_recording(self):
        """Начать запись голоса"""
        self.is_recording = True
        self.audio_data = []
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        
        # В реальном приложении здесь будет код для записи с микрофона
        # Для демо создаем пустой WAV файл
        import wave
        import struct
        
        with wave.open(self.temp_file.name, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(44100)
            # Записываем тестовые данные (1 секунда тишины)
            for i in range(44100):
                value = 0
                packed_value = struct.pack('<h', value)
                wav_file.writeframes(packed_value)
        
        return self.temp_file.name
    
    def stop_recording(self):
        """Остановить запись"""
        self.is_recording = False
        return self.temp_file.name if self.temp_file else None

# Класс для Firebase операций
class FirebaseManager:
    def __init__(self):
        self.db = db
        self.bucket = bucket
        self.file_manager = FileManager()
    
    def get_user_by_username(self, username):
        users_ref = self.db.collection('users').where('username', '==', username).stream()
        for user in users_ref:
            return user.to_dict(), user.id
        return None, None
    
    def get_user_by_email(self, email):
        users_ref = self.db.collection('users').where('email', '==', email).stream()
        for user in users_ref:
            return user.to_dict(), user.id
        return None, None
    
    def create_user(self, uid, email, username, password):
        user_data = {
            'uid': uid,
            'email': email,
            'username': username,
            'password_hash': hashlib.sha256(password.encode()).hexdigest(),
            'avatar_url': '',
            'is_admin': False,
            'is_banned': False,
            'is_frozen': False,
            'created_at': datetime.now(),
            'last_seen': datetime.now()
        }
        self.db.collection('users').document(uid).set(user_data)
        return user_data
    
    def update_user(self, uid, data):
        self.db.collection('users').document(uid).update(data)
    
    def upload_avatar(self, uid, image_path):
        """Загрузка аватарки пользователя"""
        try:
            # Сжимаем изображение
            from PIL import Image
            img = Image.open(image_path)
            img.thumbnail((256, 256))
            
            # Сохраняем во временный файл
            temp_avatar = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            img.save(temp_avatar.name, 'JPEG', quality=85)
            
            # Загружаем в Storage
            blob = self.bucket.blob(f'avatars/{uid}.jpg')
            blob.upload_from_filename(temp_avatar.name)
            blob.make_public()
            
            # Обновляем URL в Firestore
            avatar_url = blob.public_url
            self.update_user(uid, {'avatar_url': avatar_url})
            
            # Удаляем временный файл
            os.unlink(temp_avatar.name)
            
            return avatar_url
        except Exception as e:
            print(f"Error uploading avatar: {e}")
            return None
    
    def search_users(self, query):
        users = []
        users_ref = self.db.collection('users').where('username', '>=', query).where('username', '<=', query + '\uf8ff').stream()
        for user in users_ref:
            user_data = user.to_dict()
            if not user_data.get('is_banned', False):
                user_data['uid'] = user.id
                users.append(user_data)
        return users
    
    def send_message(self, sender_id, receiver_id, content, msg_type='text', file_data=None):
        """Отправка сообщения с поддержкой файлов"""
        message = {
            'sender_id': sender_id,
            'receiver_id': receiver_id,
            'content': content,
            'type': msg_type,
            'timestamp': datetime.now(),
            'is_read': False
        }
        
        # Если есть файл, добавляем информацию о нем
        if file_data:
            message['file_url'] = file_data.get('file_url')
            message['file_name'] = file_data.get('file_name')
            message['file_type'] = file_data.get('file_type')
            message['file_size'] = file_data.get('file_size')
        
        # Сохраняем сообщение
        doc_ref = self.db.collection('messages').add(message)
        message['id'] = doc_ref[1].id
        
        # Создаем уведомление для получателя
        notification = {
            'user_id': receiver_id,
            'title': 'Новое сообщение',
            'body': f'От: {self.get_user_by_id(sender_id)["username"]}',
            'type': 'message',
            'data': {'message_id': message['id'], 'sender_id': sender_id},
            'created_at': datetime.now(),
            'is_read': False
        }
        self.db.collection('notifications').add(notification)
        
        return message
    
    def get_user_by_id(self, uid):
        user_doc = self.db.collection('users').document(uid).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            user_data['uid'] = uid
            return user_data
        return None
    
    def get_chat_messages(self, user1_id, user2_id):
        messages = []
        msgs_ref = self.db.collection('messages')\
            .where('sender_id', 'in', [user1_id, user2_id])\
            .where('receiver_id', 'in', [user1_id, user2_id])\
            .order_by('timestamp').stream()
        
        for msg in msgs_ref:
            msg_data = msg.to_dict()
            msg_data['id'] = msg.id
            messages.append(msg_data)
        return messages
    
    def get_recent_chats(self, user_id):
        """Получить список последних чатов"""
        chats = {}
        
        # Получаем все сообщения пользователя
        messages = self.db.collection('messages')\
            .where('sender_id', '==', user_id)\
            .order_by('timestamp', direction='DESCENDING')\
            .limit(50).stream()
        
        for msg in messages:
            msg_data = msg.to_dict()
            other_id = msg_data['receiver_id']
            if other_id not in chats:
                other_user = self.get_user_by_id(other_id)
                if other_user:
                    chats[other_id] = {
                        'user': other_user,
                        'last_message': msg_data,
                        'timestamp': msg_data['timestamp']
                    }
        
        messages2 = self.db.collection('messages')\
            .where('receiver_id', '==', user_id)\
            .order_by('timestamp', direction='DESCENDING')\
            .limit(50).stream()
        
        for msg in messages2:
            msg_data = msg.to_dict()
            other_id = msg_data['sender_id']
            if other_id not in chats:
                other_user = self.get_user_by_id(other_id)
                if other_user:
                    chats[other_id] = {
                        'user': other_user,
                        'last_message': msg_data,
                        'timestamp': msg_data['timestamp']
                    }
        
        # Сортируем по времени последнего сообщения
        sorted_chats = sorted(chats.values(), key=lambda x: x['timestamp'], reverse=True)
        return sorted_chats
    
    def create_ticket(self, user_id, username, subject, message):
        ticket = {
            'user_id': user_id,
            'username': username,
            'subject': subject,
            'message': message,
            'status': 'open',
            'created_at': datetime.now()
        }
        self.db.collection('tickets').add(ticket)
    
    def get_tickets(self):
        tickets = []
        tickets_ref = self.db.collection('tickets').order_by('created_at', direction='DESCENDING').stream()
        for ticket in tickets_ref:
            ticket_data = ticket.to_dict()
            ticket_data['id'] = ticket.id
            tickets.append(ticket_data)
        return tickets
    
    def update_ticket_status(self, ticket_id, status):
        self.db.collection('tickets').document(ticket_id).update({'status': status})
    
    def send_broadcast(self, title, message):
        users = self.db.collection('users').stream()
        broadcast_data = {
            'title': title,
            'message': message,
            'created_at': datetime.now()
        }
        broadcast_ref = self.db.collection('broadcasts').add(broadcast_data)
        
        for user in users:
            user_id = user.id
            notification = {
                'user_id': user_id,
                'title': title,
                'body': message,
                'type': 'broadcast',
                'created_at': datetime.now(),
                'is_read': False
            }
            self.db.collection('notifications').add(notification)
        
        return broadcast_ref
    
    def get_user_notifications(self, user_id):
        notifications = []
        notif_ref = self.db.collection('notifications')\
            .where('user_id', '==', user_id)\
            .order_by('created_at', direction='DESCENDING')\
            .limit(50).stream()
        
        for notif in notif_ref:
            notif_data = notif.to_dict()
            notif_data['id'] = notif.id
            notifications.append(notif_data)
        return notifications
    
    def ban_user(self, username):
        user_data, uid = self.get_user_by_username(username)
        if user_data and not user_data.get('is_admin', False):
            self.db.collection('users').document(uid).update({'is_banned': True})
            return True
        return False
    
    def unban_user(self, username):
        user_data, uid = self.get_user_by_username(username)
        if user_data:
            self.db.collection('users').document(uid).update({'is_banned': False})
            return True
        return False
    
    def freeze_user(self, username):
        user_data, uid = self.get_user_by_username(username)
        if user_data and not user_data.get('is_admin', False):
            self.db.collection('users').document(uid).update({'is_frozen': True})
            return True
        return False
    
    def unfreeze_user(self, username):
        user_data, uid = self.get_user_by_username(username)
        if user_data:
            self.db.collection('users').document(uid).update({'is_frozen': False})
            return True
        return False

# Главное приложение
class GhostProMessenger:
    def __init__(self):
        self.fb = FirebaseManager()
        self.encryption = GhostEncryption()
        self.voice_recorder = VoiceRecorder()
        self.current_user = None
        self.current_chat = None
        self.matrix_running = False
        self.selected_file = None
        
    def main(self, page: ft.Page):
        self.page = page
        page.title = "Ghost PRO Messenger"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = "#000000"
        page.padding = 0
        page.fonts = {
            "hack": "https://github.com/ryanoasis/nerd-fonts/raw/master/patched-fonts/Hack/Regular/complete/Hack%20Regular%20Nerd%20Font%20Complete%20Mono.ttf"
        }
        
        # Устанавливаем иконку приложения
        if os.path.exists("icon.png"):
            page.icon = "icon.png"
        
        # Запускаем матричный эффект
        self.start_matrix_effect()
        
        # Показываем экран загрузки
        self.show_boot_screen()
    
    def start_matrix_effect(self):
        self.matrix_running = True
        matrix_thread = threading.Thread(target=self.matrix_effect)
        matrix_thread.daemon = True
        matrix_thread.start()
    
    def matrix_effect(self):
        while self.matrix_running:
            if hasattr(self, 'matrix_container'):
                cols = 80
                row = ''.join([str(random.randint(0, 1)) for _ in range(cols)])
                self.matrix_container.content.controls.append(
                    ft.Text(row, color=ft.colors.GREEN_400, size=10, font_family="hack")
                )
                if len(self.matrix_container.content.controls) > 20:
                    self.matrix_container.content.controls.pop(0)
                self.matrix_container.update()
            time.sleep(0.1)
    
    def show_boot_screen(self):
        boot_text = """
        ╔══════════════════════════════════════════════════════════╗
        ║                    GHOST PRO v1.0                        ║
        ║              ⚡ СЕКРЕТНЫЙ МЕССЕНДЖЕР ⚡                   ║
        ╠══════════════════════════════════════════════════════════╣
        ║  >> Инициализация системы защиты...                      ║
        ║  >> Загрузка модулей шифрования...                       ║
        ║  >> Установка защищенного соединения...                  ║
        ║  >> Готово. Доступ разрешен только авторизованным        ║
        ╚══════════════════════════════════════════════════════════╝
        """
        
        boot_screen = ft.Container(
            content=ft.Column([
                ft.Text(boot_text, color=ft.colors.GREEN_400, font_family="hack"),
                ft.ElevatedButton(
                    "> НАЧАТЬ <",
                    on_click=lambda _: self.show_login_screen(),
                    style=ft.ButtonStyle(
                        color=ft.colors.GREEN_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.GREEN_400),
                    ),
                )
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            alignment=ft.alignment.center,
            bgcolor="#000000",
            expand=True
        )
        
        self.matrix_container = ft.Container(
            content=ft.Column([], scroll=ft.ScrollMode.AUTO),
            height=100,
            bgcolor="#000000"
        )
        
        self.page.add(
            ft.Column([
                self.matrix_container,
                boot_screen
            ], spacing=0, expand=True)
        )
    
    def show_login_screen(self):
        self.page.clean()
        
        email_field = ft.TextField(
            label="> EMAIL",
            border_color=ft.colors.GREEN_400,
            color=ft.colors.GREEN_400,
            cursor_color=ft.colors.GREEN_400,
            bgcolor="#001100",
            width=300,
            font_family="hack"
        )
        
        password_field = ft.TextField(
            label="> PASSWORD",
            password=True,
            can_reveal_password=True,
            border_color=ft.colors.GREEN_400,
            color=ft.colors.GREEN_400,
            cursor_color=ft.colors.GREEN_400,
            bgcolor="#001100",
            width=300,
            font_family="hack"
        )
        
        twofa_field = ft.TextField(
            label="> 2FA CODE (если есть)",
            border_color=ft.colors.GREEN_400,
            color=ft.colors.GREEN_400,
            cursor_color=ft.colors.GREEN_400,
            bgcolor="#001100",
            width=300,
            visible=False,
            font_family="hack"
        )
        
        def try_login(e):
            email = email_field.value
            password = password_field.value
            
            # Проверка на админский вход
            if email == "admin" and password == "TimaIssam2026":
                self.current_user = {
                    'uid': 'admin',
                    'email': 'admin',
                    'username': 'admin',
                    'is_admin': True
                }
                self.show_admin_panel()
                return
            
            # Обычный вход
            try:
                user_data, uid = self.fb.get_user_by_email(email)
                if user_data and user_data.get('password_hash') == hashlib.sha256(password.encode()).hexdigest():
                    if user_data.get('is_banned', False):
                        self.page.show_snack_bar(ft.SnackBar(content=ft.Text("❌ Аккаунт заблокирован")))
                        return
                    
                    if user_data.get('is_frozen', False):
                        self.page.show_snack_bar(ft.SnackBar(content=ft.Text("❌ Аккаунт заморожен")))
                        return
                    
                    self.current_user = user_data
                    self.current_user['uid'] = uid
                    
                    # Показываем поле для 2FA
                    twofa_field.visible = True
                    self.page.update()
                else:
                    self.page.show_snack_bar(ft.SnackBar(content=ft.Text("❌ Неверные данные")))
            except Exception as e:
                self.page.show_snack_bar(ft.SnackBar(content=ft.Text(f"❌ Ошибка: {str(e)}")))
        
        def verify_2fa(e):
            # Здесь должна быть проверка 2FA
            # Для демо просто пропускаем
            self.show_terminal_main()
        
        def show_register(e):
            self.show_register_screen()
        
        login_panel = ft.Container(
            content=ft.Column([
                ft.Text("> АВТОРИЗАЦИЯ", size=20, color=ft.colors.GREEN_400, font_family="hack"),
                email_field,
                password_field,
                twofa_field,
                ft.Row([
                    ft.ElevatedButton(
                        "> ВОЙТИ",
                        on_click=try_login,
                        style=ft.ButtonStyle(
                            color=ft.colors.GREEN_400,
                            bgcolor=ft.colors.BLACK,
                            side=ft.BorderSide(2, ft.colors.GREEN_400),
                        ),
                    ),
                    ft.ElevatedButton(
                        "> РЕГИСТРАЦИЯ",
                        on_click=show_register,
                        style=ft.ButtonStyle(
                            color=ft.colors.GREEN_400,
                            bgcolor=ft.colors.BLACK,
                            side=ft.BorderSide(2, ft.colors.GREEN_400),
                        ),
                    )
                ], alignment=ft.MainAxisAlignment.CENTER),
                ft.ElevatedButton(
                    "> ПОДТВЕРДИТЬ 2FA",
                    on_click=verify_2fa,
                    visible=False,
                    style=ft.ButtonStyle(
                        color=ft.colors.GREEN_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.GREEN_400),
                    ),
                )
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            alignment=ft.alignment.center,
            bgcolor="#000000",
            expand=True
        )
        
        self.page.add(
            ft.Column([
                self.matrix_container,
                login_panel
            ], spacing=0, expand=True)
        )
    
    def show_register_screen(self):
        self.page.clean()
        
        email_field = ft.TextField(
            label="> EMAIL",
            border_color=ft.colors.GREEN_400,
            color=ft.colors.GREEN_400,
            cursor_color=ft.colors.GREEN_400,
            bgcolor="#001100",
            width=300,
            font_family="hack"
        )
        
        username_field = ft.TextField(
            label="> USERNAME",
            border_color=ft.colors.GREEN_400,
            color=ft.colors.GREEN_400,
            cursor_color=ft.colors.GREEN_400,
            bgcolor="#001100",
            width=300,
            font_family="hack"
        )
        
        password_field = ft.TextField(
            label="> PASSWORD",
            password=True,
            can_reveal_password=True,
            border_color=ft.colors.GREEN_400,
            color=ft.colors.GREEN_400,
            cursor_color=ft.colors.GREEN_400,
            bgcolor="#001100",
            width=300,
            font_family="hack"
        )
        
        confirm_field = ft.TextField(
            label="> CONFIRM PASSWORD",
            password=True,
            can_reveal_password=True,
            border_color=ft.colors.GREEN_400,
            color=ft.colors.GREEN_400,
            cursor_color=ft.colors.GREEN_400,
            bgcolor="#001100",
            width=300,
            font_family="hack"
        )
        
        def try_register(e):
            email = email_field.value
            username = username_field.value
            password = password_field.value
            confirm = confirm_field.value
            
            if not email or not username or not password:
                self.page.show_snack_bar(ft.SnackBar(content=ft.Text("❌ Заполните все поля")))
                return
            
            if password != confirm:
                self.page.show_snack_bar(ft.SnackBar(content=ft.Text("❌ Пароли не совпадают")))
                return
            
            try:
                # Проверяем уникальность username
                existing_user, _ = self.fb.get_user_by_username(username)
                if existing_user:
                    self.page.show_snack_bar(ft.SnackBar(content=ft.Text("❌ Username уже занят")))
                    return
                
                # Создаем пользователя в Firebase Auth
                user = auth.create_user(
                    email=email,
                    password=password
                )
                
                # Сохраняем в Firestore
                self.fb.create_user(user.uid, email, username, password)
                
                self.page.show_snack_bar(ft.SnackBar(content=ft.Text("✅ Регистрация успешна!")))
                self.show_login_screen()
                
            except Exception as e:
                self.page.show_snack_bar(ft.SnackBar(content=ft.Text(f"❌ Ошибка: {str(e)}")))
        
        register_panel = ft.Container(
            content=ft.Column([
                ft.Text("> РЕГИСТРАЦИЯ", size=20, color=ft.colors.GREEN_400, font_family="hack"),
                email_field,
                username_field,
                password_field,
                confirm_field,
                ft.Row([
                    ft.ElevatedButton(
                        "> ЗАРЕГИСТРИРОВАТЬСЯ",
                        on_click=try_register,
                        style=ft.ButtonStyle(
                            color=ft.colors.GREEN_400,
                            bgcolor=ft.colors.BLACK,
                            side=ft.BorderSide(2, ft.colors.GREEN_400),
                        ),
                    ),
                    ft.ElevatedButton(
                        "> НАЗАД",
                        on_click=lambda _: self.show_login_screen(),
                        style=ft.ButtonStyle(
                            color=ft.colors.GREEN_400,
                            bgcolor=ft.colors.BLACK,
                            side=ft.BorderSide(2, ft.colors.GREEN_400),
                        ),
                    )
                ], alignment=ft.MainAxisAlignment.CENTER)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            alignment=ft.alignment.center,
            bgcolor="#000000",
            expand=True
        )
        
        self.page.add(
            ft.Column([
                self.matrix_container,
                register_panel
            ], spacing=0, expand=True)
        )
    
    def show_terminal_main(self):
        self.page.clean()
        
        # Статус бар
        status_bar = ft.Container(
            content=ft.Row([
                ft.Text(f"[{datetime.now().strftime('%H:%M:%S')}]", color=ft.colors.GREEN_400, font_family="hack"),
                ft.Text(f"USER: {self.current_user['username']}", color=ft.colors.GREEN_400, font_family="hack"),
                ft.Text("⚡ ENCRYPTED", color=ft.colors.GREEN_400, font_family="hack"),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            bgcolor="#001100",
            padding=10,
            border=ft.border.all(1, ft.colors.GREEN_400)
        )
        
        # Меню
        menu = ft.Column([
            ft.ListTile(
                title=ft.Text("> ЧАТЫ", color=ft.colors.GREEN_400, font_family="hack"),
                leading=ft.Icon(ft.icons.CHAT, color=ft.colors.GREEN_400),
                on_click=lambda _: self.show_chats(),
            ),
            ft.ListTile(
                title=ft.Text("> ПОИСК ПОЛЬЗОВАТЕЛЕЙ", color=ft.colors.GREEN_400, font_family="hack"),
                leading=ft.Icon(ft.icons.SEARCH, color=ft.colors.GREEN_400),
                on_click=lambda _: self.show_user_search(),
            ),
            ft.ListTile(
                title=ft.Text("> ПРОФИЛЬ", color=ft.colors.GREEN_400, font_family="hack"),
                leading=ft.Icon(ft.icons.PERSON, color=ft.colors.GREEN_400),
                on_click=lambda _: self.show_profile(),
            ),
            ft.ListTile(
                title=ft.Text("> ТЕХ.ПОДДЕРЖКА", color=ft.colors.GREEN_400, font_family="hack"),
                leading=ft.Icon(ft.icons.SUPPORT_AGENT, color=ft.colors.GREEN_400),
                on_click=lambda _: self.show_support(),
            ),
            ft.ListTile(
                title=ft.Text("> УВЕДОМЛЕНИЯ", color=ft.colors.GREEN_400, font_family="hack"),
                leading=ft.Icon(ft.icons.NOTIFICATIONS, color=ft.colors.GREEN_400),
                on_click=lambda _: self.show_notifications(),
            ),
            ft.Divider(color=ft.colors.GREEN_400),
            ft.ListTile(
                title=ft.Text("> ВЫХОД", color=ft.colors.RED_400, font_family="hack"),
                leading=ft.Icon(ft.icons.EXIT_TO_APP, color=ft.colors.RED_400),
                on_click=lambda _: self.logout(),
            ),
        ])
        
        if self.current_user.get('is_admin', False):
            menu.controls.insert(4, ft.ListTile(
                title=ft.Text("> АДМИН ПАНЕЛЬ", color=ft.colors.RED_400, font_family="hack"),
                leading=ft.Icon(ft.icons.ADMIN_PANEL_SETTINGS, color=ft.colors.RED_400),
                on_click=lambda _: self.show_admin_panel(),
            ))
        
        main_panel = ft.Container(
            content=ft.Column([
                ft.Text("""
    ╔══════════════════════════════════════════════════════════╗
    ║               GHOST PRO - ГЛАВНОЕ МЕНЮ                  ║
    ╚══════════════════════════════════════════════════════════╝
                """, color=ft.colors.GREEN_400, font_family="hack"),
                menu
            ]),
            bgcolor="#000000",
            padding=20,
            expand=True
        )
        
        self.page.add(
            ft.Column([
                self.matrix_container,
                status_bar,
                main_panel
            ], spacing=0, expand=True)
        )
    
    def show_user_search(self):
        self.page.clean()
        
        search_field = ft.TextField(
            label="> ВВЕДИТЕ USERNAME",
            border_color=ft.colors.GREEN_400,
            color=ft.colors.GREEN_400,
            cursor_color=ft.colors.GREEN_400,
            bgcolor="#001100",
            width=300,
            font_family="hack",
            on_submit=lambda e: search_users(e)
        )
        
        results_list = ft.ListView(expand=True, spacing=10)
        
        def search_users(e):
            query = search_field.value
            if not query:
                return
            
            results_list.controls.clear()
            users = self.fb.search_users(query)
            
            if users:
                for user in users:
                    if user['uid'] != self.current_user['uid']:
                        user_card = ft.Container(
                            content=ft.Row([
                                ft.CircleAvatar(
                                    foreground_image_url=user.get('avatar_url', ''),
                                    content=ft.Text(user['username'][0].upper()) if not user.get('avatar_url') else None,
                                ),
                                ft.Column([
                                    ft.Text(user['username'], color=ft.colors.GREEN_400, font_family="hack", weight=ft.FontWeight.BOLD),
                                    ft.Text(f"ID: {user['uid'][:8]}...", color=ft.colors.GREEN_200, size=12, font_family="hack"),
                                ], spacing=0),
                                ft.IconButton(
                                    icon=ft.icons.CHAT,
                                    icon_color=ft.colors.GREEN_400,
                                    on_click=lambda _, u=user: self.start_chat(u),
                                )
                            ]),
                            bgcolor="#001100",
                            padding=10,
                            border=ft.border.all(1, ft.colors.GREEN_400),
                            border_radius=5,
                        )
                        results_list.controls.append(user_card)
            else:
                results_list.controls.append(
                    ft.Text("❌ Пользователи не найдены", color=ft.colors.RED_400, font_family="hack")
                )
            
            self.page.update()
        
        search_panel = ft.Container(
            content=ft.Column([
                ft.Text("> ПОИСК ПОЛЬЗОВАТЕЛЕЙ", size=20, color=ft.colors.GREEN_400, font_family="hack"),
                search_field,
                ft.ElevatedButton(
                    "> НАЙТИ",
                    on_click=search_users,
                    style=ft.ButtonStyle(
                        color=ft.colors.GREEN_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.GREEN_400),
                    ),
                ),
                ft.Divider(color=ft.colors.GREEN_400),
                ft.Text("> РЕЗУЛЬТАТЫ:", color=ft.colors.GREEN_400, font_family="hack"),
                results_list,
                ft.ElevatedButton(
                    "> НАЗАД",
                    on_click=lambda _: self.show_terminal_main(),
                    style=ft.ButtonStyle(
                        color=ft.colors.GREEN_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.GREEN_400),
                    ),
                )
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor="#000000",
            padding=20,
            expand=True
        )
        
        self.page.add(
            ft.Column([
                self.matrix_container,
                search_panel
            ], spacing=0, expand=True)
        )
    
    def start_chat(self, user):
        self.current_chat = user
        self.show_chat_screen()
    
    def show_chat_screen(self):
        self.page.clean()
        
        messages_list = ft.ListView(expand=True, spacing=10, auto_scroll=True)
        message_input = ft.TextField(
            hint_text="> ВВЕДИТЕ СООБЩЕНИЕ",
            border_color=ft.colors.GREEN_400,
            color=ft.colors.GREEN_400,
            cursor_color=ft.colors.GREEN_400,
            bgcolor="#001100",
            expand=True,
            multiline=True,
            min_lines=1,
            max_lines=3,
            font_family="hack",
            on_submit=lambda e: send_message(e)
        )
        
        selected_file_text = ft.Text("", color=ft.colors.GREEN_400, size=12, font_family="hack")
        is_recording = False
        
        def load_messages():
            messages = self.fb.get_chat_messages(self.current_user['uid'], self.current_chat['uid'])
            messages_list.controls.clear()
            
            for msg in messages:
                is_me = msg['sender_id'] == self.current_user['uid']
                
                # Создаем содержимое сообщения в зависимости от типа
                if msg['type'] == 'text':
                    content = ft.Text(
                        msg['content'],
                        color=ft.colors.WHITE if is_me else ft.colors.GREEN_400,
                        font_family="hack"
                    )
                elif msg['type'] == 'image':
                    content = ft.Column([
                        ft.Image(src=msg['file_url'], width=200, height=200, fit=ft.ImageFit.CONTAIN),
                        ft.Text(msg.get('content', '📷 Фото'), color=ft.colors.GREEN_200, size=12, font_family="hack")
                    ])
                elif msg['type'] == 'video':
                    content = ft.Column([
                        ft.Icon(ft.cons.VIDEO_LIBRARY, size=50, color=ft.colors.GREEN_400),
                        ft.Text(f"📹 {msg.get('file_name', 'Видео')}", color=ft.colors.GREEN_200, font_family="hack"),
                        ft.Text(msg.get('content', ''), color=ft.colors.GREEN_200, size=12, font_family="hack")
                    ])
                elif msg['type'] == 'audio':
                    content = ft.Column([
                        ft.Row([
                            ft.Icon(ft.cons.AUDIO_FILE, color=ft.colors.GREEN_400),
                            ft.Text(f"🎤 Голосовое сообщение", color=ft.colors.GREEN_200, font_family="hack"),
                            ft.IconButton(
                                icon=ft.cons.PLAY_ARROW,
                                icon_color=ft.colors.GREEN_400,
                                on_click=lambda _, url=msg['file_url']: self.play_audio(url)
                            )
                        ]),
                        ft.Text(msg.get('content', ''), color=ft.colors.GREEN_200, size=12, font_family="hack")
                    ])
                else:
                    content = ft.Text(
                        f"[{msg['type']}] {msg['content']}",
                        color=ft.colors.WHITE if is_me else ft.colors.GREEN_400,
                        font_family="hack"
                    )
                
                msg_bubble = ft.Container(
                    content=ft.Column([
                        content,
                        ft.Text(
                            msg['timestamp'].strftime('%H:%M'),
                            size=10,
                            color=ft.colors.GREY_400,
                            font_family="hack"
                        )
                    ]),
                    bgcolor="#003300" if is_me else "#001100",
                    padding=10,
                    border_radius=ft.border_radius.only(
                        top_left=20,
                        top_right=20,
                        bottom_left=5 if is_me else 20,
                        bottom_right=20 if is_me else 5
                    ),
                    margin=ft.margin.only(
                        left=50 if is_me else 0,
                        right=0 if is_me else 50
                    )
                )
                
                messages_list.controls.append(
                    ft.Row([
                        msg_bubble if is_me else ft.Container(),
                        ft.Container() if is_me else msg_bubble
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN if is_me else ft.MainAxisAlignment.START)
                )
            
            self.page.update()
        
        def send_message(e):
            if message_input.value or self.selected_file:
                file_data = None
                msg_type = 'text'
                
                # Если есть выбранный файл
                if self.selected_file:
                    file_data = self.selected_file
                    msg_type = file_data['file_type'].split('/')[0]
                    if msg_type not in ['image', 'video', 'audio']:
                        msg_type = 'file'
                
                self.fb.send_message(
                    self.current_user['uid'],
                    self.current_chat['uid'],
                    message_input.value or "",
                    msg_type,
                    file_data
                )
                
                message_input.value = ""
                self.selected_file = None
                selected_file_text.value = ""
                load_messages()
        
        def pick_files(e):
            def on_dialog_result(e: ft.FilePickerResultEvent):
                if e.files:
                    file_path = e.files[0].path
                    file_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
                    
                    # Загружаем файл
                    chat_id = f"{self.current_user['uid']}_{self.current_chat['uid']}"
                    file_data = self.fb.file_manager.upload_file(
                        file_path,
                        self.current_user['uid'],
                        chat_id,
                        file_type
                    )
                    
                    if file_data:
                        self.selected_file = file_data
                        selected_file_text.value = f"📎 Выбран: {os.path.basename(file_path)}"
                        self.page.update()
            
            file_picker = ft.FilePicker(on_result=on_dialog_result)
            self.page.overlay.append(file_picker)
            self.page.update()
            file_picker.pick_files(allow_multiple=False)
        
        def start_recording(e):
            nonlocal is_recording
            is_recording = True
            record_button.icon = ft.icons.STOP
            record_button.tooltip = "Остановить запись"
            
            # Начинаем запись в отдельном потоке
            def record():
                voice_file = self.voice_recorder.start_recording()
                self.selected_file = voice_file
            
            threading.Thread(target=record, daemon=True).start()
            self.page.update()
        
        def stop_recording(e):
            nonlocal is_recording
            is_recording = False
            record_button.icon = ft.icons.MIC
            record_button.tooltip = "Записать голосовое"
            
            voice_file = self.voice_recorder.stop_recording()
            if voice_file:
                chat_id = f"{self.current_user['uid']}_{self.current_chat['uid']}"
                file_data = self.fb.file_manager.upload_file(
                    voice_file,
                    self.current_user['uid'],
                    chat_id,
                    'audio/wav'
                )
                
                if file_data:
                    self.selected_file = file_data
                    selected_file_text.value = "🎤 Голосовое сообщение готово"
            
            self.page.update()
        
        def toggle_recording(e):
            if not is_recording:
                start_recording(e)
            else:
                stop_recording(e)
        
        def take_photo(e):
            def on_dialog_result(e: ft.FilePickerResultEvent):
                if e.files:
                    file_path = e.files[0].path
                    chat_id = f"{self.current_user['uid']}_{self.current_chat['uid']}"
                    file_data = self.fb.file_manager.upload_file(
                        file_path,
                        self.current_user['uid'],
                        chat_id,
                        'image/jpeg'
                    )
                    
                    if file_data:
                        self.selected_file = file_data
                        selected_file_text.value = "📷 Фото готово к отправке"
                        self.page.update()
            
            file_picker = ft.FilePicker(on_result=on_dialog_result)
            self.page.overlay.append(file_picker)
            self.page.update()
            file_picker.pick_files(allow_multiple=False, allowed_extensions=['jpg', 'jpeg', 'png', 'gif'])
        
        chat_header = ft.Container(
            content=ft.Row([
                ft.CircleAvatar(
                    foreground_image_url=self.current_chat.get('avatar_url', ''),
                    content=ft.Text(self.current_chat['username'][0].upper()) if not self.current_chat.get('avatar_url') else None,
                ),
                ft.Column([
                    ft.Text(self.current_chat['username'], color=ft.colors.GREEN_400, font_family="hack", weight=ft.FontWeight.BOLD),
                    ft.Text("online" if random.random() > 0.5 else "offline", color=ft.colors.GREEN_200, size=12, font_family="hack"),
                ]),
                ft.IconButton(icon=ft.icons.ARROW_BACK, icon_color=ft.colors.GREEN_400, on_click=lambda _: self.show_terminal_main())
            ]),
            bgcolor="#001100",
            padding=10,
            border=ft.border.all(1, ft.colors.GREEN_400)
        )
        
        record_button = ft.IconButton(
            icon=ft.icons.MIC,
            icon_color=ft.colors.GREEN_400,
            on_click=toggle_recording,
            tooltip="Записать голосовое"
        )
        
        chat_panel = ft.Container(
            content=ft.Column([
                chat_header,
                ft.Container(
                    content=messages_list,
                    expand=True,
                    padding=10
                ),
                selected_file_text,
                ft.Row([
                    ft.PopupMenuButton(
                        items=[
                            ft.PopupMenuItem(text="📷 Фото", on_click=lambda _: take_photo(None)),
                            ft.PopupMenuItem(text="🎥 Видео", on_click=lambda _: pick_files(None)),
                            ft.PopupMenuItem(text="📎 Файл", on_click=lambda _: pick_files(None)),
                        ],
                        icon=ft.cons.ATTACH_FILE,
                        icon_color=ft.colors.GREEN_400
                    ),
                    record_button,
                    message_input,
                    ft.IconButton(
                        icon=ft.icons.SEND,
                        icon_color=ft.colors.GREEN_400,
                        on_click=send_message
                    )
                ], alignment=ft.MainAxisAlignment.CENTER)
            ]),
            bgcolor="#000000",
            expand=True
        )
        
        self.page.add(chat_panel)
        load_messages()
        
        # Автообновление сообщений
        def update_messages():
            while self.current_chat:
                time.sleep(2)
                load_messages()
        
        threading.Thread(target=update_messages, daemon=True).start()
    
    def play_audio(self, url):
        """Воспроизведение аудио"""
        # В реальном приложении здесь будет код для воспроизведения
        self.page.show_snack_bar(ft.SnackBar(content=ft.Text("🔊 Воспроизведение аудио...")))
    
    def show_profile(self):
        self.page.clean()
        
        avatar = ft.CircleAvatar(
            foreground_image_url=self.current_user.get('avatar_url', ''),
            radius=50,
            content=ft.Text(self.current_user['username'][0].upper(), size=30) if not self.current_user.get('avatar_url') else None,
        )
        
        username_field = ft.TextField(
            label="> USERNAME",
            value=self.current_user['username'],
            border_color=ft.colors.GREEN_400,
            color=ft.colors.GREEN_400,
            cursor_color=ft.colors.GREEN_400,
            bgcolor="#001100",
            width=300,
            font_family="hack"
        )
        
        def change_avatar(e):
            def on_dialog_result(e: ft.FilePickerResultEvent):
                if e.files:
                    file_path = e.files[0].path
                    
                    # Загружаем аватарку
                    avatar_url = self.fb.upload_avatar(self.current_user['uid'], file_path)
                    
                    if avatar_url:
                        self.current_user['avatar_url'] = avatar_url
                        self.page.show_snack_bar(ft.SnackBar(content=ft.Text("✅ Аватарка обновлена")))
                        self.show_profile()  # Обновляем страницу
            
            file_picker = ft.FilePicker(on_result=on_dialog_result)
            self.page.overlay.append(file_picker)
            self.page.update()
            file_picker.pick_files(allow_multiple=False, allowed_extensions=['jpg', 'jpeg', 'png', 'gif'])
        
        def save_profile(e):
            new_username = username_field.value
            if new_username and new_username != self.current_user['username']:
                # Проверяем уникальность
                existing_user, _ = self.fb.get_user_by_username(new_username)
                if not existing_user:
                    self.fb.update_user(self.current_user['uid'], {'username': new_username})
                    self.current_user['username'] = new_username
                    self.page.show_snack_bar(ft.SnackBar(content=ft.Text("✅ Профиль обновлен")))
                else:
                    self.page.show_snack_bar(ft.SnackBar(content=ft.Text("❌ Username уже занят")))
        
        profile_panel = ft.Container(
            content=ft.Column([
                ft.Text("> ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ", size=20, color=ft.colors.GREEN_400, font_family="hack"),
                ft.Container(
                    content=ft.Stack([
                        avatar,
                        ft.Container(
                            content=ft.Icon(ft.cons.CAMERA_ALT, color=ft.colors.WHITE, size=20),
                            bgcolor=ft.colors.GREEN_400,
                            border_radius=15,
                            padding=5,
                            right=0,
                            bottom=0,
                            on_click=change_avatar
                        )
                    ]),
                    width=100,
                    height=100
                ),
                ft.Text(f"ID: {self.current_user['uid']}", color=ft.colors.GREEN_200, size=12, font_family="hack"),
                username_field,
                ft.ElevatedButton(
                    "> СОХРАНИТЬ",
                    on_click=save_profile,
                    style=ft.ButtonStyle(
                        color=ft.colors.GREEN_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.GREEN_400),
                    ),
                ),
                ft.ElevatedButton(
                    "> НАЗАД",
                    on_click=lambda _: self.show_terminal_main(),
                    style=ft.ButtonStyle(
                        color=ft.colors.GREEN_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.GREEN_400),
                    ),
                )
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor="#000000",
            padding=20,
            expand=True
        )
        
        self.page.add(
            ft.Column([
                self.matrix_container,
                profile_panel
            ], spacing=0, expand=True)
        )
    
    def show_support(self):
        self.page.clean()
        
        subject_field = ft.TextField(
            label="> ТЕМА",
            border_color=ft.colors.GREEN_400,
            color=ft.colors.GREEN_400,
            cursor_color=ft.colors.GREEN_400,
            bgcolor="#001100",
            width=300,
            font_family="hack"
        )
        
        message_field = ft.TextField(
            label="> СООБЩЕНИЕ",
            multiline=True,
            min_lines=3,
            max_lines=5,
            border_color=ft.colors.GREEN_400,
            color=ft.colors.GREEN_400,
            cursor_color=ft.colors.GREEN_400,
            bgcolor="#001100",
            width=300,
            font_family="hack"
        )
        
        def send_ticket(e):
            subject = subject_field.value
            message = message_field.value
            
            if subject and message:
                self.fb.create_ticket(
                    self.current_user['uid'],
                    self.current_user['username'],
                    subject,
                    message
                )
                self.page.show_snack_bar(ft.SnackBar(content=ft.Text("✅ Запрос отправлен в поддержку")))
                self.show_terminal_main()
        
        support_panel = ft.Container(
            content=ft.Column([
                ft.Text("> ТЕХНИЧЕСКАЯ ПОДДЕРЖКА", size=20, color=ft.colors.GREEN_400, font_family="hack"),
                ft.Text("Опишите вашу проблему:", color=ft.colors.GREEN_200, font_family="hack"),
                subject_field,
                message_field,
                ft.ElevatedButton(
                    "> ОТПРАВИТЬ",
                    on_click=send_ticket,
                    style=ft.ButtonStyle(
                        color=ft.colors.GREEN_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.GREEN_400),
                    ),
                ),
                ft.ElevatedButton(
                    "> НАЗАД",
                    on_click=lambda _: self.show_terminal_main(),
                    style=ft.ButtonStyle(
                        color=ft.colors.GREEN_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.GREEN_400),
                    ),
                )
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor="#000000",
            padding=20,
            expand=True
        )
        
        self.page.add(
            ft.Column([
                self.matrix_container,
                support_panel
            ], spacing=0, expand=True)
        )
    
    def show_notifications(self):
        self.page.clean()
        
        notifications_list = ft.ListView(expand=True, spacing=10)
        
        def load_notifications():
            notifications = self.fb.get_user_notifications(self.current_user['uid'])
            notifications_list.controls.clear()
            
            for notif in notifications:
                notif_card = ft.Container(
                    content=ft.Column([
                        ft.Text(notif['title'], color=ft.colors.GREEN_400, weight=ft.FontWeight.BOLD, font_family="hack"),
                        ft.Text(notif['body'], color=ft.colors.GREEN_200, font_family="hack"),
                        ft.Text(notif['created_at'].strftime('%H:%M %d.%m.%Y'), color=ft.colors.GREY_400, size=12, font_family="hack"),
                    ]),
                    bgcolor="#001100",
                    padding=10,
                    border=ft.border.all(1, ft.colors.GREEN_400),
                    border_radius=5
                )
                notifications_list.controls.append(notif_card)
            
            if not notifications:
                notifications_list.controls.append(
                    ft.Text("📭 Нет новых уведомлений", color=ft.colors.GREEN_400, font_family="hack")
                )
            
            self.page.update()
        
        notifications_panel = ft.Container(
            content=ft.Column([
                ft.Text("> УВЕДОМЛЕНИЯ", size=20, color=ft.colors.GREEN_400, font_family="hack"),
                notifications_list,
                ft.ElevatedButton(
                    "> НАЗАД",
                    on_click=lambda _: self.show_terminal_main(),
                    style=ft.ButtonStyle(
                        color=ft.colors.GREEN_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.GREEN_400),
                    ),
                )
            ]),
            bgcolor="#000000",
            padding=20,
            expand=True
        )
        
        self.page.add(
            ft.Column([
                self.matrix_container,
                notifications_panel
            ], spacing=0, expand=True)
        )
        
        load_notifications()
    
    def show_admin_panel(self):
        self.page.clean()
        
        admin_menu = ft.Column([
            ft.ListTile(
                title=ft.Text("> ТИКЕТЫ ПОДДЕРЖКИ", color=ft.colors.RED_400, font_family="hack"),
                leading=ft.Icon(ft.icons.SUPPORT_AGENT, color=ft.colors.RED_400),
                on_click=lambda _: self.show_admin_tickets(),
            ),
            ft.ListTile(
                title=ft.Text("> УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ", color=ft.colors.RED_400, font_family="hack"),
                leading=ft.Icon(ft.icons.PEOPLE, color=ft.colors.RED_400),
                on_click=lambda _: self.show_user_management(),
            ),
            ft.ListTile(
                title=ft.Text("> РАССЫЛКА", color=ft.colors.RED_400, font_family="hack"),
                leading=ft.Icon(ft.icons.CAMPAIGN, color=ft.colors.RED_400),
                on_click=lambda _: self.show_broadcast(),
            ),
            ft.Divider(color=ft.colors.RED_400),
            ft.ListTile(
                title=ft.Text("> НАЗАД", color=ft.colors.GREEN_400, font_family="hack"),
                leading=ft.Icon(ft.icons.ARROW_BACK, color=ft.colors.GREEN_400),
                on_click=lambda _: self.show_terminal_main(),
            ),
        ])
        
        admin_panel = ft.Container(
            content=ft.Column([
                ft.Text("""
    ╔══════════════════════════════════════════════════════════╗
    ║                  👑 АДМИН ПАНЕЛЬ 👑                     ║
    ╚══════════════════════════════════════════════════════════╝
                """, color=ft.colors.RED_400, font_family="hack"),
                admin_menu
            ]),
            bgcolor="#000000",
            padding=20,
            expand=True
        )
        
        self.page.add(
            ft.Column([
                self.matrix_container,
                admin_panel
            ], spacing=0, expand=True)
        )
    
    def show_admin_tickets(self):
        self.page.clean()
        
        tickets_list = ft.ListView(expand=True, spacing=10)
        
        def load_tickets():
            tickets = self.fb.get_tickets()
            tickets_list.controls.clear()
            
            for ticket in tickets:
                status_color = ft.colors.GREEN_400 if ticket['status'] == 'open' else ft.colors.GREY_400
                
                ticket_card = ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text(f"#{ticket['id'][:8]}", color=status_color, weight=ft.FontWeight.BOLD, font_family="hack"),
                            ft.Text(f"[{ticket['status']}]", color=status_color, font_family="hack"),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Text(f"От: {ticket['username']}", color=ft.colors.GREEN_400, font_family="hack"),
                        ft.Text(f"Тема: {ticket['subject']}", color=ft.colors.GREEN_200, weight=ft.FontWeight.BOLD, font_family="hack"),
                        ft.Text(ticket['message'], color=ft.colors.GREEN_200, font_family="hack"),
                        ft.Text(ticket['created_at'].strftime('%d.%m.%Y %H:%M'), color=ft.colors.GREY_400, size=12, font_family="hack"),
                        ft.Row([
                            ft.ElevatedButton(
                                "✅ Закрыть",
                                on_click=lambda _, t=ticket: close_ticket(t['id']),
                                style=ft.ButtonStyle(color=ft.colors.GREEN_400),
                                visible=ticket['status'] == 'open'
                            ),
                            ft.ElevatedButton(
                                "❌ Удалить",
                                on_click=lambda _, t=ticket: delete_ticket(t['id']),
                                style=ft.ButtonStyle(color=ft.colors.RED_400),
                            )
                        ])
                    ]),
                    bgcolor="#001100",
                    padding=10,
                    border=ft.border.all(1, status_color),
                    border_radius=5
                )
                tickets_list.controls.append(ticket_card)
            
            self.page.update()
        
        def close_ticket(ticket_id):
            self.fb.update_ticket_status(ticket_id, 'closed')
            load_tickets()
        
        def delete_ticket(ticket_id):
            self.fb.db.collection('tickets').document(ticket_id).delete()
            load_tickets()
        
        tickets_panel = ft.Container(
            content=ft.Column([
                ft.Text("> ТИКЕТЫ ПОДДЕРЖКИ", size=20, color=ft.colors.RED_400, font_family="hack"),
                ft.ElevatedButton(
                    "🔄 ОБНОВИТЬ",
                    on_click=lambda _: load_tickets(),
                    style=ft.ButtonStyle(color=ft.colors.GREEN_400),
                ),
                tickets_list,
                ft.ElevatedButton(
                    "> НАЗАД",
                    on_click=lambda _: self.show_admin_panel(),
                    style=ft.ButtonStyle(
                        color=ft.colors.GREEN_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.GREEN_400),
                    ),
                )
            ]),
            bgcolor="#000000",
            padding=20,
            expand=True
        )
        
        self.page.add(
            ft.Column([
                self.matrix_container,
                tickets_panel
            ], spacing=0, expand=True)
        )
        
        load_tickets()
    
    def show_user_management(self):
        self.page.clean()
        
        username_field = ft.TextField(
            label="> USERNAME",
            border_color=ft.colors.RED_400,
            color=ft.colors.RED_400,
            cursor_color=ft.colors.RED_400,
            bgcolor="#001100",
            width=300,
            font_family="hack"
        )
        
        result_text = ft.Text("", color=ft.colors.GREEN_400, font_family="hack")
        
        def ban_user(e):
            username = username_field.value
            if username:
                if self.fb.ban_user(username):
                    result_text.value = f"✅ Пользователь {username} забанен"
                else:
                    result_text.value = f"❌ Пользователь {username} не найден"
                self.page.update()
        
        def unban_user(e):
            username = username_field.value
            if username:
                if self.fb.unban_user(username):
                    result_text.value = f"✅ Пользователь {username} разбанен"
                else:
                    result_text.value = f"❌ Пользователь {username} не найден"
                self.page.update()
        
        def freeze_user(e):
            username = username_field.value
            if username:
                if self.fb.freeze_user(username):
                    result_text.value = f"✅ Пользователь {username} заморожен"
                else:
                    result_text.value = f"❌ Пользователь {username} не найден"
                self.page.update()
        
        def unfreeze_user(e):
            username = username_field.value
            if username:
                if self.fb.unfreeze_user(username):
                    result_text.value = f"✅ Пользователь {username} разморожен"
                else:
                    result_text.value = f"❌ Пользователь {username} не найден"
                self.page.update()
        
        management_panel = ft.Container(
            content=ft.Column([
                ft.Text("> УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ", size=20, color=ft.colors.RED_400, font_family="hack"),
                username_field,
                ft.Row([
                    ft.ElevatedButton("🚫 ЗАБАНИТЬ", on_click=ban_user, style=ft.ButtonStyle(color=ft.colors.RED_400)),
                    ft.ElevatedButton("✅ РАЗБАНИТЬ", on_click=unban_user, style=ft.ButtonStyle(color=ft.colors.GREEN_400)),
                ], alignment=ft.MainAxisAlignment.CENTER),
                ft.Row([
                    ft.ElevatedButton("❄️ ЗАМОРОЗИТЬ", on_click=freeze_user, style=ft.ButtonStyle(color=ft.colors.BLUE_400)),
                    ft.ElevatedButton("🔥 РАЗМОРОЗИТЬ", on_click=unfreeze_user, style=ft.ButtonStyle(color=ft.colors.ORANGE_400)),
                ], alignment=ft.MainAxisAlignment.CENTER),
                result_text,
                ft.ElevatedButton(
                    "> НАЗАД",
                    on_click=lambda _: self.show_admin_panel(),
                    style=ft.ButtonStyle(
                        color=ft.colors.GREEN_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.GREEN_400),
                    ),
                )
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor="#000000",
            padding=20,
            expand=True
        )
        
        self.page.add(
            ft.Column([
                self.matrix_container,
                management_panel
            ], spacing=0, expand=True)
        )
    
    def show_broadcast(self):
        self.page.clean()
        
        title_field = ft.TextField(
            label="> ЗАГОЛОВОК",
            border_color=ft.colors.RED_400,
            color=ft.colors.RED_400,
            cursor_color=ft.colors.RED_400,
            bgcolor="#001100",
            width=300,
            font_family="hack"
        )
        
        message_field = ft.TextField(
            label="> СООБЩЕНИЕ",
            multiline=True,
            min_lines=3,
            max_lines=5,
            border_color=ft.colors.RED_400,
            color=ft.colors.RED_400,
            cursor_color=ft.colors.RED_400,
            bgcolor="#001100",
            width=300,
            font_family="hack"
        )
        
        def send_broadcast(e):
            title = title_field.value
            message = message_field.value
            
            if title and message:
                self.fb.send_broadcast(title, message)
                self.page.show_snack_bar(ft.SnackBar(content=ft.Text("✅ Рассылка отправлена всем пользователям")))
                self.show_admin_panel()
        
        broadcast_panel = ft.Container(
            content=ft.Column([
                ft.Text("> РАССЫЛКА ПОЛЬЗОВАТЕЛЯМ", size=20, color=ft.colors.RED_400, font_family="hack"),
                ft.Text("Введите сообщение для рассылки:", color=ft.colors.RED_200, font_family="hack"),
                title_field,
                message_field,
                ft.Text("Пример: Вышла новая версия приложения! Обновитесь в Telegram канале", color=ft.colors.GREY_400, size=12, font_family="hack"),
                ft.ElevatedButton(
                    "📢 ОТПРАВИТЬ ВСЕМ",
                    on_click=send_broadcast,
                    style=ft.ButtonStyle(
                        color=ft.colors.RED_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.RED_400),
                    ),
                ),
                ft.ElevatedButton(
                    "> НАЗАД",
                    on_click=lambda _: self.show_admin_panel(),
                    style=ft.ButtonStyle(
                        color=ft.colors.GREEN_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.GREEN_400),
                    ),
                )
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor="#000000",
            padding=20,
            expand=True
        )
        
        self.page.add(
            ft.Column([
                self.matrix_container,
                broadcast_panel
            ], spacing=0, expand=True)
        )
    
    def show_chats(self):
        self.page.clean()
        
        chats_list = ft.ListView(expand=True, spacing=10)
        
        def load_chats():
            chats = self.fb.get_recent_chats(self.current_user['uid'])
            chats_list.controls.clear()
            
            if chats:
                for chat in chats:
                    user = chat['user']
                    last_msg = chat['last_message']
                    
                    chat_card = ft.Container(
                        content=ft.Row([
                            ft.CircleAvatar(
                                foreground_image_url=user.get('avatar_url', ''),
                                content=ft.Text(user['username'][0].upper()) if not user.get('avatar_url') else None,
                            ),
                            ft.Column([
                                ft.Text(user['username'], color=ft.colors.GREEN_400, weight=ft.FontWeight.BOLD, font_family="hack"),
                                ft.Text(
                                    f"{'📷 ' if last_msg['type'] == 'image' else '🎥 ' if last_msg['type'] == 'video' else '🎤 ' if last_msg['type'] == 'audio' else ''}{last_msg['content'][:30]}...",
                                    color=ft.colors.GREEN_200,
                                    size=12,
                                    font_family="hack"
                                ),
                            ], expand=True),
                            ft.Text(
                                last_msg['timestamp'].strftime('%H:%M'),
                                color=ft.colors.GREY_400,
                                size=12,
                                font_family="hack"
                            )
                        ]),
                        bgcolor="#001100",
                        padding=10,
                        border=ft.border.all(1, ft.colors.GREEN_400),
                        border_radius=5,
                        on_click=lambda _, u=user: self.start_chat(u)
                    )
                    chats_list.controls.append(chat_card)
            else:
                chats_list.controls.append(
                    ft.Text("📭 Нет активных чатов", color=ft.colors.GREEN_400, font_family="hack")
                )
            
            self.page.update()
        
        chats_panel = ft.Container(
            content=ft.Column([
                ft.Text("> ВАШИ ЧАТЫ", size=20, color=ft.colors.GREEN_400, font_family="hack"),
                ft.ElevatedButton(
                    "🔄 ОБНОВИТЬ",
                    on_click=lambda _: load_chats(),
                    style=ft.ButtonStyle(color=ft.colors.GREEN_400),
                ),
                chats_list,
                ft.ElevatedButton(
                    "> НАЗАД",
                    on_click=lambda _: self.show_terminal_main(),
                    style=ft.ButtonStyle(
                        color=ft.colors.GREEN_400,
                        bgcolor=ft.colors.BLACK,
                        side=ft.BorderSide(2, ft.colors.GREEN_400),
                    ),
                )
            ]),
            bgcolor="#000000",
            padding=20,
            expand=True
        )
        
        self.page.add(
            ft.Column([
                self.matrix_container,
                chats_panel
            ], spacing=0, expand=True)
        )
        
        load_chats()
    
    def logout(self):
        self.current_user = None
        self.current_chat = None
        self.show_login_screen()

def main(page: ft.Page):
    app = GhostProMessenger()
    app.main(page)

if __name__ == "__main__":
    ft.app(target=main)
