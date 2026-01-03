import sys
import traceback
import asyncio
# from bs4 import BeautifulSoup  <-- 已移除此行，避免报错
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
@@ -17,20 +16,104 @@
load_dotenv()

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
# 如果本地测试没有 .env，可以在这里填入 token（生产环境请勿填写）
# BOT_TOKEN = "YOUR_TOKEN_HERE"
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
@@ -44,8 +127,6 @@
"order": "https://www.yanci.com.tw/gives"
}

# [关键修复]：严格对齐 yanci_final_v4.py 的 Headers
# 移除了 'Upgrade-Insecure-Requests'，防止 AJAX 请求被识别为页面访问
HEADERS_BASE = {
'Host': 'www.yanci.com.tw',
'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
@@ -54,7 +135,7 @@
'Origin': 'https://www.yanci.com.tw',
}

# ================= 逻辑工具类 =================
# ================= 逻辑工具类 (保持不变) =================

class YanciBotLogic:
"""封装核心业务逻辑，确保 Session 和状态管理清晰"""
@@ -118,14 +199,10 @@ def extract_id(text_or_url):
def extract_text_from_html(html_content):
"""尝试从 HTML 中提取有用的提示信息"""
try:
            # 简单的正则提取 alert('xxx') 内容
alert_match = re.search(r"alert\(['\"](.*?)['\"]\)", html_content)
if alert_match:
return f"弹窗提示: {alert_match.group(1)}"
            
            # 提取 body 文本 (简单版)
clean_text = re.sub('<[^<]+?>', '', html_content).strip()
            # 截取一部分，防止太长
return clean_text[:100].replace('\n', ' ')
except:
return "无法解析页面内容"
@@ -135,7 +212,6 @@ def get_initial_session():
session = requests.Session()
session.headers.update(HEADERS_BASE)
try:
            # 这里的 get 需要 allow_redirects=True 才能获取到跳转后的 ID
resp = session.get(URLS['entry'] + "?lg=tw", timeout=15, allow_redirects=True)
found_id = YanciBotLogic.extract_id(resp.url) or YanciBotLogic.extract_id(resp.text)

@@ -169,7 +245,6 @@ def register_loop(session, email, phone, start_id):
resp = session.post(URLS['register'], headers=headers, data=payload, timeout=20)
resp.encoding = 'utf-8'

                # 检查 JSON 错误
try:
res_json = resp.json()
if isinstance(res_json, list) and len(res_json) > 0:
@@ -182,7 +257,6 @@ def register_loop(session, email, phone, start_id):
except:
pass

                # HTML 错误 / ID 纠错
if "<!DOCTYPE html>" in resp.text or "vc=Y" in resp.text:
new_id = YanciBotLogic.extract_id(resp.text) or YanciBotLogic.extract_id(resp.url)
if new_id and new_id != current_id:
@@ -224,7 +298,6 @@ def login(session, email):
headers = HEADERS_BASE.copy()
headers['Referer'] = URLS['login']
headers['X-Requested-With'] = 'XMLHttpRequest'
        # [关键修复] 严格对齐 yanci_final_v4.py 的 Accept，模拟 jQuery
headers['Accept'] = 'application/json, text/javascript, */*; q=0.01'

