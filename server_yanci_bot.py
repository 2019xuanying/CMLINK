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
from urllib.parse import unquote, urlparse, parse_qs
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
            return {"users": {}, "config": {"send_qr": True}} # 默认配置
        try:
            with open(self.FILE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "config" not in data:
                    data["config"] = {"send_qr": True}
                return data
        except Exception as e:
            logger.error(f"加载数据失败: {e}")
            return {"users": {}, "config": {"send_qr": True}}

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
    
    # --- 配置相关 ---
    def get_config(self, key, default=None):
        return self.data["config"].get(key, default)

    def set_config(self, key, value):
        self.data["config"][key] = value
        self._save()

user_manager = UserManager()

# ================= 临时邮箱工具类 (Mail.tm) =================
class MailTm:
    BASE_URL = "https://api.mail.tm"

    @staticmethod
    def create_account():
        """创建临时账户，返回 (address, token)"""
        try:
            # 1. 获取可用域名
            domains_resp = requests.get(f"{MailTm.BASE_URL}/domains", timeout=10)
            if domains_resp.status_code != 200:
                return None, None
            
            domains_data = domains_resp.json().get('hydra:member', [])
            if not domains_data:
                return None, None
            
            domain = domains_data[0]['domain'] 

            # 2. 生成随机账号密码
            username = "".join(random.choices("abcdefghijklmnopqrstuvwxyz1234567890", k=10))
            password = "".join(random.choices("abcdefghijklmnopqrstuvwxyz1234567890", k=12))
            address = f"{username}@{domain}"

            # 3. 注册账户
            reg_resp = requests.post(
                f"{MailTm.BASE_URL}/accounts", 
                json={"address": address, "password": password},
                timeout=10
            )
            if reg_resp.status_code != 201:
                return None, None

            # 4. 获取 Token (登录)
            token_resp = requests.post(
                f"{MailTm.BASE_URL}/token",
                json={"address": address, "password": password},
                timeout=10
            )
            if token_resp.status_code != 200:
                return None, None

            token = token_resp.json().get('token')
            return address, token

        except Exception as e:
            logger.error(f"MailTm create_account exception: {e}")
            return None, None

    @staticmethod
    def check_inbox(token):
        """检查收件箱，需要 Token"""
        if not token: return []
        headers = {"Authorization": f"Bearer {token}"}
        try:
            resp = requests.get(f"{MailTm.BASE_URL}/messages", headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.json().get('hydra:member', [])
            return []
        except:
            return []

    @staticmethod
    def get_message_content(token, msg_id):
        """获取邮件具体内容"""
        if not token: return None
        headers = {"Authorization": f"Bearer {token}"}
        try:
            resp = requests.get(f"{MailTm.BASE_URL}/messages/{msg_id}", headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # 优先返回 html，其次 text
                body = data.get('html')
                if not body:
                    body = data.get('text')
                
                # 强制转换为字符串，防止 None
                if body is None:
                    body = ""
                elif not isinstance(body, str):
                    body = str(body)

                subject = data.get('subject')
                if subject is None:
                    subject = ""
                
                return {'body': body, 'subject': str(subject)}
            return None
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
        if not html_content or not isinstance(html_content, str):
            return None
        match = re.search(r'(https?://www\.yanci\.com\.tw/sendvcurl[^\s"\'<>]+)', html_content)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def extract_text_from_html(html_content):
        """尝试从 HTML 中提取有用的提示信息"""
        try:
            alert_match = re.search(r"alert\(['\"](.*?)['\"]\)", html_content)
            if alert_match:
                return f"弹窗提示: {alert_match.group(1)}"
            clean_text = re.sub('<[^<]+?>', '', html_content).strip()
            return clean_text[:100].replace('\n', ' ')
        except:
            return "无法解析页面内容"
        
    @staticmethod
    def extract_esim_info(html_content):
        """从邮件中智能提取 LPA、激活码和二维码链接"""
        if not html_content or not isinstance(html_content, str):
            return None

        info = {}

        # 1. 提取 SM-DP+ Address 和 激活码
        # 使用非贪婪匹配和忽略标签的模式来穿透 HTML
        # 匹配 【SM-DP+Address】 后面的所有标签和空白，直到捕获非标签内容
        sm_dp_match = re.search(r'【SM-DP\+Address】(?:[\s\n<[^>]+>]*)([\w\.\-]+)', html_content)
        code_match = re.search(r'【啟用碼】(?:[\s\n<[^>]+>]*)([\w\-]+)', html_content)

        if sm_dp_match and code_match:
            sm_dp = sm_dp_match.group(1).strip()
            code = code_match.group(1).strip()
            # 拼接标准 LPA 格式
            info['lpa_str'] = f"LPA:1${sm_dp}${code}"
            info['address'] = sm_dp
            info['code'] = code

        # 2. 提取二维码图片链接 (优先找 quickchart)
        qr_match = re.search(r'(https?://quickchart\.io/qr\?[^"\'\s>]+)', html_content)
        if qr_match:
            # 清理 URL 中的 HTML 实体
            info['qr_url'] = qr_match.group(1).replace('&amp;', '&')
        
        # 3. 如果没找到 quickchart，尝试通用的 img src 匹配 (作为备用)
        if 'qr_url' not in info:
             # 排除 icon, banner, footer, logo 等干扰项
             img_candidates = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html_content)
             for img_url in img_candidates:
                 if not any(k in img_url for k in ['icon', 'banner', 'footer', 'logo']):
                     if 'qr' in img_url.lower() or 'code' in img_url.lower():
                         info['qr_url'] = img_url
                         break

        # 4. 如果第1步失败，尝试从 quickchart URL 中反解 LPA
        if 'lpa_str' not in info and 'qr_url' in info:
            try:
                parsed = urlparse(info['qr_url'])
                qs = parse_qs(parsed.query)
                if 'text' in qs:
                    info['lpa_str'] = qs['text'][0]
            except:
                pass

        return info if info else None

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
            headers['Referer'] = 'https://mail.tm/' # 模拟从邮箱跳转
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
        f"👋 **Yanci 全自动助手 (V14.3 Pro)**\n\n"
        f"你好，{user.first_name}！\n\n"
        f"🚀 **一键功能**：自动注册 -> 自动验证 -> 自动下单 -> 自动提取 eSIM"
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
        
        asyncio.create_task(run_auto_task(query, context, user))
        return

    if data == "btn_my_info":
        status = "✅ 已授权" if user_manager.is_authorized(user.id) else "🚫 未授权"
        await query.edit_message_text(f"👤 **用户信息**\n\n姓名: {user.first_name}\nID: `{user.id}`\n状态: {status}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]]), parse_mode='Markdown')
        return

    if data == "btn_admin_menu":
        if user.id != ADMIN_ID: return
        context.user_data['state'] = STATE_NONE
        
        # 获取当前发图设置
        send_qr = user_manager.get_config("send_qr", True)
        qr_status = "✅ 开启" if send_qr else "🔴 关闭"
        
        keyboard = [
            [InlineKeyboardButton("✅ 授权用户", callback_data="admin_add"), InlineKeyboardButton("🚫 移除用户", callback_data="admin_del")],
            [InlineKeyboardButton(f"🖼 发图设置: {qr_status}", callback_data="admin_toggle_qr")],
            [InlineKeyboardButton("📊 查看统计", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
        ]
        await query.edit_message_text("👮 **管理面板**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return
    
    if data == "admin_toggle_qr":
        if user.id != ADMIN_ID: return
        current = user_manager.get_config("send_qr", True)
        new_state = not current
        user_manager.set_config("send_qr", new_state)
        
        # 刷新界面
        qr_status = "✅ 开启" if new_state else "🔴 关闭"
        keyboard = [
            [InlineKeyboardButton("✅ 授权用户", callback_data="admin_add"), InlineKeyboardButton("🚫 移除用户", callback_data="admin_del")],
            [InlineKeyboardButton(f"🖼 发图设置: {qr_status}", callback_data="admin_toggle_qr")],
            [InlineKeyboardButton("📊 查看统计", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
        ]
        await query.edit_message_text("👮 **管理面板**\n设置已更新。", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
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
    
    await query.edit_message_text("🏗 **正在初始化环境...**\n⏳ 正在申请临时邮箱 (Mail.tm)...")
    
    email, mail_token = MailTm.create_account()
    if not email or not mail_token:
        await query.edit_message_text("❌ 临时邮箱创建失败，请稍后再试。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]]))
        return
        
    phone = YanciBotLogic.generate_taiwan_phone()
    user_manager.increment_usage(user.id, user.first_name)
    
    msg_status = await query.edit_message_text(
        f"🚀 **任务启动**\n\n"
        f"📧 `{email}`\n"
        f"⏳ **正在连接服务器...**", 
        parse_mode='Markdown'
    )

    try:
        session, verify_id, init_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.get_initial_session)
        if not session:
            await msg_status.edit_text(f"❌ 初始化失败: {init_msg}")
            return

        await msg_status.edit_text(f"✅ 获取ID: {verify_id}\n⏳ **正在提交注册请求...**")
        reg_success, final_id, reg_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.register_loop, session, email, phone, verify_id
        )
        if not reg_success:
            await msg_status.edit_text(f"❌ 注册被拒: {reg_msg}")
            return

        await msg_status.edit_text(f"✅ 注册请求已通过\n⏳ **正在触发验证邮件...**")
        send_success, send_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.send_verify_email, session, final_id
        )
        if not send_success:
            await msg_status.edit_text(f"❌ 发信失败: {send_msg}")
            return

        await msg_status.edit_text(f"📩 **验证信已发送！**\n⏳ 正在自动监听邮箱 (最多等2分钟)...")
        
        verification_link = None
        start_time = time.time()
        
        while time.time() - start_time < 120:
            mails = await asyncio.get_running_loop().run_in_executor(None, MailTm.check_inbox, mail_token)
            if mails:
                for mail in mails:
                    if "驗證" in mail.get('subject', '') or "Verify" in mail.get('subject', '') or "验证" in mail.get('subject', ''):
                        mail_detail = await asyncio.get_running_loop().run_in_executor(None, MailTm.get_message_content, mail_token, mail.get('id'))
                        if mail_detail:
                            link = YanciBotLogic.extract_verification_link(mail_detail.get('body', ''))
                            if link:
                                verification_link = link
                                break
            if verification_link: break
            await asyncio.sleep(4)

        if not verification_link:
            await msg_status.edit_text("❌ 等待超时，未收到验证邮件。任务终止。")
            return

        await msg_status.edit_text(f"🔎 **捕获到验证链接！**\n⏳ 正在模拟点击验证...")
        visit_success, visit_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.visit_verification_link, session, verification_link
        )
        
        if not visit_success:
            await msg_status.edit_text(f"❌ 验证链接访问失败: {visit_msg}")
            return

        await msg_status.edit_text(f"✅ 邮箱验证通过！\n⏳ **正在登录并自动下单...**")
        
        login_success, login_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.login, session, email)
        if not login_success:
            await msg_status.edit_text(f"❌ 登录失败: {login_msg}")
            return
            
        update_success, name = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.update_profile, session, phone)
        if not update_success:
            await msg_status.edit_text("❌ 资料保存失败。")
            return

        order_success, order_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.place_order, session)
        
        if not order_success and ("登入" in order_msg or "失效" in order_msg):
             await msg_status.edit_text("⚠️ 会话闪断，正在重连...")
             relogin_success, _ = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.login, session, email)
             if relogin_success:
                 order_success, order_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.place_order, session)

        if not order_success:
             await msg_status.edit_text(f"❌ 下单最终失败: {order_msg}")
             return

        await msg_status.edit_text(
            f"🎉 **下单成功！**\n"
            f"📧 邮箱: `{email}`\n"
            f"⏳ **正在等待发货邮件 (最多5分钟)...**\n(请勿关闭此对话)"
        , parse_mode='Markdown')
        
        esim_data = None
        wait_mail_start = time.time()
        
        while time.time() - wait_mail_start < 300: 
            mails = await asyncio.get_running_loop().run_in_executor(None, MailTm.check_inbox, mail_token)
            if mails:
                for mail in mails:
                    subject = mail.get('subject', '')
                    if any(k in subject for k in ["訂單", "Order", "開通", "eSIM", "成功", "QR code"]):
                        mail_detail = await asyncio.get_running_loop().run_in_executor(None, MailTm.get_message_content, mail_token, mail.get('id'))
                        if mail_detail:
                            extracted = YanciBotLogic.extract_esim_info(mail_detail.get('body', ''))
                            if extracted and extracted.get('lpa_str'):
                                esim_data = extracted
                                break
            if esim_data: break
            await asyncio.sleep(5)

        # 最终结果推送
        if esim_data:
            lpa_str = esim_data.get('lpa_str', '未知')
            
            # 发送文本信息
            final_text = (
                f"✅ **eSIM 自动提取成功！**\n\n"
                f"📡 **LPA 激活串**: \n`{lpa_str}`\n\n"
                f"📧 账户: `{email}`\n"
                f"🔑 密码: `{FIXED_PASSWORD}`\n\n"
                f"祝您使用愉快！"
            )
            await context.bot.send_message(chat_id=user.id, text=final_text, parse_mode='Markdown')
            
            # 检查是否需要发送图片
            send_qr_setting = user_manager.get_config("send_qr", True)
            qr_url = esim_data.get('qr_url')
            
            if send_qr_setting and qr_url:
                try:
                    await context.bot.send_photo(chat_id=user.id, photo=qr_url, caption="📷 eSIM 二维码")
                except Exception as e:
                    logger.error(f"发图失败: {e}")
                    await context.bot.send_message(chat_id=user.id, text="⚠️ 图片发送失败，请使用上方的 LPA 码激活。")
                    
        else:
            final_text = (
                f"✅ **任务完成 (但未捕获到发货邮件)**\n\n"
                f"📧 账户: `{email}`\n"
                f"🔑 密码: `{FIXED_PASSWORD}`\n\n"
                f"发货可能延迟，请稍后手动登录邮箱或扬奇官网查看。\n"
                f"建议立刻去官网取回。"
            )
            await context.bot.send_message(chat_id=user.id, text=final_text, parse_mode='Markdown')

    except Exception as e:
        logger.error(traceback.format_exc())
        await msg_status.edit_text(f"💥 自动化流程异常: {str(e)}")


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state', STATE_NONE)
    text = update.message.text.strip()
    user = update.effective_user

    if state == STATE_NONE: return

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
    
    print("🤖 Yanci Auto Bot (Mail.tm + LPA Parser) 已启动...")
    application.run_polling()
