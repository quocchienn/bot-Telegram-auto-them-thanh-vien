import asyncio
import random
import time
import json
import os
import logging
from datetime import datetime
from telethon import TelegramClient, errors
from telethon.tl.functions.channels import InviteToChannelRequest
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

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
📊 <b>BÁO CÁO QUÉT</b>
⏱️ Thời gian: Đã xong
📁 Từ file: {INPUT_TXT}
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
📤 <b>BÁO CÁO THÊM USER</b>
✅ Đã thêm: {added}
❌ Thất bại: {failed}
⏱️ Thời gian: Đã xong
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

# Khởi tạo aiogram bot với cấu hình mới
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ===== BOT HANDLERS =====

@dp.message(Command("start"))
async def cmd_start(message: Message):
    welcome_text = """
🤖 <b>Telegram Scanner Bot</b>

<b>⚙️ CẤU HÌNH:</b>
/setapi <code>&lt;api_id&gt; &lt;api_hash&gt;</code>
/setphone <code>&lt;số_điện_thoại&gt;</code>
/setgroup <code>@username_group</code>
/config

<b>🔐 ĐĂNG NHẬP:</b>
/connect
/login
/verify <code>&lt;mã&gt;</code>
/2fa <code>&lt;mật_khẩu&gt;</code>

<b>🔍 QUÉT:</b>
/scan <code>[số_lượng]</code>
/stats
/list

<b>📤 THÊM USER:</b>
/add <code>[số_lượng]</code>

<b>🛠️ KHÁC:</b>
/stop
/help
"""
    await message.answer(welcome_text)

@dp.message(Command("setapi"))
async def cmd_setapi(message: Message):
    args = message.text.split()[1:]
    if len(args) != 2:
        await message.answer("❌ <b>Sai cú pháp!</b>\nDùng: <code>/setapi &lt;api_id&gt; &lt;api_hash&gt;</code>")
        return
    
    scanner.config['api_id'] = args[0]
    scanner.config['api_hash'] = args[1]
    scanner.save_config()
    await message.answer(f"✅ <b>Đã cấu hình API!</b>\nAPI_ID: <code>{args[0]}</code>\nAPI_HASH: <code>{args[1][:10]}...</code>")

@dp.message(Command("setphone"))
async def cmd_setphone(message: Message):
    args = message.text.split()[1:]
    if not args:
        await message.answer("❌ <b>Sai cú pháp!</b>\nDùng: <code>/setphone &lt;số_điện_thoại&gt;</code>")
        return
    
    scanner.config['phone'] = args[0]
    scanner.save_config()
    await message.answer(f"✅ <b>Đã cấu hình số điện thoại:</b> <code>{args[0]}</code>")

@dp.message(Command("setgroup"))
async def cmd_setgroup(message: Message):
    args = message.text.split()[1:]
    if not args:
        await message.answer("❌ <b>Sai cú pháp!</b>\nDùng: <code>/setgroup @username_group</code>")
        return
    
    scanner.config['target_group'] = args[0]
    scanner.config['is_configured'] = True
    scanner.save_config()
    await message.answer(f"✅ <b>Đã cấu hình nhóm:</b> <code>{args[0]}</code>")

@dp.message(Command("config"))
async def cmd_config(message: Message):
    config_text = f"""
⚙️ <b>CẤU HÌNH:</b>
API_ID: <code>{scanner.config.get('api_id', '❌ Chưa có')}</code>
API_HASH: <code>{scanner.config.get('api_hash', '❌ Chưa có')[:10]}...</code>
Phone: <code>{scanner.config.get('phone', '❌ Chưa có')}</code>
Nhóm: <code>{scanner.config.get('target_group', '❌ Chưa có')}</code>
"""
    await message.answer(config_text)

@dp.message(Command("connect"))
async def cmd_connect(message: Message):
    await message.answer("🔄 <b>Đang kết nối...</b>")
    success, msg = await scanner.connect_client()
    await message.answer(msg)

@dp.message(Command("login"))
async def cmd_login(message: Message):
    await message.answer("🔄 <b>Đang đăng nhập...</b>")
    success, msg = await scanner.login()
    await message.answer(msg)

@dp.message(Command("verify"))
async def cmd_verify(message: Message):
    args = message.text.split()[1:]
    if not args:
        await message.answer("❌ <b>Sai cú pháp!</b>\nDùng: <code>/verify &lt;mã&gt;</code>")
        return
    
    await message.answer("🔄 <b>Đang xác minh...</b>")
    success, msg = await scanner.verify(args[0])
    await message.answer(msg)

