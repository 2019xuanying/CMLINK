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
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# ================= 环境配置 =================
load_dotenv()

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
# [新增] 管理员 ID，只有此 ID 可以执行管理命令
# 请在 .env 中添加 TG_ADMIN_ID=123456789，或者直接在这里填入数字
ADMIN_ID = os.getenv("TG_ADMIN_ID") 

if not BOT_TOKEN:
    print("❌ 错误：未找到 TG_BOT_TOKEN。请检查环境变量或 .env 文件。")
    sys.exit(1)

# 如果环境变量没配，转换类型防止报错，这里做个简单的容错
try:
    if ADMIN_ID:
        ADMIN_ID = int(ADMIN_ID)
    else:
        print("⚠️ 警告：未设置 TG_ADMIN_ID，管理功能将无法使用。")
except ValueError:
    print("❌ 错误：TG_ADMIN_ID 必须是数字。")
    sys.exit(1)

# 配置日志
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
        """加载用户数据"""
        if not os.path.exists(self.FILE_PATH):
            return {"users": {}}
        try:
            with open(self.FILE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载数据失败: {e}")
            return {"users": {}}

    def _save(self):
        """保存用户数据"""
        try:
            with open(self.FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存数据失败: {e}")

    def authorize_user(self, user_id, username=None):
        """授权用户"""
        uid = str(user_id)
        if uid not in self.data["users"]:
            self.data["users"][uid] = {"authorized": True, "count": 0, "name": username or "Unknown"}
        else:
            self.data["users"][uid]["authorized"] = True
            if username: self.data["users"][uid]["name"] = username
        self._save()
        return True

    def revoke_user(self, user_id):
        """移除权限"""
        uid = str(user_id)
        if uid in self.data["users"]:
            self.data["users"][uid]["authorized"] = False
            self._save()
            return True
        return False

    def is_authorized(self, user_id):
        """检查是否有权限"""
        # 管理员永远有权限
        if ADMIN_ID and user_id == ADMIN_ID:
            return True
        
        uid = str(user_id)
        user = self.data["users"].get(uid)
        return user and user.get("authorized", False)

    def increment_usage(self, user_id, username=None):
        """增加使用次数"""
        uid = str(user_id)
        if uid not in self.data["users"]:
            self.data["users"][uid] = {"authorized": False, "count": 1, "name": username or "Unknown"}
        else:
            self.data["users"][uid]["count"] += 1
            if username: self.data["users"][uid]["name"] = username
        self._save()

    def get_all_stats(self):
        """获取所有统计信息"""
        return self.data["users"]

# 初始化管理器
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
    """封装核心业务逻辑，确保 Session 和状态管理清晰"""
    
    @staticmethod
    def generate_taiwan_phone():
        return f"09{random.randint(10000000, 99999999)}"

    @staticmethod
    def generate_random_name():
        """生成随机姓名"""
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
        """生成随机但合法的台湾地址结构"""
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
        
        return {
            "city": loc["city"],
            "area": loc["area"],
            "zip": loc["zip"],
            "addr": full_addr
        }

    @staticmethod
    def extract_id(text_or_url):
        match_url = re.search(r'[&?](\d{5})(?:$|&)', text_or_url)
        if match_url: return match_url.group(1)
        
        match_html = re.search(r'vc=Y(?:&amp;|&)(\d{5})', text_or_url)
        if match_html: return match_html.group(1)
            
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
            
            payload = {
                'userMode': 'normal', 'userACC': email, 'userPWD': FIXED_PASSWORD,
                'userPhn': phone, 'userChk': 'true', 'userPage': ''
            }
            
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
                            if "唯一" in msg or "重複" in msg or "重复" in msg:
                                return True, current_id, "账号已存在(视为成功)"
                            return False, current_id, f"服务器拒绝: {msg}"
                except:
                    pass

                if "<!DOCTYPE html>" in resp.text or "vc=Y" in resp.text:
                    new_id = YanciBotLogic.extract_id(resp.text) or YanciBotLogic.extract_id(resp.url)
                    if new_id and new_id != current_id:
                        logger.info(f"检测到 ID 变更 (旧: {current_id} -> 新: {new_id})，准备重试...")
                        current_id = new_id
                        time.sleep(1)
                        continue
                    else:
                        return False, current_id, "注册被拒绝且无法获取新ID"

                if resp.status_code == 200:
                    return True, current_id, "注册请求已发送"
                
                return False, current_id, f"HTTP状态异常: {resp.status_code}"

            except Exception as e:
                return False, current_id, f"请求异常: {str(e)}"
        
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
            if resp.status_code == 200 and "400" not in resp.text:
                return True, "发送成功"
            return False, f"发送失败 (Code: {resp.status_code})"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def login(session, email):
        headers = HEADERS_BASE.copy()
        headers['Referer'] = URLS['login']
        headers['X-Requested-With'] = 'XMLHttpRequest'
        headers['Accept'] = 'application/json, text/javascript, */*; q=0.01'
        
        payload = {
            'userMode': 'normal', 'userACC': email, 'userPWD': FIXED_PASSWORD,
            'userRem': 'true', 'userPage': ''
        }
        try:
            resp = session.post(URLS['login'], headers=headers, data=payload, timeout=20)
            if resp.status_code == 200 and "alert" not in resp.text:
                return True, "登录成功"
            return False, "登录失败(可能是密码错误或未验证)"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def update_profile(session, phone):
        name = YanciBotLogic.generate_random_name()
        addr_data = YanciBotLogic.generate_random_address()
        sex = '男性' if random.random() > 0.5 else '女性'
        
        headers = HEADERS_BASE.copy()
        headers['Referer'] = 'https://www.yanci.com.tw/member_edit'
        headers['X-Requested-With'] = 'XMLHttpRequest'
        
        payload = {
            'userName': name, 'userSex': sex, 'userPhn': phone, 'userTel': phone,
            'userZip': addr_data['zip'], 'userCity': addr_data['city'],
            'userArea': addr_data['area'], 'userAddr': addr_data['addr']
        }
        
        logger.info(f"正在更新资料: {name} | {addr_data['city']}{addr_data['area']}")
        
        try:
            resp = session.post(URLS['update'], headers=headers, data=payload, timeout=20)
            return resp.status_code == 200, name
        except:
            return False, name

    @staticmethod
    def place_order(session):
        time.sleep(1.0) # 稍微等待

        headers = HEADERS_BASE.copy()
        headers['Referer'] = 'https://www.yanci.com.tw/product_give'
        headers['X-Requested-With'] = 'XMLHttpRequest'
        
        if 'Upgrade-Insecure-Requests' in headers:
            del headers['Upgrade-Insecure-Requests']

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
                    if code == '200':
                        return True, f"下单成功: {msg}"
                    elif code == '400':
                        return False, f"服务器拒绝: {msg}"
            except:
                pass 

            if resp.status_code == 200:
                if "<!DOCTYPE html>" in resp.text or "<html" in resp.text:
                    title_match = re.search(r'<title>(.*?)</title>', resp.text, re.IGNORECASE)
                    page_title = title_match.group(1) if title_match else "未知页面"
                    page_text = YanciBotLogic.extract_text_from_html(resp.text)
                    logger.warning(f"下单返回 HTML: 标题={page_title}, 内容={page_text}")
                    
                    if "登入" in page_title or "Login" in page_title or "登入" in page_text:
                        return False, "下单失败: 会话失效(需重登录)"
                    
                    return False, f"服务器返回页面: {page_title} (可能是: {page_text})"
                
                return True, "请求发送成功 (未返回错误)"
                
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

# ================= Telegram Bot Handlers =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # 基础欢迎语与说明
    welcome_text = (
        f"👋 **Yanci 自动助手 (V12.7 交互管理版)**\n\n"
        f"你好，{user.first_name}！\n\n"
        "🚀 **开始任务**：\n"
        "请直接发送指令：`/new 邮箱地址`\n"
        "例如：`/new test@example.com`"
    )
    
    # 普通用户按钮
    keyboard = [
        [InlineKeyboardButton("🆔 查看我的 ID", callback_data="check_my_id")],
    ]
    
    # 管理员特权按钮和说明
    if ADMIN_ID and user.id == ADMIN_ID:
        welcome_text += (
            "\n\n👮 **管理员指令**：\n"
            "• `/adduser <ID>` - 授权\n"
            "• `/deluser <ID>` - 移除\n"
            "• 点击下方按钮查看统计"
        )
        keyboard.append([InlineKeyboardButton("📊 查看所有统计", callback_data="admin_stats")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """用户查询自己的 ID (指令版)"""
    user_id = update.effective_user.id
    status = "✅ 已授权" if user_manager.is_authorized(user_id) else "🚫 未授权"
    await update.message.reply_text(f"🆔 您的 Telegram ID: `{user_id}`\n状态: {status}", parse_mode='Markdown')

# ----- 管理员指令 -----

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员添加用户"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        return # 静默忽略非管理员指令

    if not context.args:
        await update.message.reply_text("❌ 用法: `/adduser 123456789`")
        return

    try:
        target_id = int(context.args[0])
        user_manager.authorize_user(target_id)
        await update.message.reply_text(f"✅ 已授权用户 `{target_id}` 使用机器人。", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ ID 必须是数字。")

async def del_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员移除用户"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        return 

    if not context.args:
        await update.message.reply_text("❌ 用法: `/deluser 123456789`")
        return

    try:
        target_id = int(context.args[0])
        if user_manager.revoke_user(target_id):
            await update.message.reply_text(f"🚫 已移除用户 `{target_id}` 的权限。", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"ℹ️ 用户 `{target_id}` 本来就没有权限或不存在。", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ ID 必须是数字。")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员查看统计 (指令版)"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        return 

    data = user_manager.get_all_stats()
    if not data:
        await update.message.reply_text("📊 暂无用户数据。")
        return

    msg = "📊 **用户统计列表**\n\n"
    for uid, info in data.items():
        auth_icon = "✅" if info.get('authorized') else "🚫"
        name = info.get('name', 'Unknown')
        count = info.get('count', 0)
        msg += f"{auth_icon} `{uid}` ({name}): **{count}** 次\n"

    await update.message.reply_text(msg, parse_mode='Markdown')

# ----- 核心功能 -----

async def new_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # 权限检查拦截
    if not user_manager.is_authorized(user.id):
        await update.message.reply_text(
            f"🚫 **访问被拒绝**\n\n"
            f"您没有权限使用此机器人。\n"
            f"请将您的 ID 发送给管理员@ziqing2025申请授权：\n"
            f"ID: `{user.id}`",
            parse_mode='Markdown'
        )
        return

    try:
        if not context.args:
            await update.message.reply_text("❌ 请输入邮箱，例如：\n`/new abc@gmail.com`")
            return

        email = context.args[0]
        phone = YanciBotLogic.generate_taiwan_phone()
        
        # 记录使用次数
        user_manager.increment_usage(user.id, user.first_name)
        
        msg = await update.message.reply_text(f"🚀 初始化任务...\n邮箱: `{email}`\n手机: `{phone}`", parse_mode='Markdown')

        session, verify_id, init_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.get_initial_session)
        
        if not session or not verify_id:
            await msg.edit_text(f"❌ 初始化失败: {init_msg}")
            return
            
        context.user_data['session'] = session
        context.user_data['email'] = email
        context.user_data['phone'] = phone
        
        await msg.edit_text(f"✅ 获取 ID: {verify_id}\n⏳ 正在执行智能注册 (可能需要尝试多次)...")

        reg_success, final_id, reg_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.register_loop, session, email, phone, verify_id
        )
        
        if not reg_success:
            await msg.edit_text(f"❌ 注册失败: {reg_msg}")
            return

        context.user_data['verify_id'] = final_id
        
        await msg.edit_text(f"✅ 注册通过 (最终ID: {final_id})\n⏳ 正在申请验证邮件...")
        
        send_success, send_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.send_verify_email, session, final_id
        )
        
        if not send_success:
            await msg.edit_text(f"❌ 发信失败: {send_msg}")
            return

        keyboard = [
            [InlineKeyboardButton("✅ 我已点击邮件链接验证", callback_data="verify_done")],
            [InlineKeyboardButton("❌ 取消", callback_data="cancel_task")]
        ]
        
        await msg.edit_text(
            f"📩 **验证信已发送！**\n\n"
            f"请前往邮箱 `{email}` 点击验证链接。\n"
            f"完成后，点击下方按钮继续。",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"任务错误: {traceback.format_exc()}")
        await update.message.reply_text(f"💥 机器人发生未捕获异常: {str(e)}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    await query.answer()
    
    # --- 新增：菜单按钮逻辑 ---
    
    if query.data == "check_my_id":
        status = "✅ 已授权" if user_manager.is_authorized(user.id) else "🚫 未授权"
        # 使用 edit_message_text 替换原消息，保持界面整洁
        await query.edit_message_text(
            f"👋 **用户信息**\n\n"
            f"👤 姓名: {user.first_name}\n"
            f"🆔 Telegram ID: `{user.id}`\n"
            f"🔐 权限状态: {status}\n\n"
            "💡 发送 `/new <邮箱>` 开始任务",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]]),
            parse_mode='Markdown'
        )
        return

    if query.data == "admin_stats":
        if ADMIN_ID and user.id != ADMIN_ID:
            await query.edit_message_text("🚫 您没有权限查看统计。")
            return

        data = user_manager.get_all_stats()
        if not data:
            msg = "📊 暂无用户数据。"
        else:
            msg = "📊 **用户统计列表**\n\n"
            for uid, info in data.items():
                auth_icon = "✅" if info.get('authorized') else "🚫"
                name = info.get('name', 'Unknown')
                count = info.get('count', 0)
                msg += f"{auth_icon} `{uid}` ({name}): **{count}** 次\n"
        
        # 增加刷新按钮
        keyboard = [
            [InlineKeyboardButton("🔄 刷新数据", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
        ]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    if query.data == "main_menu":
        # 恢复主菜单界面
        welcome_text = (
            f"👋 **Yanci 自动助手 (V12.7 交互管理版)**\n\n"
            f"你好，{user.first_name}！\n\n"
            "🚀 **开始任务**：\n"
            "请直接发送指令：`/new 邮箱地址`\n"
            "例如：`/new test@example.com`"
        )
        keyboard = [[InlineKeyboardButton("🆔 查看我的 ID", callback_data="check_my_id")]]
        
        if ADMIN_ID and user.id == ADMIN_ID:
            welcome_text += (
                "\n\n👮 **管理员指令**：\n"
                "• `/adduser <ID>` - 授权\n"
                "• `/deluser <ID>` - 移除\n"
                "• 点击下方按钮查看统计"
            )
            keyboard.append([InlineKeyboardButton("📊 查看所有统计", callback_data="admin_stats")])
            
        await query.edit_message_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    # --- 原有：任务流程逻辑 ---

    if query.data == "cancel_task":
        await query.edit_message_text("🚫 任务已取消。")
        return

    if query.data == "verify_done":
        session = context.user_data.get('session')
        email = context.user_data.get('email')
        phone = context.user_data.get('phone')
        
        if not session:
            await query.edit_message_text("❌ 会话已过期，请重新运行 /new。")
            return

        await query.edit_message_text("⏳ 正在登录...")

        login_success, login_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.login, session, email
        )
        if not login_success:
            await query.edit_message_text(f"❌ {login_msg}\n(如果刚验证完，请稍等几秒再试，或检查是否真验证成功)")
            return

        await query.edit_message_text("✅ 登录成功，正在生成并完善随机资料...")
        update_success, name = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.update_profile, session, phone
        )
        
        if not update_success:
            await query.edit_message_text("❌ 资料保存失败，停止下单。")
            return

        await query.edit_message_text(f"✅ 资料已保存 (姓名: {name})\n⏳ 正在尝试下单...")
        order_success, order_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.place_order, session
        )

        # 自动重试机制
        if not order_success and ("登入" in order_msg or "失效" in order_msg):
             await query.edit_message_text(f"⚠️ 会话闪断，正在自动重新登录补救...")
             relogin_success, relogin_msg = await asyncio.get_running_loop().run_in_executor(
                None, YanciBotLogic.login, session, email
             )
             if relogin_success:
                 await query.edit_message_text(f"✅ 补救登录成功，正在重试下单...")
                 order_success, order_msg = await asyncio.get_running_loop().run_in_executor(
                    None, YanciBotLogic.place_order, session
                 )
             else:
                 order_msg = f"自动重连失败: {relogin_msg}"
        
        if order_success:
            await query.edit_message_text(
                f"🎉 **任务圆满完成！**\n\n"
                f"📧 邮箱: `{email}`\n"
                f"👤 姓名: {name}\n"
                f"✅ 结果: {order_msg}\n\n"
                f"请登录网页版查看订单。",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(f"❌ 下单失败: {order_msg}")

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_task))
    # 新增指令
    application.add_handler(CommandHandler("id", my_id))
    application.add_handler(CommandHandler("adduser", add_user))
    application.add_handler(CommandHandler("deluser", del_user))
    application.add_handler(CommandHandler("stats", stats))
    
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("🤖 Bot 已启动...")
    application.run_polling()
