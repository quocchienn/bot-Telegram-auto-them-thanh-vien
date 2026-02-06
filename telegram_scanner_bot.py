import asyncio
import random
import time
import json
import os
import logging
import sqlite3
from datetime import datetime
from telethon import TelegramClient, errors
from telethon.tl.functions.channels import InviteToChannelRequest
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, WebhookInfo
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiohttp import web
import sys

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print("=" * 80)
print("🤖 TELEGRAM USERNAME SCANNER BOT - WEB SERVICE")
print("=" * 80)

# === CẤU HÌNH ===
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '')
PORT = int(os.environ.get('PORT', 10000))

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
        self.session_file = 'scanner_session.session'
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
    
    def fix_sqlite_locking(self):
        """Sửa lỗi SQLite locking"""
        try:
            # Kiểm tra và sửa session file nếu cần
            if os.path.exists(self.session_file):
                # Backup file cũ
                backup_file = f"{self.session_file}.backup"
                if os.path.exists(backup_file):
                    os.remove(backup_file)
                os.rename(self.session_file, backup_file)
                
                # Tạo file session mới nếu backup tồn tại
                if os.path.exists(backup_file):
                    # Copy backup trở lại
                    import shutil
                    shutil.copy2(backup_file, self.session_file)
                    logger.info("✅ Đã sửa session file")
                
        except Exception as e:
            logger.error(f"❌ Lỗi sửa session file: {e}")
    
    async def connect_client(self, max_retries=3):
        """Kết nối Telethon client với retry"""
        for attempt in range(max_retries):
            try:
                if not self.config['api_id'] or not self.config['api_hash']:
                    return False, "❌ Chưa cấu hình API_ID và API_HASH!"
                
                # Sửa lỗi SQLite locking trước khi kết nối
                if attempt > 0:
                    self.fix_sqlite_locking()
                    await asyncio.sleep(1)  # Chờ một chút
                
                self.client = TelegramClient(
                    self.session_file,
                    int(self.config['api_id']),
                    self.config['api_hash']
                )
                
                # Thiết lập connection parameters để tránh lỗi
                self.client.flood_sleep_threshold = 0
                
                await self.client.connect()
                
                if not await self.client.is_user_authorized():
                    if not self.config['phone']:
                        return False, "❌ Chưa cấu hình số điện thoại!"
                    return False, "🔐 Chưa đăng nhập. Dùng /login"
                
                logger.info(f"✅ Kết nối thành công (attempt {attempt + 1})")
                return True, "✅ Đã kết nối và đăng nhập!"
                
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"⚠️ Database bị locked, thử lại... ({attempt + 1}/{max_retries})")
                    self.fix_sqlite_locking()
                    await asyncio.sleep(2)
                    continue
                else:
                    return False, f"❌ Lỗi database: {str(e)}"
                    
            except Exception as e:
                error_msg = str(e)
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ Lỗi kết nối, thử lại... ({attempt + 1}/{max_retries}): {error_msg[:100]}")
                    await asyncio.sleep(2)
                else:
                    return False, f"❌ Lỗi kết nối: {error_msg[:200]}"
        
        return False, "❌ Không thể kết nối sau nhiều lần thử"
    
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
        """Quét username với error handling"""
        try:
            if not self.client or not await self.client.is_user_authorized():
                success, msg = await self.connect_client()
                if not success:
                    return False, msg
            
            usernames = self.load_usernames()
            if not usernames:
                return False, f"❌ Không có username trong {INPUT_TXT}"
            
            if count and count < len(usernames):
                usernames = random.sample(usernames, count)
            
            self.is_running = True
            found_users = []
            scanned = 0
            errors = 0
            
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
                        logger.debug(f"✅ Tìm thấy: @{username}")
                
                except (ValueError, errors.UsernameNotOccupiedError):
                    pass
                except errors.FloodWaitError as e:
                    logger.warning(f"⚠️ Flood wait: {e.seconds}s")
                    await asyncio.sleep(e.seconds)
                    continue
                except Exception as e:
                    errors += 1
                    if errors > 10:  # Nếu quá nhiều lỗi, dừng lại
                        logger.error(f"Quá nhiều lỗi, dừng quét: {e}")
                        break
                
                scanned += 1
                
                # Delay ngẫu nhiên
                if scanned % BATCH_SIZE == 0:
                    wait_time = random.uniform(MIN_DELAY, MAX_DELAY)
                    await asyncio.sleep(wait_time)
            
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
            if errors > 0:
                report += f"⚠️ Lỗi: {errors}\n"
            
            return True, report
            
        except Exception as e:
            self.is_running = False
            logger.error(f"Lỗi khi quét: {e}")
            return False, f"❌ Lỗi khi quét: {str(e)[:200]}"
    
    async def add_users(self, count=50):
        """Thêm user vào nhóm"""
        try:
            if not self.client or not await self.client.is_user_authorized():
                success, msg = await self.connect_client()
                if not success:
                    return False, msg
            
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
            
            for i, user_info in enumerate(users_to_add, 1):
                if not self.is_running:
                    break
                
                try:
                    user = await self.client.get_entity(f"@{user_info['username']}")
                    
                    if getattr(user, 'bot', False):
                        failed += 1
                        logger.debug(f"🤖 Bỏ qua bot: @{user_info['username']}")
                        continue
                    
                    await self.client(InviteToChannelRequest(group, [user]))
                    added += 1
                    
                    # Ghi vào file
                    with open(ADDED_TXT, 'a', encoding='utf-8') as f:
                        f.write(f"{datetime.now().isoformat()}|@{user_info['username']}|{user.id}\n")
                    
                    logger.info(f"✅ Đã thêm: @{user_info['username']} ({i}/{len(users_to_add)})")
                
                except (errors.UserPrivacyRestrictedError, errors.UserAlreadyParticipantError) as e:
                    failed += 1
                    logger.debug(f"❌ Không thêm được: @{user_info['username']} - {type(e).__name__}")
                except errors.FloodWaitError as e:
                    logger.warning(f"⏳ Flood wait {e.seconds}s, dừng thêm")
                    break
                except Exception as e:
                    failed += 1
                    logger.debug(f"⚠️ Lỗi với @{user_info['username']}: {type(e).__name__}")
                
                # Delay
                wait_time = random.uniform(MIN_DELAY * 2, MAX_DELAY * 2)
                await asyncio.sleep(wait_time)
            
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
            logger.error(f"Lỗi khi thêm: {e}")
            return False, f"❌ Lỗi khi thêm: {str(e)[:200]}"
    
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
            logger.info(f"💾 Đã lưu {len(found_users)} user vào {OUTPUT_JSON}")
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
        if self.client and self.client.is_connected():
            await self.client.disconnect()
        return "⏹️ Đã dừng"
    
    async def cleanup(self):
        """Dọn dẹp khi dừng"""
        if self.client:
            try:
                await self.client.disconnect()
            except:
                pass

