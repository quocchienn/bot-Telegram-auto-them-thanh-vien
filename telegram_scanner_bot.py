import asyncio
import random
import time
import json
import os
import logging
from datetime import datetime
from telethon import TelegramClient, errors
from telethon.tl.functions.channels import InviteToChannelRequest
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import sys

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print("=" * 80)
print("🤖 TELEGRAM USERNAME SCANNER BOT")
print("=" * 80)

# === CẤU HÌNH ===
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
SESSION_NAME = 'scanner_session'
ADMIN_USER_ID = os.environ.get('ADMIN_USER_ID', '')

# === CẤU HÌNH SCANNER ===
INPUT_TXT = "usernames.txt"
OUTPUT_JSON = "found_users.json"
ADDED_TXT = "added_users.txt"
CONFIG_FILE = "bot_config.json"
MIN_DELAY = 0.1
MAX_DELAY = 0.5
BATCH_SIZE = 20

class TelegramScanner:
    def __init__(self):
        self.client = None
        self.is_running = False
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
            'failed': 0
        }
        self.load_config()
    
    def load_config(self):
        """Tải cấu hình từ file"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                logger.info("✅ Đã tải cấu hình")
        except Exception as e:
            logger.error(f"❌ Lỗi tải cấu hình: {e}")
    
    def save_config(self):
        """Lưu cấu hình"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
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
            
            if not await self.client.is_user_authorized():
                if not self.config['phone']:
                    return False, "❌ Chưa cấu hình số điện thoại!"
                return False, "🔐 Chưa đăng nhập. Dùng /login"
            
            return True, "✅ Đã kết nối và đăng nhập!"
        except Exception as e:
            return False, f"❌ Lỗi kết nối: {str(e)}"
    
    async def login(self):
        """Đăng nhập vào Telegram"""
        try:
            if not self.client:
                return False, "❌ Client chưa được kết nối!"
            
            await self.client.send_code_request(self.config['phone'])
            return True, "📱 Mã xác minh đã được gửi. Dùng /verify <mã>"
        except Exception as e:
            return False, f"❌ Lỗi đăng nhập: {str(e)}"
    
    async def verify(self, code):
        """Xác minh mã OTP"""
        try:
            await self.client.sign_in(self.config['phone'], code)
            return True, "✅ Đăng nhập thành công!"
        except errors.SessionPasswordNeededError:
            return False, "🔒 Cần mật khẩu 2FA. Dùng /2fa <mật_khẩu>"
        except Exception as e:
            return False, f"❌ Lỗi xác minh: {str(e)}"
    
    async def verify_2fa(self, password):
        """Xác minh 2FA"""
        try:
            await self.client.sign_in(password=password)
            return True, "✅ Đăng nhập 2FA thành công!"
        except Exception as e:
            return False, f"❌ Lỗi 2FA: {str(e)}"
    
    def load_usernames(self):
        """Đọc username từ file"""
        if not os.path.exists(INPUT_TXT):
            self.create_sample_file()
            return []
        
        try:
            with open(INPUT_TXT, 'r', encoding='utf-8') as f:
                usernames = []
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if line.startswith('@'):
                            usernames.append(line[1:])
                        else:
                            usernames.append(line)
                return usernames
        except Exception as e:
            logger.error(f"❌ Lỗi đọc file: {e}")
            return []
    
    def create_sample_file(self):
        """Tạo file mẫu"""
        sample = [
            "# Thêm username vào đây (mỗi dòng một username)",
            "# Có thể bỏ qua @ ở đầu",
            "# Ví dụ:",
            "username1",
            "username2",
            "testuser"
        ]
        
        with open(INPUT_TXT, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sample))
        logger.info(f"📝 Đã tạo file {INPUT_TXT} mẫu")
    
    async def scan(self, count=None):
        """Quét username"""
        try:
            if not self.client or not await self.client.is_user_authorized():
                return False, "❌ Chưa đăng nhập!"
            
            usernames = self.load_usernames()
            if not usernames:
                return False, f"❌ Không có username trong {INPUT_TXT}"
            
            if count and count < len(usernames):
                usernames = random.sample(usernames, count)
            
            self.is_running = True
            found_users = []
            scanned = 0
            
            for username in usernames:
                if not self.is_running:
                    break
                
                try:
                    user = await self.client.get_entity(f"@{username}")
                    
                    if not getattr(user, 'bot', False):
                        user_info = {
                            'id': user.id,
                            'username': username,
                            'first_name': user.first_name or '',
                            'scanned_at': datetime.now().isoformat()
                        }
                        found_users.append(user_info)
                
                except (ValueError, errors.UsernameNotOccupiedError):
                    pass
                except Exception:
                    pass
                
                scanned += 1
                
                # Delay ngẫu nhiên
                if scanned % BATCH_SIZE == 0:
                    await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            
            # Lưu kết quả
            if found_users:
                self.save_results(found_users)
            
            self.is_running = False
            
            # Tính tỷ lệ
            success_rate = 0
            if scanned > 0:
                success_rate = len(found_users) / scanned * 100
            
            report = f"""
📊 **BÁO CÁO QUÉT**
🔍 Đã quét: {scanned} username
✅ Tìm thấy: {len(found_users)} user
🎯 Tỷ lệ: {success_rate:.2f}%
💾 Đã lưu: {OUTPUT_JSON}
"""
            return True, report
            
        except Exception as e:
            self.is_running = False
            return False, f"❌ Lỗi khi quét: {str(e)}"
    
    async def add_users(self, count=50):
        """Thêm user vào nhóm"""
        try:
            if not self.client or not await self.client.is_user_authorized():
                return False, "❌ Chưa đăng nhập!"
            
            if not self.config['target_group']:
                return False, "❌ Chưa cấu hình nhóm!"
            
            # Tải user đã tìm thấy
            found_users = self.load_found_users()
            if not found_users:
                return False, "❌ Không có user để thêm!"
            
            group = await self.client.get_entity(self.config['target_group'])
            users_to_add = random.sample(found_users, min(count, len(found_users)))
            
            self.is_running = True
            added = 0
            failed = 0
            
            for user_info in users_to_add:
                if not self.is_running:
                    break
                
                try:
                    user = await self.client.get_entity(f"@{user_info['username']}")
                    
                    if getattr(user, 'bot', False):
                        failed += 1
                        continue
                    
                    await self.client(InviteToChannelRequest(group, [user]))
                    added += 1
                    
                    # Ghi vào file
                    with open(ADDED_TXT, 'a', encoding='utf-8') as f:
                        f.write(f"{datetime.now().isoformat()}|@{user_info['username']}|{user.id}\n")
                
                except (errors.UserPrivacyRestrictedError, errors.UserAlreadyParticipantError):
                    failed += 1
                except Exception:
                    failed += 1
                
                # Delay
                await asyncio.sleep(random.uniform(MIN_DELAY * 2, MAX_DELAY * 2))
            
            self.is_running = False
            
            # Tính tỷ lệ
            success_rate = 0
            if len(users_to_add) > 0:
                success_rate = added / len(users_to_add) * 100
            
            report = f"""
📤 **BÁO CÁO THÊM USER**
✅ Đã thêm: {added}
❌ Thất bại: {failed}
📈 Tỷ lệ: {success_rate:.1f}%
"""
            return True, report
            
        except Exception as e:
            self.is_running = False
            return False, f"❌ Lỗi khi thêm: {str(e)}"
    
    def save_results(self, found_users):
        """Lưu kết quả"""
        try:
            data = {
                'scan_time': datetime.now().isoformat(),
                'total_found': len(found_users),
                'users': found_users
            }
            
            with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Lỗi lưu kết quả: {e}")
    
    def load_found_users(self):
        """Tải user đã tìm"""
        try:
            if os.path.exists(OUTPUT_JSON):
                with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('users', [])
        except Exception as e:
            logger.error(f"❌ Lỗi tải user: {e}")
        return []
    
    async def stop(self):
        """Dừng tác vụ"""
        self.is_running = False
        return "⏹️ Đã dừng"

