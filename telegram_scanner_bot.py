import asyncio
import random
import time
import json
import os
import logging
from datetime import datetime
from telethon import TelegramClient, errors
from telethon.tl.functions.channels import InviteToChannelRequest
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print("=" * 80)
print("🤖 TELEGRAM USERNAME SCANNER BOT")
print("=" * 80)

# === CẤU HÌNH MẶC ĐỊNH ===
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
SESSION_NAME = 'session_scanner'
ADMIN_USER_ID = os.environ.get('ADMIN_USER_ID', '')

# === CẤU HÌNH SCANNER ===
SCAN_ATTEMPTS = 500
ADD_ATTEMPTS = 100
MIN_DELAY = 0.1
MAX_DELAY = 0.5
BATCH_SIZE = 20
INPUT_TXT = "usernames.txt"
OUTPUT_JSON = "found_users.json"
ADDED_TXT = "added_users.txt"
CONFIG_FILE = "bot_config.json"

class TelegramScanner:
    def __init__(self):
        self.client = None
        self.is_running = False
        self.current_task = None
        self.config = {
            'api_id': '',
            'api_hash': '',
            'target_group': '',
            'phone': '',
            'is_configured': False
        }
        self.stats = {
            'scanned': 0,
            'found': 0,
            'added': 0,
            'failed': 0,
            'start_time': None
        }
        self.load_config()
    
    def load_config(self):
        """Tải cấu hình từ file"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                logger.info("✅ Đã tải cấu hình từ file")
        except Exception as e:
            logger.error(f"❌ Lỗi tải cấu hình: {e}")
    
    def save_config(self):
        """Lưu cấu hình vào file"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.info("💾 Đã lưu cấu hình")
        except Exception as e:
            logger.error(f"❌ Lỗi lưu cấu hình: {e}")
    
    async def connect_client(self):
        """Kết nối Telethon client"""
        try:
            if not self.config['api_id'] or not self.config['api_hash']:
                return False, "❌ Chưa cấu hình API_ID và API_HASH!"
            
            self.client = TelegramClient(
                SESSION_NAME,
                int(self.config['api_id']),
                self.config['api_hash']
            )
            
            await self.client.connect()
            return True, "✅ Đã kết nối client!"
        except Exception as e:
            return False, f"❌ Lỗi kết nối: {str(e)}"
    
    async def login(self):
        """Đăng nhập vào Telegram"""
        try:
            if not self.client:
                return False, "❌ Client chưa được kết nối!"
            
            if await self.client.is_user_authorized():
                return True, "✅ Đã đăng nhập từ trước!"
            
            if not self.config['phone']:
                return False, "❌ Chưa cấu hình số điện thoại!"
            
            await self.client.send_code_request(self.config['phone'])
            return False, "📱 Mã xác minh đã được gửi. Vui lòng nhập mã bằng lệnh /verify <mã>"
        except Exception as e:
            return False, f"❌ Lỗi đăng nhập: {str(e)}"
    
    async def verify(self, code):
        """Xác minh mã OTP"""
        try:
            await self.client.sign_in(self.config['phone'], code)
            return True, "✅ Đăng nhập thành công!"
        except errors.SessionPasswordNeededError:
            return False, "🔒 Cần mật khẩu 2FA. Vui lòng dùng lệnh /2fa <mật_khẩu>"
        except Exception as e:
            return False, f"❌ Lỗi xác minh: {str(e)}"
    
    async def verify_2fa(self, password):
        """Xác minh 2FA"""
        try:
            await self.client.sign_in(password=password)
            return True, "✅ Đăng nhập 2FA thành công!"
        except Exception as e:
            return False, f"❌ Lỗi 2FA: {str(e)}"
    
    def load_usernames_from_file(self):
        """Đọc username từ file txt"""
        usernames = []
        
        if os.path.exists(INPUT_TXT):
            try:
                with open(INPUT_TXT, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if line.startswith('@'):
                                usernames.append(line[1:])
                            else:
                                usernames.append(line)
                
                logger.info(f"📁 Đã đọc {len(usernames)} username từ {INPUT_TXT}")
                return usernames
            except Exception as e:
                logger.error(f"❌ Lỗi đọc file: {e}")
                return []
        else:
            logger.warning(f"⚠️ File {INPUT_TXT} không tồn tại")
            self.create_sample_usernames_file()
            return []
    
    def create_sample_usernames_file(self):
        """Tạo file username mẫu"""
        sample_users = [
            "user1", "user2", "testuser", "example", "demo",
            "admin", "support", "help", "info", "contact"
        ]
        
        with open(INPUT_TXT, "w", encoding="utf-8") as f:
            f.write("# Danh sách username để quét (mỗi dòng một username)\n")
            f.write("# Có thể bỏ qua @ ở đầu\n\n")
            for user in sample_users:
                f.write(f"{user}\n")
        
        logger.info(f"📝 Đã tạo file {INPUT_TXT} mẫu")
    
    def generate_usernames(self, count):
        """Tạo username tự động"""
        common_words = ['user', 'test', 'vip', 'pro', 'master', 'tech', 
                       'hack', 'free', 'premium', 'shadow', 'rocket', 
                       'official', 'real', 'alpha', 'beta', 'prime']
        
        usernames = set()
        while len(usernames) < count:
            word = random.choice(common_words)
            num = random.randint(1, 9999)
            
            patterns = [
                f"{word}{num}", f"{word}_{num}", f"{num}{word}",
                f"{word}{random.choice(common_words)}", f"real{word}{num}"
            ]
            
            username = random.choice(patterns).lower()
            if 5 <= len(username) <= 32:
                usernames.add(username)
        
        return list(usernames)[:count]
    
    async def scan_usernames(self, count=None):
        """Quét username từ file"""
        try:
            if not self.client or not await self.client.is_user_authorized():
                return False, "❌ Chưa đăng nhập! Dùng /login trước"
            
            self.is_running = True
            self.stats = {
                'scanned': 0,
                'found': 0,
                'start_time': time.time(),
                'found_users': []
            }
            
            # Đọc username từ file
            usernames = self.load_usernames_from_file()
            if not usernames:
                return False, f"❌ Không có username trong file {INPUT_TXT}!"
            
            # Giới hạn số lượng
            if count and count < len(usernames):
                usernames = random.sample(usernames, count)
            
            random.shuffle(usernames)
            found_users = []
            
            # Quét theo batch
            batches = [usernames[i:i+BATCH_SIZE] for i in range(0, len(usernames), BATCH_SIZE)]
            
            progress_msg = f"🔍 Đang quét {len(usernames)} username...\n0/{len(usernames)}"
            
            for batch_num, batch in enumerate(batches, 1):
                if not self.is_running:
                    break
                
                for username in batch:
                    try:
                        user = await self.client.get_entity(f"@{username}")
                        
                        if not getattr(user, 'bot', False):
                            user_info = {
                                'id': user.id,
                                'username': username,
                                'first_name': user.first_name or '',
                                'last_name': user.last_name or '',
                                'scanned_at': datetime.now().isoformat()
                            }
                            found_users.append(user_info)
                        
                    except (ValueError, errors.UsernameNotOccupiedError):
                        pass
                    except Exception as e:
                        logger.debug(f"Lỗi với @{username}: {type(e).__name__}")
                    
                    self.stats['scanned'] += 1
                
                # Delay giữa các batch
                if batch_num < len(batches) and self.is_running:
                    await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            
            self.stats['found'] = len(found_users)
            self.stats['found_users'] = found_users
            
            # Lưu kết quả
            if found_users:
                self.save_results(found_users)
            
            elapsed = time.time() - self.stats['start_time']
            
            report = f"""
📊 **BÁO CÁO QUÉT**
⏱️ Thời gian: {elapsed:.1f}s
📁 Từ file: {INPUT_TXT}
🔍 Đã quét: {self.stats['scanned']} username
✅ Tìm thấy: {self.stats['found']} user
⚡ Tốc độ: {self.stats['scanned']/elapsed:.1f} user/giây
🎯 Tỷ lệ: {self.stats['found']/self.stats['scanned']*100:.2f}%
💾 Đã lưu: {OUTPUT_JSON}
"""
            
            return True, report
            
        except Exception as e:
            logger.error(f"Lỗi khi quét: {e}")
            return False, f"❌ Lỗi khi quét: {str(e)}"
        finally:
            self.is_running = False
    
    async def add_users_to_group(self, count=100):
        """Thêm user vào nhóm"""
        try:
            if not self.client or not await self.client.is_user_authorized():
                return False, "❌ Chưa đăng nhập!"
            
            if not self.config['target_group']:
                return False, "❌ Chưa cấu hình nhóm mục tiêu!"
            
            # Tải user đã tìm thấy
            found_users = self.load_found_users()
            if not found_users:
                return False, "❌ Không có user nào để thêm!"
            
            self.is_running = True
            self.stats['start_time'] = time.time()
            
            # Lấy entity nhóm
            group = await self.client.get_entity(self.config['target_group'])
            
            # Chọn user để thêm
            users_to_add = random.sample(found_users, min(count, len(found_users)))
            
            added_count = 0
            failed_count = 0
            
            for i, user_info in enumerate(users_to_add, 1):
                if not self.is_running:
                    break
                
                try:
                    user = await self.client.get_entity(f"@{user_info['username']}")
                    
                    if getattr(user, 'bot', False):
                        failed_count += 1
                        continue
                    
                    await self.client(InviteToChannelRequest(group, [user]))
                    added_count += 1
                    
                    # Ghi vào file
                    with open(ADDED_TXT, "a", encoding="utf-8") as f:
                        f.write(f"{datetime.now().isoformat()}|@{user_info['username']}|{user.id}\n")
                    
                except (errors.UserPrivacyRestrictedError, errors.UserAlreadyParticipantError):
                    failed_count += 1
                except Exception:
                    failed_count += 1
                
                # Delay
                if i < len(users_to_add) and self.is_running:
                    await asyncio.sleep(random.uniform(MIN_DELAY * 3, MAX_DELAY * 3))
            
            elapsed = time.time() - self.stats['start_time']
            
            report = f"""
📤 **BÁO CÁO THÊM USER**
✅ Đã thêm: {added_count}
❌ Thất bại: {failed_count}
⏱️ Thời gian: {elapsed:.1f}s
📈 Tỷ lệ: {added_count/len(users_to_add)*100:.1f}%
"""
            
            return True, report
            
        except Exception as e:
            logger.error(f"Lỗi khi thêm user: {e}")
            return False, f"❌ Lỗi khi thêm user: {str(e)}"
        finally:
            self.is_running = False
    
    def save_results(self, found_users):
        """Lưu kết quả quét"""
        try:
            data = {
                'scan_time': datetime.now().isoformat(),
                'total_scanned': self.stats['scanned'],
                'total_found': len(found_users),
                'users': found_users
            }
            
            with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 Đã lưu {len(found_users)} user vào {OUTPUT_JSON}")
        except Exception as e:
            logger.error(f"❌ Lỗi lưu kết quả: {e}")
    
    def load_found_users(self):
        """Tải user đã tìm thấy"""
        try:
            if os.path.exists(OUTPUT_JSON):
                with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get('users', [])
        except Exception as e:
            logger.error(f"❌ Lỗi tải user: {e}")
        return []
    
    async def stop(self):
        """Dừng tác vụ hiện tại"""
        self.is_running = False
        return "⏹️ Đã dừng tác vụ!"
    
    def get_status(self):
        """Lấy trạng thái"""
        status = [
            f"🤖 **TRẠNG THÁI BOT**",
            f"🏃 Đang chạy: {'✅' if self.is_running else '❌'}",
            f"🔌 Đã kết nối: {'✅' if self.client and self.client.is_connected() else '❌'}",
            f"⚙️ Đã cấu hình: {'✅' if self.config['is_configured'] else '❌'}"
        ]
        
        if self.config['is_configured']:
            status.append(f"📱 Phone: {self.config.get('phone', 'Chưa có')}")
            status.append(f"🎯 Nhóm: {self.config.get('target_group', 'Chưa có')}")
        
        found_users = self.load_found_users()
        status.append(f"📊 User đã tìm: {len(found_users)}")
        
        return "\n".join(status)

# Khởi tạo scanner
scanner = TelegramScanner()

# ===== TELEGRAM BOT HANDLERS =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /start"""
    welcome_text = """
🤖 **Telegram Scanner Bot**

Các lệnh có sẵn:

⚙️ **CẤU HÌNH**
/setapi <api_id> <api_hash>
/setphone <số_điện_thoại>
/setgroup @username_group
/config - Xem cấu hình hiện tại

🔐 **ĐĂNG NHẬP**
/connect - Kết nối client
/login - Đăng nhập Telegram
/verify <mã> - Xác minh OTP
/2fa <mật_khẩu> - Xác minh 2FA

🔍 **SCANNER**
/scan [số_lượng] - Quét từ file (mặc định: tất cả)
/scangen <số_lượng> - Quét username tự sinh

📤 **THÊM USER**
/add [số_lượng] - Thêm vào nhóm (mặc định: 100)

📊 **THÔNG TIN**
/status - Trạng thái bot
/stats - Thống kê
/listusers - Xem user đã tìm

🛠️ **QUẢN LÝ**
/stop - Dừng tác vụ
/clear - Xóa dữ liệu
/help - Trợ giúp
"""
    await update.message.reply_text(welcome_text)

async def setapi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cấu hình API_ID và API_HASH"""
    if len(context.args) != 2:
        await update.message.reply_text("❌ Sai cú pháp! Dùng: /setapi <api_id> <api_hash>")
        return
    
    api_id, api_hash = context.args
    scanner.config['api_id'] = api_id
    scanner.config['api_hash'] = api_hash
    scanner.save_config()
    
    await update.message.reply_text(f"✅ Đã cấu hình API!\nAPI_ID: {api_id}\nAPI_HASH: {api_hash[:10]}...")

async def setphone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cấu hình số điện thoại"""
    if not context.args:
        await update.message.reply_text("❌ Sai cú pháp! Dùng: /setphone <số_điện_thoại>")
        return
    
    phone = context.args[0]
    scanner.config['phone'] = phone
    scanner.save_config()
    
    await update.message.reply_text(f"✅ Đã cấu hình số điện thoại: {phone}")

async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cấu hình nhóm mục tiêu"""
    if not context.args:
        await update.message.reply_text("❌ Sai cú pháp! Dùng: /setgroup @username_group")
        return
    
    group = context.args[0]
    scanner.config['target_group'] = group
    scanner.config['is_configured'] = True
    scanner.save_config()
    
    await update.message.reply_text(f"✅ Đã cấu hình nhóm: {group}")

async def connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kết nối Telethon client"""
    await update.message.reply_text("🔄 Đang kết nối...")
    success, message = await scanner.connect_client()
    await update.message.reply_text(message)

async def login_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Đăng nhập vào Telegram"""
    await update.message.reply_text("🔄 Đang đăng nhập...")
    success, message = await scanner.login()
    await update.message.reply_text(message)

async def verify_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xác minh mã OTP"""
    if not context.args:
        await update.message.reply_text("❌ Sai cú pháp! Dùng: /verify <mã>")
        return
    
    code = context.args[0]
    await update.message.reply_text("🔄 Đang xác minh...")
    success, message = await scanner.verify(code)
    await update.message.reply_text(message)

async def tfa_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xác minh 2FA"""
    if not context.args:
        await update.message.reply_text("❌ Sai cú pháp! Dùng: /2fa <mật_khẩu>")
        return
    
    password = context.args[0]
    await update.message.reply_text("🔄 Đang xác minh 2FA...")
    success, message = await scanner.verify_2fa(password)
    await update.message.reply_text(message)

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quét username từ file"""
    if scanner.is_running:
        await update.message.reply_text("⚠️ Bot đang chạy tác vụ khác!")
        return
    
    count = int(context.args[0]) if context.args else None
    
    # Gửi thông báo bắt đầu
    msg = await update.message.reply_text(f"🔍 Bắt đầu quét từ file {INPUT_TXT}...")
    
    # Chạy quét trong background
    async def scan_task():
        success, result = await scanner.scan_usernames(count)
        await msg.edit_text(result)
    
    asyncio.create_task(scan_task())

async def scangen_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quét username tự sinh"""
    if scanner.is_running:
        await update.message.reply_text("⚠️ Bot đang chạy tác vụ khác!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Sai cú pháp! Dùng: /scangen <số_lượng>")
        return
    
    count = int(context.args[0])
    
    # Tạo username và lưu vào file tạm
    usernames = scanner.generate_usernames(count)
    
    temp_file = "temp_usernames.txt"
    with open(temp_file, "w", encoding="utf-8") as f:
        for username in usernames:
            f.write(f"{username}\n")
    
    # Lưu file gốc và thay thế tạm thời
    original_file = INPUT_TXT
    if os.path.exists(original_file):
        os.rename(original_file, f"{original_file}.backup")
    
    os.rename(temp_file, original_file)
    
    msg = await update.message.reply_text(f"🔍 Bắt đầu quét {count} username tự sinh...")
    
    async def scan_task():
        success, result = await scanner.scan_usernames(count)
        
        # Khôi phục file gốc
        if os.path.exists(f"{original_file}.backup"):
            os.remove(original_file)
            os.rename(f"{original_file}.backup", original_file)
        
        await msg.edit_text(result)
    
    asyncio.create_task(scan_task())

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Thêm user vào nhóm"""
    if scanner.is_running:
        await update.message.reply_text("⚠️ Bot đang chạy tác vụ khác!")
        return
    
    count = int(context.args[0]) if context.args else ADD_ATTEMPTS
    
    msg = await update.message.reply_text(f"📤 Bắt đầu thêm {count} user...")
    
    async def add_task():
        success, result = await scanner.add_users_to_group(count)
        await msg.edit_text(result)
    
    asyncio.create_task(add_task())

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dừng tác vụ"""
    message = await scanner.stop()
    await update.message.reply_text(message)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem trạng thái"""
    status_text = scanner.get_status()
    await update.message.reply_text(status_text)

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem thống kê"""
    found_users = scanner.load_found_users()
    
    stats_text = f"""
📈 **THỐNG KÊ**
📊 User đã tìm: {len(found_users)}
📁 File: {OUTPUT_JSON}

📋 **5 user gần nhất:**
"""
    
    for i, user in enumerate(found_users[-5:], 1):
        name = user.get('first_name', '') or f"@{user.get('username', '')}"
        stats_text += f"{i}. {name} (@{user.get('username', '')})\n"
    
    await update.message.reply_text(stats_text)

async def listusers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liệt kê user đã tìm"""
    found_users = scanner.load_found_users()
    
    if not found_users:
        await update.message.reply_text("❌ Chưa có user nào được tìm thấy!")
        return
    
    # Chia thành các phần nhỏ để tránh tin nhắn quá dài
    chunk_size = 20
    for i in range(0, len(found_users), chunk_size):
        chunk = found_users[i:i+chunk_size]
        text = f"📋 User {i+1}-{min(i+chunk_size, len(found_users))}/{len(found_users)}:\n\n"
        
        for j, user in enumerate(chunk, i+1):
            name = user.get('first_name', '') or f"@{user.get('username', '')}"
            text += f"{j}. {name} (@{user.get('username', '')})\n"
        
        await update.message.reply_text(text)
        await asyncio.sleep(0.5)  # Delay giữa các tin nhắn

async def config_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem cấu hình"""
    config_text = f"""
⚙️ **CẤU HÌNH HIỆN TẠI**
API_ID: {scanner.config.get('api_id', 'Chưa cấu hình')}
API_HASH: {scanner.config.get('api_hash', 'Chưa cấu hình')[:10]}...
Phone: {scanner.config.get('phone', 'Chưa cấu hình')}
Nhóm: {scanner.config.get('target_group', 'Chưa cấu hình')}
Trạng thái: {'✅ Đã cấu hình' if scanner.config['is_configured'] else '❌ Chưa cấu hình'}
"""
    await update.message.reply_text(config_text)

async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xóa dữ liệu"""
    try:
        if os.path.exists(OUTPUT_JSON):
            os.remove(OUTPUT_JSON)
        if os.path.exists(ADDED_TXT):
            os.remove(ADDED_TXT)
        await update.message.reply_text("✅ Đã xóa dữ liệu!")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi khi xóa: {str(e)}")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hiển thị trợ giúp"""
    help_text = """
ℹ️ **HƯỚNG DẪN SỬ DỤNG**

1️⃣ **CẤU HÌNH BAN ĐẦU:**
/setapi <api_id> <api_hash> - Lấy từ my.telegram.org
/setphone <số_điện_thoại> - Số điện thoại Telegram
/setgroup @username_group - Nhóm cần thêm user

2️⃣ **ĐĂNG NHẬP:**
/connect - Kết nối client
/login - Đăng nhập (sẽ nhận mã OTP)
/verify <mã> - Nhập mã OTP
/2fa <mật_khẩu> - Nếu có 2FA

3️⃣ **QUÉT USERNAME:**
- Thêm username vào file `usernames.txt`
- Mỗi dòng một username, có thể bỏ @
- Dùng lệnh /scan để quét

4️⃣ **THÊM USER:**
/add [số_lượng] - Thêm user vào nhóm

⚠️ **LƯU Ý:**
- Chỉ quét user từ file `usernames.txt`
- Session được lưu tự động
- Dữ liệu lưu trong file JSON
"""
    await update.message.reply_text(help_text)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lỗi"""
    logger.error(f"Lỗi: {context.error}")
    if update and update.message:
        await update.message.reply_text(f"⚠️ Đã xảy ra lỗi: {context.error}")

async def main():
    """Hàm chính khởi động bot"""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN chưa được cấu hình!")
        logger.info("ℹ️ Vui lòng đặt biến môi trường BOT_TOKEN")
        return
    
    # Kiểm tra và tạo file usernames.txt nếu chưa có
    if not os.path.exists(INPUT_TXT):
        scanner.create_sample_usernames_file()
    
    # Tạo ứng dụng bot
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Thêm các handler
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setapi", setapi))
    application.add_handler(CommandHandler("setphone", setphone))
    application.add_handler(CommandHandler("setgroup", setgroup))
    application.add_handler(CommandHandler("config", config_cmd))
    application.add_handler(CommandHandler("connect", connect_cmd))
    application.add_handler(CommandHandler("login", login_cmd))
    application.add_handler(CommandHandler("verify", verify_cmd))
    application.add_handler(CommandHandler("2fa", tfa_cmd))
    application.add_handler(CommandHandler("scan", scan_cmd))
    application.add_handler(CommandHandler("scangen", scangen_cmd))
    application.add_handler(CommandHandler("add", add_cmd))
    application.add_handler(CommandHandler("stop", stop_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("listusers", listusers_cmd))
    application.add_handler(CommandHandler("clear", clear_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    
    # Xử lý lỗi
    application.add_error_handler(error_handler)
    
    # Khởi động bot
    print("🤖 Bot đang khởi động...")
    print(f"📁 File username: {INPUT_TXT}")
    print(f"💾 File config: {CONFIG_FILE}")
    print("=" * 80)
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    print("✅ Bot đã khởi động thành công!")
    print("📲 Tìm bot trên Telegram và dùng /start để bắt đầu")
    
    # Giữ bot chạy
    try:
        while True:
            await asyncio.sleep(3600)  # Giữ bot chạy
    except KeyboardInterrupt:
        print("\n👋 Đang dừng bot...")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    # Chạy bot
    asyncio.run(main())