# Khởi tạo scanner
scanner = TelegramScanner()

# Khởi tạo aiogram bot
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
/status - Trạng thái bot
/reset - Reset session
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

@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    """Reset session file"""
    try:
        if os.path.exists(scanner.session_file):
            os.remove(scanner.session_file)
            await message.answer("✅ <b>Đã xóa session file!</b>\nDùng /connect để tạo session mới.")
        else:
            await message.answer("ℹ️ <b>Không có session file để xóa.</b>")
    except Exception as e:
        await message.answer(f"❌ <b>Lỗi khi reset:</b> {str(e)}")

@dp.message(Command("status"))
async def cmd_status(message: Message):
    # Kiểm tra kết nối
    is_connected = scanner.client and scanner.client.is_connected() if scanner.client else False
    
    status_text = f"""
📊 <b>TRẠNG THÁI BOT:</b>
🏃 Đang chạy: <code>{'✅' if scanner.is_running else '❌'}</code>
🔌 Kết nối: <code>{'✅' if is_connected else '❌'}</code>
⚙️ Đã cấu hình: <code>{'✅' if scanner.config['is_configured'] else '❌'}</code>
📁 File username: <code>{len(scanner.load_usernames())} user</code>
💾 User đã tìm: <code>{len(scanner.load_found_users())} user</code>
"""
    await message.answer(status_text)

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

<b>🛠️ Lệnh khác:</b>
<code>/status</code> - Xem trạng thái
<code>/reset</code> - Reset session (nếu bị lỗi)
<code>/stop</code> - Dừng tác vụ
"""
    await message.answer(help_text)

@dp.message()
async def handle_unknown(message: Message):
    await message.answer("❌ <b>Lệnh không hợp lệ!</b>\nDùng <code>/help</code> để xem các lệnh.")

async def create_app():
    """Tạo ứng dụng web"""
    app = web.Application()
    
    # Health check endpoint
    async def health_check(request):
        return web.json_response({
            'status': 'running',
            'service': 'Telegram Scanner Bot',
            'timestamp': datetime.now().isoformat()
        })
    
    # Lệnh reset qua web (cho admin)
    async def reset_session(request):
        try:
            if os.path.exists(scanner.session_file):
                os.remove(scanner.session_file)
                return web.json_response({'status': 'success', 'message': 'Session reset'})
            else:
                return web.json_response({'status': 'no_session'})
        except Exception as e:
            return web.json_response({'status': 'error', 'message': str(e)}, status=500)
    
    # Thêm routes
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    app.router.add_post('/reset', reset_session)
    
    return app

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
    print(f"🌐 Port: {PORT}")
    print(f"💾 Session file: {scanner.session_file}")
    print("=" * 80)
    
    # Tạo ứng dụng web
    app = await create_app()
    
    # Tạo web runner
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Bind vào port
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    print(f"✅ Web server đang chạy trên port {PORT}")
    print("📲 Tìm bot trên Telegram và dùng /start để bắt đầu")
    
    # Chạy bot polling
    print("🤖 Đang khởi động bot polling...")
    
    try:
        # Chạy bot polling
        await dp.start_polling(bot, handle_signals=False)
    except KeyboardInterrupt:
        print("\n\n👋 Bot đang dừng...")
    except Exception as e:
        print(f"\n❌ Lỗi khi chạy bot: {e}")
    finally:
        # Dọn dẹp
        print("🧹 Đang dọn dẹp...")
        await scanner.cleanup()
        await runner.cleanup()
        await bot.session.close()
        print("👋 Bot đã dừng hoàn toàn")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Bot đã dừng")
    except Exception as e:
        print(f"\n❌ Lỗi: {str(e)}")
        import traceback
        traceback.print_exc()