# Khởi tạo scanner
scanner = TelegramScanner()

# ===== BOT HANDLERS =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
🤖 **Telegram Scanner Bot**

⚙️ **CẤU HÌNH:**
/setapi <api_id> <api_hash>
/setphone <số_điện_thoại>
/setgroup @username_group
/config

🔐 **ĐĂNG NHẬP:**
/connect
/login
/verify <mã>
/2fa <mật_khẩu>

🔍 **QUÉT:**
/scan [số_lượng]
/stats
/list

📤 **THÊM USER:**
/add [số_lượng]

🛠️ **KHÁC:**
/stop
/help
""")

async def setapi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text("❌ Dùng: /setapi <api_id> <api_hash>")
        return
    
    scanner.config['api_id'] = context.args[0]
    scanner.config['api_hash'] = context.args[1]
    scanner.save_config()
    await update.message.reply_text(f"✅ Đã cấu hình API")

async def setphone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Dùng: /setphone <số_điện_thoại>")
        return
    
    scanner.config['phone'] = context.args[0]
    scanner.save_config()
    await update.message.reply_text(f"✅ Đã cấu hình số điện thoại")

async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Dùng: /setgroup @username_group")
        return
    
    scanner.config['target_group'] = context.args[0]
    scanner.config['is_configured'] = True
    scanner.save_config()
    await update.message.reply_text(f"✅ Đã cấu hình nhóm")

async def config_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config_text = f"""
⚙️ **CẤU HÌNH:**
API_ID: {scanner.config.get('api_id', '❌ Chưa có')}
API_HASH: {scanner.config.get('api_hash', '❌ Chưa có')[:10]}...
Phone: {scanner.config.get('phone', '❌ Chưa có')}
Nhóm: {scanner.config.get('target_group', '❌ Chưa có')}
"""
    await update.message.reply_text(config_text)

async def connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    success, msg = await scanner.connect_client()
    await update.message.reply_text(msg)

async def login_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    success, msg = await scanner.login()
    await update.message.reply_text(msg)

async def verify_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Dùng: /verify <mã>")
        return
    
    success, msg = await scanner.verify(context.args[0])
    await update.message.reply_text(msg)

async def tfa_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Dùng: /2fa <mật_khẩu>")
        return
    
    success, msg = await scanner.verify_2fa(context.args[0])
    await update.message.reply_text(msg)

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if scanner.is_running:
        await update.message.reply_text("⚠️ Đang chạy tác vụ khác!")
        return
    
    count = int(context.args[0]) if context.args else None
    
    msg = await update.message.reply_text("🔍 Đang quét...")
    
    async def task():
        success, result = await scanner.scan(count)
        await msg.edit_text(result)
    
    asyncio.create_task(task())

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if scanner.is_running:
        await update.message.reply_text("⚠️ Đang chạy tác vụ khác!")
        return
    
    count = int(context.args[0]) if context.args else 50
    
    msg = await update.message.reply_text("📤 Đang thêm user...")
    
    async def task():
        success, result = await scanner.add_users(count)
        await msg.edit_text(result)
    
    asyncio.create_task(task())

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    found_users = scanner.load_found_users()
    
    stats = f"""