payload = {
@@ -248,7 +321,6 @@ def update_profile(session, phone):
headers = HEADERS_BASE.copy()
headers['Referer'] = 'https://www.yanci.com.tw/member_edit'
headers['X-Requested-With'] = 'XMLHttpRequest'
        # 注意：这里保持默认 Accept 即可，原代码就是 copy()

payload = {
'userName': name, 'userSex': sex, 'userPhn': phone, 'userTel': phone,
@@ -268,13 +340,10 @@ def update_profile(session, phone):
def place_order(session):
time.sleep(1.0) # 稍微等待

        # [关键修复] 完全移除多余的预访问，直接对齐原代码逻辑
        # headers 严格对齐原代码
headers = HEADERS_BASE.copy()
headers['Referer'] = 'https://www.yanci.com.tw/product_give'
headers['X-Requested-With'] = 'XMLHttpRequest'

        # 确保没有 Upgrade-Insecure-Requests (虽然 HEADERS_BASE 已经移除了，这里双重保险)
if 'Upgrade-Insecure-Requests' in headers:
del headers['Upgrade-Insecure-Requests']

@@ -285,7 +354,6 @@ def place_order(session):

logger.info(f"下单接口返回: Status={resp.status_code} | Body Len={len(resp.text)}")

            # 1. 优先尝试解析 JSON (成功情况)
try:
res_json = resp.json()
if isinstance(res_json, list) and len(res_json) > 0:
@@ -297,20 +365,15 @@ def place_order(session):
elif code == '400':
return False, f"服务器拒绝: {msg}"
except:
                pass # 不是 JSON，继续往下
                pass 

            # 2. 处理 HTML 返回 (通常是失败/重定向)
if resp.status_code == 200:
if "<!DOCTYPE html>" in resp.text or "<html" in resp.text:
                    # 尝试解析页面里的具体信息
title_match = re.search(r'<title>(.*?)</title>', resp.text, re.IGNORECASE)
page_title = title_match.group(1) if title_match else "未知页面"
                    
                    # 提取页面里的 alert 内容，看看服务器说了什么
page_text = YanciBotLogic.extract_text_from_html(resp.text)
logger.warning(f"下单返回 HTML: 标题={page_title}, 内容={page_text}")

                    # [修复] 增加对 '登入' 的模糊匹配，无论是标题还是内容
if "登入" in page_title or "Login" in page_title or "登入" in page_text:
return False, "下单失败: 会话失效(需重登录)"

@@ -325,15 +388,115 @@ def place_order(session):
# ================= Telegram Bot Handlers =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Yanci 自动助手 (V12.6 自动重连版)**\n\n"
        "指令列表：\n"
        "`/new <邮箱>` - 开始新任务 (自动注册->发信)\n\n"
        "示例：`/new test@example.com`",
        parse_mode='Markdown'
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
@@ -342,6 +505,9 @@ async def new_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
email = context.args[0]
phone = YanciBotLogic.generate_taiwan_phone()

        # 记录使用次数
        user_manager.increment_usage(user.id, user.first_name)
        
msg = await update.message.reply_text(f"🚀 初始化任务...\n邮箱: `{email}`\n手机: `{phone}`", parse_mode='Markdown')

session, verify_id, init_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.get_initial_session)
@@ -395,7 +561,73 @@ async def new_task(update: Update, context: ContextTypes.DEFAULT_TYPE):

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
@@ -433,18 +665,14 @@ async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
None, YanciBotLogic.place_order, session
)

        # [新增] 自动重试机制：如果是因为登录失效，则尝试重新登录一次
        # 自动重试机制
if not order_success and ("登入" in order_msg or "失效" in order_msg):
await query.edit_message_text(f"⚠️ 会话闪断，正在自动重新登录补救...")
             
             # 重新登录
relogin_success, relogin_msg = await asyncio.get_running_loop().run_in_executor(
None, YanciBotLogic.login, session, email
)
             
if relogin_success:
await query.edit_message_text(f"✅ 补救登录成功，正在重试下单...")
                 # 重新下单
order_success, order_msg = await asyncio.get_running_loop().run_in_executor(
None, YanciBotLogic.place_order, session
)
@@ -468,6 +696,12 @@ async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("new", new_task))
    # 新增指令
    application.add_handler(CommandHandler("id", my_id))
    application.add_handler(CommandHandler("adduser", add_user))
    application.add_handler(CommandHandler("deluser", del_user))
    application.add_handler(CommandHandler("stats", stats))
    
application.add_handler(CallbackQueryHandler(button_callback))

print("🤖 Bot 已启动...")
