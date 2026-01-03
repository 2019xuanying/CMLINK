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

# ================= 数据存储管理类 =================
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

# ================= 临时邮箱工具类 (1secmail) =================
class OneSecMail:
    BASE_URL = "https://www.1secmail.com/api/v1/"

    @staticmethod
    def generate_email():
        """生成一个随机邮箱"""
        try:
            # 获取可用域名列表
            # resp = requests.get(f"{OneSecMail.BASE_URL}?action=getDomainList")
            # domains = resp.json()
            # domain = random.choice(domains)
            # 指定常用域名，有时候 random 的会被墙
            domain = "1secmail.com" 
            
            name = f"user{random.randint(100000, 999999)}"
            email = f"{name}@{domain}"
            return email, name, domain
        except Exception as e:
            logger.error(f"邮箱生成失败: {e}")
            return None, None, None

    @staticmethod
    def check_inbox(login, domain):
        """检查收件箱，返回邮件列表"""
        try:
            url = f"{OneSecMail.BASE_URL}?action=getMessages&login={login}&domain={domain}"
            resp = requests.get(url, timeout=10)
            return resp.json()
        except:
            return []

    @staticmethod
    def get_message_content(login, domain, msg_id):
        """获取邮件具体内容"""
        try:
            url = f"{OneSecMail.BASE_URL}?action=readMessage&login={login}&domain={domain}&id={msg_id}"
            resp = requests.get(url, timeout=10)
            return resp.json()
        except:
            return None