@dp.message(Command("2fa"))
async def cmd_2fa(message: Message):
    args = message.text.split()[1:]
    if not args:
        await message.answer("❌ <b>Sai cú pháp!</b>\nDùng: <code>/2fa &lt;mật_khẩu&gt;</code>")
        return
    
    await message.answer("🔄 <b>Đang xác minh 2FA...</b>")
    success, msg = await scanner.verify_2fa(args[0])
    await message.answer(msg)

@dp.message(Command("scan"))
async def cmd_scan(message: Message):
    if scanner.is_running:
        await message.answer("⚠️ <b>Đang chạy tác vụ khác!</b>")
        return
    
    args = message.text.split()[1:]
    count = int(args[0]) if args else None
    
    msg = await message.answer("🔍 <b>Đang quét...</b>")
    
    async def task():
        success, result = await scanner.scan(count)
        await msg.edit_text(result)
    
    asyncio.create_task(task())

@dp.message(Command("add"))
async def cmd_add(message: Message):
    if scanner.is_running:
        await message.answer("⚠️ <b>Đang chạy tác vụ khác!</b>")
        return
    
    args = message.text.split()[1:]
    count = int(args[0]) if args else 50
    
    msg = await message.answer("📤 <b>Đang thêm user...</b>")
    
    async def task():
        success, result = await scanner.add_users(count)
        await msg.edit_text(result)
    
    asyncio.create_task(task())

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    found_users = scanner.load_found_users()
    
    stats = f"""
📊 <b>THỐNG KÊ:</b>
User đã tìm: <code>{len(found_users)}</code>
File: <code>{OUTPUT_JSON}</code>
"""
    
    if found_users:
        stats += "\n<b>📋 5 user gần nhất:</b>\n"
        for i, user in enumerate(found_users[-5:], 1):
            name = user.get('first_name', '') or f"@{user.get('username', '')}"
            stats += f"{i}. {name}\n"
    
    await message.answer(stats)

@dp.message(Command("list"))
async def cmd_list(message: Message):
    found_users = scanner.load_found_users()
    
    if not found_users:
        await message.answer("❌ <b>Chưa có user nào!</b>")
        return
    
    # Chia thành các tin nhắn nhỏ
    chunk_size = 15
    for i in range(0, len(found_users), chunk_size):
        chunk = found_users[i:i+chunk_size]
        text = f"📋 <b>User {i+1}-{i+len(chunk)}:</b>\n\n"
        
        for user in chunk:
            text += f"• @{user.get('username', '')}\n"
        
        await message.answer(text)
        await asyncio.sleep(0.3)

@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    msg = await scanner.stop()
    await message.answer(msg)

@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = """
ℹ️ <b>HƯỚNG DẪN:</b>

1. <b>Cấu hình API</b> từ my.telegram.org:
   <code>/setapi &lt;api_id&gt; &lt;api_hash&gt;</code>

2. <b>Cấu hình số điện thoại:</b>
   <code>/setphone &lt;số_điện_thoại&gt;</code>

3. <b>Cấu hình nhóm:</b>
   <code>/setgroup @username_group</code>

4. <b>Đăng nhập:</b>
   <code>/connect</code> → <code>/login</code> → <code>/verify &lt;mã&gt;</code>

5. <b>Thêm username vào file usernames.txt</b>

6. <b>Quét:</b>
   <code>/scan [số_lượng]</code>

7. <b>Thêm user:</b>
   <code>/add [số_lượng]</code>
"""
    await message.answer(help_text)

@dp.message()
async def handle_unknown(message: Message):
    await message.answer("❌ <b>Lệnh không hợp lệ!</b>\nDùng <code>/help</code> để xem các lệnh.")

async def main():
    """Hàm chính"""
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN chưa được cấu hình!")
        print("ℹ️ Vui lòng đặt biến môi trường BOT_TOKEN trên Render")
        return
    
    # Kiểm tra file usernames.txt
    if not os.path.exists(INPUT_TXT):
        scanner.create_sample_file()
    
    print("🤖 Bot đang khởi động...")
    print(f"📁 File username: {INPUT_TXT}")
    print("=" * 80)
    
    # Chạy bot
    print("✅ Bot đã khởi động!")
    print("📲 Tìm bot trên Telegram và dùng /start để bắt đầu")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Bot đã dừng")
    except Exception as e:
        print(f"\n❌ Lỗi: {str(e)}")
        import traceback
        traceback.print_exc()
