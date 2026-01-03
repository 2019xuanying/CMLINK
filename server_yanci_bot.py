import logging
import requests
import re
import random
import time
import json
import os
import sys
import traceback
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# ================= 环境配置 =================
load_dotenv()

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
ADMIN_ID = os.getenv("TG_ADMIN_ID")

if not BOT_TOKEN:
    print("❌ 错误：未找到 TG_BOT_TOKEN。请检查环境变量或 .env 文件。")
    sys.exit(1)

try:
    if ADMIN_ID:
        ADMIN_ID = int(ADMIN_ID)
    else:
        print("⚠️ 警告：未设置 TG_ADMIN_ID，管理功能将无法使用。")
except ValueError:
    print("❌ 错误：TG_ADMIN_ID 必须是数字。")
    sys.exit(1)

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= 数据存储管理类 (保持不变) =================
class UserManager:
    FILE_PATH = 'user_data.json'

    def __init__(self):
        self.data = self._load()

    def _load(self):
        if not os.path.exists(self.FILE_PATH):
            return {"users": {}}
        try:
            with open(self.FILE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载数据失败: {e}")
            return {"users": {}}

    def _save(self):
        try:
            with open(self.FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存数据失败: {e}")

    def authorize_user(self, user_id, username=None):
        uid = str(user_id)
        if uid not in self.data["users"]:
            self.data["users"][uid] = {"authorized": True, "count": 0, "name": username or "Unknown"}
        else:
            self.data["users"][uid]["authorized"] = True
            if username: self.data["users"][uid]["name"] = username
        self._save()
        return True

    def revoke_user(self, user_id):
        uid = str(user_id)
        if uid in self.data["users"]:
            self.data["users"][uid]["authorized"] = False
            self._save()
            return True
        return False

    def is_authorized(self, user_id):
        if ADMIN_ID and user_id == ADMIN_ID:
            return True
        uid = str(user_id)
        user = self.data["users"].get(uid)
        return user and user.get("authorized", False)

    def increment_usage(self, user_id, username=None):
        uid = str(user_id)
        if uid not in self.data["users"]:
            self.data["users"][uid] = {"authorized": False, "count": 1, "name": username or "Unknown"}
        else:
            self.data["users"][uid]["count"] += 1
            if username: self.data["users"][uid]["name"] = username
        self._save()

    def get_all_stats(self):
        return self.data["users"]

user_manager = UserManager()

# ================= 常量定义 =================
FIXED_PASSWORD = "Pass1234"
PRODUCT_ID = '974'

URLS = {
    "entry": "https://www.yanci.com.tw/register",
    "register": "https://www.yanci.com.tw/storeregd",
    "send_verify": "https://www.yanci.com.tw/sendvcurl", 
    "login": "https://www.yanci.com.tw/login",
    "update": "https://www.yanci.com.tw/updateopt",
    "order": "https://www.yanci.com.tw/gives"
}

HEADERS_BASE = {
    'Host': 'www.yanci.com.tw',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://www.yanci.com.tw',
}

# ================= 逻辑工具类 (保持不变) =================
class YanciBotLogic:
    @staticmethod
    def generate_taiwan_phone():
        return f"09{random.randint(10000000, 99999999)}"

    @staticmethod
    def generate_random_name():
        if random.random() < 0.3:
            first_names_en = ["James", "John", "Robert", "Michael", "David", "William", "Richard", "Joseph", "Thomas", "Charles", "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan", "Jessica", "Sarah", "Karen"]
            last_names_en = ["Smith", "Johnson", "Williams", "Jones", "Brown", "Davis", "Miller", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris"]
            return f"{random.choice(first_names_en)} {random.choice(last_names_en)}"
        else:
            last_names_cn = ["陳", "林", "黃", "張", "李", "王", "吳", "劉", "蔡", "楊", "許", "鄭", "謝", "郭", "洪", "曾", "邱", "廖", "賴", "徐"]
            first_names_cn = ["家豪", "志明", "俊傑", "建宏", "俊宏", "志偉", "志強", "文雄", "淑芬", "淑惠", "美玲", "雅婷", "美惠", "麗华", "秀英", "宗翰", "怡君", "雅雯", "欣怡", "心怡"]
            return f"{random.choice(last_names_cn)}{random.choice(first_names_cn)}"

    @staticmethod
    def generate_random_address():
        locations = [
            {"city": "臺北市", "area": "信義區", "zip": "110"},
            {"city": "臺北市", "area": "大安區", "zip": "106"},
            {"city": "新北市", "area": "板橋區", "zip": "220"},
            {"city": "桃園市", "area": "桃園區", "zip": "330"},
            {"city": "臺中市", "area": "西屯區", "zip": "407"},
            {"city": "臺南市", "area": "東區", "zip": "701"},
            {"city": "高雄市", "area": "左營區", "zip": "813"},
        ]
        roads = ["中正路", "中山路", "中華路", "建國路", "復興路", "三民路", "民生路", "信義路"]
        loc = random.choice(locations)
        road = random.choice(roads)
        section = f"{random.randint(1, 5)}段" if random.random() > 0.5 else ""
        no = f"{random.randint(1, 500)}號"
        floor = f"{random.randint(2, 20)}樓" if random.random() > 0.3 else ""
        full_addr = f"{road}{section}{no}{floor}"
        return {"city": loc["city"], "area": loc["area"], "zip": loc["zip"], "addr": full_addr}

    @staticmethod
    def extract_id(text_or_url):
        match_url = re.search(r'[&?](\d{5})(?:$|&)', text_or_url)
        if match_url: return match_url.group(1)
        match_html = re.search(r'vc=Y(?:&amp;|&)(\d{5})', text_or_url)
        if match_html: return match_html.group(1)
        return None

    @staticmethod
    def extract_text_from_html(html_content):
        try:
            alert_match = re.search(r"alert\(['\"](.*?)['\"]\)", html_content)
            if alert_match: return f"弹窗提示: {alert_match.group(1)}"
            clean_text = re.sub('<[^<]+?>', '', html_content).strip()
            return clean_text[:100].replace('\n', ' ')
        except: return "无法解析页面内容"

    @staticmethod
    def get_initial_session():
        session = requests.Session()
        session.headers.update(HEADERS_BASE)
        try:
            resp = session.get(URLS['entry'] + "?lg=tw", timeout=15, allow_redirects=True)
            found_id = YanciBotLogic.extract_id(resp.url) or YanciBotLogic.extract_id(resp.text)
            if found_id:
                logger.info(f"成功获取 ID: {found_id}")
                return session, found_id, "成功"
            else:
                random_id = str(random.randint(20000, 30000))
                logger.warning(f"未找到 ID，使用随机 ID: {random_id}")
                return session, random_id, "随机生成"
        except Exception as e:
            return None, None, f"网络错误: {str(e)}"

    @staticmethod
    def register_loop(session, email, phone, start_id):
        current_id = start_id
        max_retries = 3
        for attempt in range(max_retries):
            logger.info(f"注册尝试 {attempt+1}/{max_retries} (ID: {current_id}) -> {email}")
            payload = {'userMode': 'normal', 'userACC': email, 'userPWD': FIXED_PASSWORD, 'userPhn': phone, 'userChk': 'true', 'userPage': ''}
            headers = HEADERS_BASE.copy()
            headers['Referer'] = f"{URLS['entry']}?lg=tw&vc=Y&{current_id}"
            try:
                resp = session.post(URLS['register'], headers=headers, data=payload, timeout=20)
                resp.encoding = 'utf-8'
                try:
                    res_json = resp.json()
                    if isinstance(res_json, list) and len(res_json) > 0:
                        code = res_json[0].get('code')
                        msg = res_json[0].get('msg', '')
                        if code == '400':
                            if "唯一" in msg or "重複" in msg or "重复" in msg: return True, current_id, "账号已存在(视为成功)"
                            return False, current_id, f"服务器拒绝: {msg}"
                except: pass

                if "<!DOCTYPE html>" in resp.text or "vc=Y" in resp.text:
                    new_id = YanciBotLogic.extract_id(resp.text) or YanciBotLogic.extract_id(resp.url)
                    if new_id and new_id != current_id:
                        logger.info(f"检测到 ID 变更 (旧: {current_id} -> 新: {new_id})，准备重试...")
                        current_id = new_id
                        time.sleep(1)
                        continue
                    else: return False, current_id, "注册被拒绝且无法获取新ID"

                if resp.status_code == 200: return True, current_id, "注册请求已发送"
                return False, current_id, f"HTTP状态异常: {resp.status_code}"
            except Exception as e: return False, current_id, f"请求异常: {str(e)}"
        return False, current_id, "超过最大重试次数"

    @staticmethod
    def send_verify_email(session, verify_id):
        url = f"{URLS['send_verify']}{verify_id}"
        headers = HEADERS_BASE.copy()
        headers['Referer'] = f"{URLS['entry']}?lg=tw&vc=Y&{verify_id}"
        headers['Accept'] = 'application/json, text/plain, */*'
        try:
            time.sleep(1)
            resp = session.post(url, headers=headers, data='Y', timeout=20)
            if resp.status_code == 200 and "400" not in resp.text: return True, "发送成功"
            return False, f"发送失败 (Code: {resp.status_code})"
        except Exception as e: return False, str(e)

    @staticmethod
    def login(session, email):
        headers = HEADERS_BASE.copy()
        headers['Referer'] = URLS['login']
        headers['X-Requested-With'] = 'XMLHttpRequest'
        headers['Accept'] = 'application/json, text/javascript, */*; q=0.01'
        payload = {'userMode': 'normal', 'userACC': email, 'userPWD': FIXED_PASSWORD, 'userRem': 'true', 'userPage': ''}
        try:
            resp = session.post(URLS['login'], headers=headers, data=payload, timeout=20)
            if resp.status_code == 200 and "alert" not in resp.text: return True, "登录成功"
            return False, "登录失败(可能是密码错误或未验证)"
        except Exception as e: return False, str(e)

    @staticmethod
    def update_profile(session, phone):
        name = YanciBotLogic.generate_random_name()
        addr_data = YanciBotLogic.generate_random_address()
        sex = '男性' if random.random() > 0.5 else '女性'
        headers = HEADERS_BASE.copy()
        headers['Referer'] = 'https://www.yanci.com.tw/member_edit'
        headers['X-Requested-With'] = 'XMLHttpRequest'
        payload = {'userName': name, 'userSex': sex, 'userPhn': phone, 'userTel': phone, 'userZip': addr_data['zip'], 'userCity': addr_data['city'], 'userArea': addr_data['area'], 'userAddr': addr_data['addr']}
        logger.info(f"正在更新资料: {name} | {addr_data['city']}{addr_data['area']}")
        try:
            resp = session.post(URLS['update'], headers=headers, data=payload, timeout=20)
            return resp.status_code == 200, name
        except: return False, name

    @staticmethod
    def place_order(session):
        time.sleep(1.0)
        headers = HEADERS_BASE.copy()
        headers['Referer'] = 'https://www.yanci.com.tw/product_give'
        headers['X-Requested-With'] = 'XMLHttpRequest'
        if 'Upgrade-Insecure-Requests' in headers: del headers['Upgrade-Insecure-Requests']
        payload = {'given': PRODUCT_ID, 'giveq': '1'}
        try:
            resp = session.post(URLS['order'], headers=headers, data=payload, timeout=20)
            resp.encoding = 'utf-8'
            logger.info(f"下单接口返回: Status={resp.status_code} | Body Len={len(resp.text)}")
            try:
                res_json = resp.json()
                if isinstance(res_json, list) and len(res_json) > 0:
                    data = res_json[0]
                    code = str(data.get('code', ''))
                    msg = data.get('msg', '无返回信息')
                    if code == '200': return True, f"下单成功: {msg}"
                    elif code == '400': return False, f"服务器拒绝: {msg}"
            except: pass 
            if resp.status_code == 200:
                if "<!DOCTYPE html>" in resp.text or "<html" in resp.text:
                    title_match = re.search(r'<title>(.*?)</title>', resp.text, re.IGNORECASE)
                    page_title = title_match.group(1) if title_match else "未知页面"
                    page_text = YanciBotLogic.extract_text_from_html(resp.text)
                    if "登入" in page_title or "Login" in page_title or "登入" in page_text: return False, "下单失败: 会话失效(需重登录)"
                    return False, f"服务器返回页面: {page_title} (可能是: {page_text})"
                return True, "请求发送成功 (未返回错误)"
            return False, f"HTTP {resp.status_code}"
        except Exception as e: return False, str(e)

# ================= Telegram Bot Handlers =================

# --- 状态常量 ---
STATE_NONE = 0
STATE_WAIT_EMAIL = 1
STATE_WAIT_ADD_ID = 2
STATE_WAIT_DEL_ID = 3

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data['state'] = STATE_NONE # 重置状态
    
    welcome_text = (
        f"👋 **Yanci 自动助手 **\n\n"
        f"你好，{user.first_name}！\n请通过下方按钮操作："
    )
    
    keyboard = [
        [InlineKeyboardButton("🚀 开始新任务", callback_data="btn_new_task")],
        [InlineKeyboardButton("👤 我的信息", callback_data="btn_my_info")]
    ]
    
    # 管理员入口
    if ADMIN_ID and user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👮 管理面板", callback_data="btn_admin_menu")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 兼容新消息和回调更新
    if update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    await query.answer()
    
    data = query.data
    
    # === 主菜单逻辑 ===
    if data == "main_menu":
        await start(update, context)
        return

    # === 任务流程 ===
    if data == "btn_new_task":
        if not user_manager.is_authorized(user.id):
            await query.edit_message_text(
                f"🚫 **访问被拒绝**\n您没有权限。请联系管理员 ID: `{ADMIN_ID}`\n您的 ID: `{user.id}`",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]]),
                parse_mode='Markdown'
            )
            return
        
        context.user_data['state'] = STATE_WAIT_EMAIL
        await query.edit_message_text(
            "📧 **请输入注册邮箱：**\n\n请直接回复邮箱地址 (例如: `abc@gmail.com`)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="main_menu")]])
        , parse_mode='Markdown')
        return

    if data == "btn_my_info":
        status = "✅ 已授权" if user_manager.is_authorized(user.id) else "🚫 未授权"
        await query.edit_message_text(
            f"👤 **用户信息**\n\n姓名: {user.first_name}\nID: `{user.id}`\n状态: {status}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]]),
            parse_mode='Markdown'
        )
        return

    if data == "verify_done":
        # 用户点击了“我已验证”，继续执行后续逻辑
        await execute_post_verification(query, context)
        return

    # === 管理员面板 ===
    if data == "btn_admin_menu":
        if user.id != ADMIN_ID: return
        context.user_data['state'] = STATE_NONE
        keyboard = [
            [InlineKeyboardButton("✅ 授权用户", callback_data="admin_add")],
            [InlineKeyboardButton("🚫 移除用户", callback_data="admin_del")],
            [InlineKeyboardButton("📊 查看统计", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
        ]
        await query.edit_message_text("👮 **管理面板**\n请选择操作：", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    if data == "admin_stats":
        stats = user_manager.get_all_stats()
        msg = "📊 **用户统计**\n\n"
        if not stats: msg += "暂无数据"
        for uid, info in stats.items():
            icon = "✅" if info.get('authorized') else "🚫"
            msg += f"{icon} `{uid}` ({info.get('name')}): {info.get('count')}次\n"
        
        keyboard = [[InlineKeyboardButton("🔙 返回管理", callback_data="btn_admin_menu")]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    if data == "admin_add":
        context.user_data['state'] = STATE_WAIT_ADD_ID
        await query.edit_message_text(
            "➕ **请输入要授权的 Telegram ID：**\n\n请直接回复数字 ID。",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="btn_admin_menu")]])
        , parse_mode='Markdown')
        return

    if data == "admin_del":
        context.user_data['state'] = STATE_WAIT_DEL_ID
        await query.edit_message_text(
            "➖ **请输入要移除的 Telegram ID：**\n\n请直接回复数字 ID。",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="btn_admin_menu")]])
        , parse_mode='Markdown')
        return

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理所有文本输入，根据状态分发"""
    state = context.user_data.get('state', STATE_NONE)
    text = update.message.text.strip()
    user = update.effective_user

    if state == STATE_NONE:
        # 如果没有状态，不处理或仅提示
        return

    # === 处理邮箱输入 (任务开始) ===
    if state == STATE_WAIT_EMAIL:
        email = text
        context.user_data['state'] = STATE_NONE # 清除状态
        if "@" not in email:
            await update.message.reply_text("❌ 邮箱格式看似不正确，请重新点击按钮输入。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]]))
            return
        
        # 开始执行任务逻辑
        await start_task_logic(update, context, email)
        return

    # === 处理添加用户输入 ===
    if state == STATE_WAIT_ADD_ID:
        if user.id != ADMIN_ID: return
        context.user_data['state'] = STATE_NONE
        try:
            target_id = int(text)
            user_manager.authorize_user(target_id)
            await update.message.reply_text(f"✅ 用户 `{target_id}` 已授权。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回管理", callback_data="btn_admin_menu")]]), parse_mode='Markdown')
        except ValueError:
            await update.message.reply_text("❌ ID 必须是数字。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回管理", callback_data="btn_admin_menu")]]))
        return

    # === 处理移除用户输入 ===
    if state == STATE_WAIT_DEL_ID:
        if user.id != ADMIN_ID: return
        context.user_data['state'] = STATE_NONE
        try:
            target_id = int(text)
            user_manager.revoke_user(target_id)
            await update.message.reply_text(f"🚫 用户 `{target_id}` 权限已移除。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回管理", callback_data="btn_admin_menu")]]), parse_mode='Markdown')
        except ValueError:
            await update.message.reply_text("❌ ID 必须是数字。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回管理", callback_data="btn_admin_menu")]]))
        return

# --- 业务逻辑封装 ---

async def start_task_logic(update: Update, context: ContextTypes.DEFAULT_TYPE, email: str):
    """执行任务的第一阶段：初始化、注册、发信"""
    user = update.effective_user
    phone = YanciBotLogic.generate_taiwan_phone()
    user_manager.increment_usage(user.id, user.first_name)

    msg = await update.message.reply_text(f"🚀 **任务启动**\n邮箱: `{email}`\n⏳ 正在初始化...", parse_mode='Markdown')

    try:
        # 1. 获取 Session
        session, verify_id, init_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.get_initial_session)
        if not session or not verify_id:
            await msg.edit_text(f"❌ 初始化失败: {init_msg}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]]))
            return

        context.user_data['session'] = session
        context.user_data['email'] = email
        context.user_data['phone'] = phone
        
        await msg.edit_text(f"✅ 获取 ID: {verify_id}\n⏳ 正在注册...")

        # 2. 注册
        reg_success, final_id, reg_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.register_loop, session, email, phone, verify_id
        )
        if not reg_success:
            await msg.edit_text(f"❌ 注册失败: {reg_msg}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]]))
            return

        context.user_data['verify_id'] = final_id
        await msg.edit_text(f"✅ 注册通过\n⏳ 正在申请验证信...")

        # 3. 发送验证信
        send_success, send_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.send_verify_email, session, final_id
        )
        if not send_success:
            await msg.edit_text(f"❌ 发信失败: {send_msg}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]]))
            return

        # 4. 等待用户确认
        keyboard = [
            [InlineKeyboardButton("✅ 我已点击邮件链接验证", callback_data="verify_done")],
            [InlineKeyboardButton("❌ 取消任务", callback_data="main_menu")]
        ]
        await msg.edit_text(
            f"📩 **验证信已发送！**\n\n请前往邮箱 `{email}` 点击验证链接。\n完成后点击下方按钮：",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(traceback.format_exc())
        await msg.edit_text(f"💥 发生错误: {str(e)}")

async def execute_post_verification(query, context):
    """执行任务的第二阶段：登录、完善资料、下单"""
    session = context.user_data.get('session')
    email = context.user_data.get('email')
    phone = context.user_data.get('phone')

    if not session:
        await query.edit_message_text("❌ 会话已过期，请重新开始任务。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]]))
        return

    await query.edit_message_text("⏳ 正在登录并执行后续操作...")

    try:
        # 1. 登录
        login_success, login_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.login, session, email)
        if not login_success:
            await query.edit_message_text(f"❌ {login_msg}\n(请确保确实已在邮件中点击了链接)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 我确实验证了，重试", callback_data="verify_done")]]))
            return

        # 2. 完善资料
        update_success, name = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.update_profile, session, phone)
        if not update_success:
            await query.edit_message_text("❌ 资料保存失败，无法下单。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]]))
            return

        await query.edit_message_text(f"✅ 资料已保存 (姓名: {name})\n⏳ 正在下单...")

        # 3. 下单
        order_success, order_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.place_order, session)
        
        # 自动重试逻辑 (Session闪断)
        if not order_success and ("登入" in order_msg or "失效" in order_msg):
             await query.edit_message_text(f"⚠️ 会话微小异常，正在自动重连...")
             relogin_success, _ = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.login, session, email)
             if relogin_success:
                 order_success, order_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.place_order, session)

        if order_success:
            await query.edit_message_text(
                f"🎉 **任务圆满完成！**\n\n📧 邮箱: `{email}`\n👤 姓名: {name}\n✅ 结果: {order_msg}\n\n请登录网页查看。",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]]),
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"❌ 下单失败: {order_msg}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]])
            )

    except Exception as e:
        logger.error(traceback.format_exc())
        await query.edit_message_text(f"💥 流程异常: {str(e)}")


if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # 核心入口：只有 start 指令和 文本消息处理
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # 捕获所有文本消息，用于状态机输入 (邮箱、ID等)
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_input))
    
    print("🤖 Yanci Button Bot 已启动...")
    application.run_polling()