# ================= 业务逻辑工具类 =================
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
    def extract_verification_link(html_content):
        """从邮件HTML中提取验证链接"""
        # 寻找包含 checkreg 或类似结构的链接
        match = re.search(r'(https?://www\.yanci\.com\.tw/checkreg[^\s"\'<>]+)', html_content)
        if match:
            return match.group(1)
        return None
        
    @staticmethod
    def extract_esim_info(html_content):
        """从邮件中提取激活码或二维码图片"""
        info = []
        # 尝试提取 LPA 码
        lpa_match = re.search(r'(LPA:1\$[a-zA-Z0-9\.\-]+\$[a-zA-Z0-9]+)', html_content)
        if lpa_match:
            info.append(f"📡 **LPA 激活码**: `{lpa_match.group(1)}`")
        
        # 尝试提取纯数字/字母激活码 (根据扬奇的格式调整)
        code_match = re.search(r'激活碼[：:]\s*([A-Za-z0-9]+)', html_content)
        if code_match:
            info.append(f"🔑 **激活码**: `{code_match.group(1)}`")
            
        # 尝试提取二维码图片链接
        # 注意：如果是附件形式，1secmail 需要额外处理下载，这里先只提取 src
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+\.png|[^"\']+\.jpg)[^"\']*["\']', html_content)
        if img_match:
            # 过滤掉 icon 等无关图片，这里假设二维码比较大或者是特定的
            if "logo" not in img_match.group(1):
                info.append(f"🖼 **可能的二维码链接**: {img_match.group(1)}")
                
        return "\n".join(info)

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
    def visit_verification_link(session, link):
        """模拟点击验证链接"""
        try:
            headers = HEADERS_BASE.copy()
            headers['Referer'] = 'https://www.1secmail.com/' # 模拟从邮箱跳转
            resp = session.get(link, headers=headers, timeout=20)
            if resp.status_code == 200:
                return True, "验证链接访问成功"
            return False, f"验证链接访问失败: {resp.status_code}"
        except Exception as e:
            return False, str(e)

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
STATE_WAIT_ADD_ID = 2
STATE_WAIT_DEL_ID = 3

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data['state'] = STATE_NONE 
    
    welcome_text = (
        f"👋 **Yanci 全自动助手 (V14.0 托管版)**\n\n"
        f"你好，{user.first_name}！\n此版本已集成临时邮箱，无需手动输入。\n\n"
        f"🚀 **一键功能**：自动注册 -> 自动验证 -> 自动下单 -> 自动收货"
    )
    
    keyboard = [
        [InlineKeyboardButton("🚀 一键全自动抢单", callback_data="btn_auto_task")],
        [InlineKeyboardButton("👤 我的信息", callback_data="btn_my_info")]
    ]
    
    if ADMIN_ID and user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👮 管理面板", callback_data="btn_admin_menu")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    await query.answer()
    
    data = query.data
    
    if data == "main_menu":
        await start(update, context)
        return

    # === 全自动任务入口 ===
    if data == "btn_auto_task":
        if not user_manager.is_authorized(user.id):
            await query.edit_message_text("🚫 无权访问。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]]))
            return
        
        # 启动后台异步任务，不阻塞 Bot 响应
        asyncio.create_task(run_auto_task(query, context, user))
        return

    if data == "btn_my_info":
        status = "✅ 已授权" if user_manager.is_authorized(user.id) else "🚫 未授权"
        await query.edit_message_text(f"👤 **用户信息**\n\n姓名: {user.first_name}\nID: `{user.id}`\n状态: {status}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]]), parse_mode='Markdown')
        return

    if data == "btn_admin_menu":
        if user.id != ADMIN_ID: return
        context.user_data['state'] = STATE_NONE
        keyboard = [
            [InlineKeyboardButton("✅ 授权用户", callback_data="admin_add")],
            [InlineKeyboardButton("🚫 移除用户", callback_data="admin_del")],
            [InlineKeyboardButton("📊 查看统计", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
        ]
        await query.edit_message_text("👮 **管理面板**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
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
        await query.edit_message_text("➕ **回复要授权的 ID：**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="btn_admin_menu")]]) , parse_mode='Markdown')
        return

    if data == "admin_del":
        context.user_data['state'] = STATE_WAIT_DEL_ID
        await query.edit_message_text("➖ **回复要移除的 ID：**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="btn_admin_menu")]]) , parse_mode='Markdown')
        return

# === 全自动任务逻辑 ===

async def run_auto_task(query, context, user):
    """全自动任务核心逻辑"""
    
    # 1. 初始化 & 生成邮箱
    await query.edit_message_text("🏗 **正在初始化环境...**\n⏳ 正在申请临时邮箱...")
    
    email, mail_login, mail_domain = OneSecMail.generate_email()
    if not email:
        await query.edit_message_text("❌ 临时邮箱服务暂时不可用，请稍后再试。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]]))
        return
        
    phone = YanciBotLogic.generate_taiwan_phone()
    user_manager.increment_usage(user.id, user.first_name)
    
    msg_status = await query.edit_message_text(
        f"🚀 **任务启动 (托管模式)**\n\n"
        f"📧 临时邮箱: `{email}`\n"
        f"📱 虚拟手机: `{phone}`\n"
        f"⏳ **正在连接服务器...**", 
        parse_mode='Markdown'
    )

    try:
        # 2. 获取 Session
        session, verify_id, init_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.get_initial_session)
        if not session:
            await msg_status.edit_text(f"❌ 初始化失败: {init_msg}")
            return

        # 3. 注册
        await msg_status.edit_text(f"✅ 获取ID: {verify_id}\n⏳ **正在提交注册请求...**")
        reg_success, final_id, reg_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.register_loop, session, email, phone, verify_id
        )
        if not reg_success:
            await msg_status.edit_text(f"❌ 注册被拒: {reg_msg}")
            return

        # 4. 发送验证邮件
        await msg_status.edit_text(f"✅ 注册请求已通过\n⏳ **正在触发验证邮件...**")
        send_success, send_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.send_verify_email, session, final_id
        )
        if not send_success:
            await msg_status.edit_text(f"❌ 发信失败: {send_msg}")
            return

        # 5. 循环监听邮件 (最多等待 120 秒)
        await msg_status.edit_text(f"📩 **验证信已发送！**\n⏳ 正在自动监听邮箱 (最多等2分钟)...")
        
        verification_link = None
        start_time = time.time()
        
        while time.time() - start_time < 120:
            # 检查邮件
            mails = await asyncio.get_running_loop().run_in_executor(None, OneSecMail.check_inbox, mail_login, mail_domain)
            
            if mails:
                for mail in mails:
                    # 判断标题是否相关
                    if "驗證" in mail.get('subject', '') or "Verify" in mail.get('subject', '') or "验证" in mail.get('subject', ''):
                        # 读取邮件详情
                        mail_detail = await asyncio.get_running_loop().run_in_executor(None, OneSecMail.get_message_content, mail_login, mail_domain, mail.get('id'))
                        if mail_detail:
                            # 提取链接
                            link = YanciBotLogic.extract_verification_link(mail_detail.get('body', ''))
                            if link:
                                verification_link = link
                                break
            
            if verification_link:
                break
            
            await asyncio.sleep(4) # 每4秒轮询一次

        if not verification_link:
            await msg_status.edit_text("❌ 等待超时，未收到验证邮件。任务终止。")
            return

        # 6. 点击验证链接
        await msg_status.edit_text(f"🔎 **捕获到验证链接！**\n⏳ 正在模拟点击验证...")
        visit_success, visit_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.visit_verification_link, session, verification_link
        )
        
        if not visit_success:
            await msg_status.edit_text(f"❌ 验证链接访问失败: {visit_msg}")
            return

        # 7. 登录 & 完善资料 & 下单
        await msg_status.edit_text(f"✅ 邮箱验证通过！\n⏳ **正在登录并自动下单...**")
        
        # 登录
        login_success, login_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.login, session, email)
        if not login_success:
            await msg_status.edit_text(f"❌ 登录失败: {login_msg}")
            return
            
        # 完善资料
        update_success, name = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.update_profile, session, phone)
        if not update_success:
            await msg_status.edit_text("❌ 资料保存失败。")
            return

        # 下单
        order_success, order_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.place_order, session)
        
        # 自动重试逻辑
        if not order_success and ("登入" in order_msg or "失效" in order_msg):
             await msg_status.edit_text("⚠️ 会话闪断，正在重连...")
             relogin_success, _ = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.login, session, email)
             if relogin_success:
                 order_success, order_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.place_order, session)

        if not order_success:
             await msg_status.edit_text(f"❌ 下单最终失败: {order_msg}")
             return

        # 8. 成功下单，等待发货邮件 (新功能)
        await msg_status.edit_text(
            f"🎉 **下单成功！**\n"
            f"👤 姓名: {name}\n"
            f"📧 邮箱: `{email}`\n"
            f"⏳ **正在等待发货邮件提取激活码...**\n(您可以现在离开，结果会稍后发送)"
        , parse_mode='Markdown')
        
        # 继续监听邮件 (最多等 5 分钟)
        esim_info = None
        wait_mail_start = time.time()
        
        while time.time() - wait_mail_start < 300: # 5分钟等待
            mails = await asyncio.get_running_loop().run_in_executor(None, OneSecMail.check_inbox, mail_login, mail_domain)
            if mails:
                for mail in mails:
                    # 排除掉之前的验证邮件，找新的订单邮件
                    subject = mail.get('subject', '')
                    # 关键词匹配：订单, order, 开通, eSIM
                    if any(k in subject for k in ["訂單", "Order", "開通", "eSIM", "成功"]):
                        # 读取详情
                        mail_detail = await asyncio.get_running_loop().run_in_executor(None, OneSecMail.get_message_content, mail_login, mail_domain, mail.get('id'))
                        if mail_detail:
                            # 提取激活码
                            info_text = YanciBotLogic.extract_esim_info(mail_detail.get('body', ''))
                            if info_text:
                                esim_info = info_text
                                break
            
            if esim_info:
                break
            await asyncio.sleep(5)

        # 最终结果推送
        if esim_info:
            final_text = (
                f"✅ **eSIM 自动提取成功！**\n\n"
                f"📧 账户: `{email}`\n"
                f"🔑 密码: `{FIXED_PASSWORD}`\n\n"
                f"{esim_info}\n\n"
                f"祝您使用愉快！"
            )
        else:
            final_text = (
                f"✅ **任务完成 (但未捕获到发货邮件)**\n\n"
                f"📧 账户: `{email}`\n"
                f"🔑 密码: `{FIXED_PASSWORD}`\n\n"
                f"发货可能延迟，请稍后手动登录邮箱或扬奇官网查看。\n"
                f"临时邮箱查询地址: https://www.1secmail.com/mailbox"
            )

        # 发送新消息告知结果
        await context.bot.send_message(chat_id=user.id, text=final_text, parse_mode='Markdown')

    except Exception as e:
        logger.error(traceback.format_exc())
        await msg_status.edit_text(f"💥 自动化流程异常: {str(e)}")


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state', STATE_NONE)
    text = update.message.text.strip()
    user = update.effective_user

    if state == STATE_NONE: return

    # === 管理员操作 ===
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

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_input))
    
    print("🤖 Yanci Auto Bot (1secmail) 已启动...")
    application.run_polling()