📊 **THỐNG KÊ:**
User đã tìm: {len(found_users)}
File: {OUTPUT_JSON}
"""
    
    if found_users:
        stats += "\n📋 **5 user gần nhất:**\n"
        for i, user in enumerate(found_users[-5:], 1):
            name = user.get('first_name', '') or f"@{user.get('username', '')}"
            stats += f"{i}. {name}\n"
    
    await update.message.reply_text(stats)

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    found_users = scanner.load_found_users()
    
    if not found_users:
        await update.message.reply_text("❌ Chưa có user nào!")
        return
    
    # Chia thành các tin nhắn nhỏ
    chunk_size = 15
    for i in range(0, len(found_users), chunk_size):
        chunk = found_users[i:i+chunk_size]
        text = f"📋 User {i+1}-{i+len(chunk)}:\n\n"
        
        for user in chunk:
            text += f"• @{user.get('username', '')}\n"
        
        await update.message.reply_text(text)
        await asyncio.sleep(0.3)

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await scanner.stop()
    await update.message.reply_text(msg)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
ℹ️ **HƯỚNG DẪN:**

1. Cấu hình API từ my.telegram.org:
   /setapi <api_id> <api_hash>

2. Cấu hình số điện thoại:
   /setphone <số_điện_thoại>

3. Cấu hình nhóm:
   /setgroup @username_group

4. Đăng nhập:
   /connect → /login → /verify <mã>

5. Thêm username vào file usernames.txt

6. Quét:
   /scan [số_lượng]

7. Thêm user:
   /add [số_lượng]
""")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Lỗi: {context.error}")
    if update and update.message:
        await update.message.reply_text(f"⚠️ Lỗi: {context.error}")

def main():
    """Hàm chính"""
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN chưa được cấu hình!")
        print("ℹ️ Vui lòng đặt biến môi trường BOT_TOKEN trên Render")
        return
    
    # Kiểm tra file usernames.txt
    if not os.path.exists(INPUT_TXT):
        scanner.create_sample_file()
    
    # Tạo ứng dụng bot
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Thêm handlers
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
    application.add_handler(CommandHandler("add", add_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("list", list_cmd))
    application.add_handler(CommandHandler("stop", stop_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    
    # Xử lý lỗi
    application.add_error_handler(error_handler)
    
    print("🤖 Bot đang khởi động...")
    print(f"📁 File username: {INPUT_TXT}")
    print("=" * 80)
    
    # Chạy bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
