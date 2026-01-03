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
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters,
    ConversationHandler
)

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

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= 状态定义 (用于对话流程) =================
# 定义对话状态
WAITING_EMAIL = 1        # 等待输入邮箱
WAITING_ADD_ID = 2       # 管理员：等待输入要授权的ID
WAITING_DEL_ID = 3       # 管理员：等待输入要删除的ID

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

# ================= 核心逻辑类 =================

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
        """生成随机姓名 (完整版)"""
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
        """生成随机但合法的台湾地址结构 (完整版)"""
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
        match = re.search(r'[&?](\d{5})(?:$|&)', text_or_url) or re.search(r'vc=Y(?:&amp;|&)(\d{5})', text_or_url)
        return match.group(1) if match else None

    @staticmethod
    def get_initial_session():
        s = requests.Session()
        s.headers.update(HEADERS_BASE)
        try:
            resp = s.get(URLS['entry'] + "?lg=tw", timeout=15)
            fid = YanciBotLogic.extract_id(resp.url) or YanciBotLogic.extract_id(resp.text)
            return s, fid or str(random.randint(20000, 30000)), "成功" if fid else "随机生成"
        except Exception as e:
            return None, None, str(e)

    @staticmethod
    def register_loop(session, email, phone, start_id):
        curr_id = start_id
        for _ in range(3):
            payload = {'userMode': 'normal', 'userACC': email, 'userPWD': FIXED_PASSWORD, 'userPhn': phone, 'userChk': 'true', 'userPage': ''}
            headers = HEADERS_BASE.copy()
            headers['Referer'] = f"{URLS['entry']}?lg=tw&vc=Y&{curr_id}"
            try:
                resp = session.post(URLS['register'], headers=headers, data=payload, timeout=20)
                resp.encoding = 'utf-8'
                if "唯一" in resp.text or "重複" in resp.text: return True, curr_id, "账号已存在"
                if resp.status_code == 200 and "<!DOCTYPE" not in resp.text: return True, curr_id, "请求发送成功"
                new_id = YanciBotLogic.extract_id(resp.text)
                if new_id and new_id != curr_id: curr_id = new_id; continue
            except: pass
        return False, curr_id, "注册失败"

    @staticmethod
    def send_verify_email(session, verify_id):
        try:
            resp = session.post(f"{URLS['send_verify']}{verify_id}", headers=HEADERS_BASE, data='Y', timeout=20)
            return (resp.status_code == 200 and "400" not in resp.text), "发送失败"
        except Exception as e: return False, str(e)

    @staticmethod
    def login(session, email):
        headers = HEADERS_BASE.copy()
        headers.update({'Referer': URLS['login'], 'X-Requested-With': 'XMLHttpRequest'})
        payload = {'userMode': 'normal', 'userACC': email, 'userPWD': FIXED_PASSWORD, 'userRem': 'true', 'userPage': ''}
        try:
            resp = session.post(URLS['login'], headers=headers, data=payload, timeout=20)
            return (resp.status_code == 200 and "alert" not in resp.text), "登录失败"
        except Exception as e: return False, str(e)

    @staticmethod
    def update_profile(session, phone):
        name = YanciBotLogic.generate_random_name()
        addr = YanciBotLogic.generate_random_address()
        headers = HEADERS_BASE.copy()
        headers.update({'Referer': 'https://www.yanci.com.tw/member_edit', 'X-Requested-With': 'XMLHttpRequest'})
        payload = {'userName': name, 'userSex': '男性', 'userPhn': phone, 'userTel': phone, 'userZip': addr['zip'], 'userCity': addr['city'], 'userArea': addr['area'], 'userAddr': addr['addr']}
        try:
            resp = session.post(URLS['update'], headers=headers, data=payload, timeout=20)
            return resp.status_code == 200, name
        except: return False, name

    @staticmethod
    def place_order(session):
        headers = HEADERS_BASE.copy()
        headers.update({'Referer': 'https://www.yanci.com.tw/product_give', 'X-Requested-With': 'XMLHttpRequest'})
        payload = {'given': PRODUCT_ID, 'giveq': '1'}
        try:
            resp = session.post(URLS['order'], headers=headers, data=payload, timeout=20)
            
            # --- 增加详细日志记录 ---
            logger.info(f"[下单调试] 状态码: {resp.status_code}")
            logger.info(f"[下单调试] URL: {resp.url}")
            # 记录一部分响应内容，防止日志过长
            content_snippet = resp.text[:500].replace("\n", " ")
            logger.info(f"[下单调试] 响应内容摘要: {content_snippet}")

            if resp.status_code == 200:
                # 检查多种失败特征
                resp.encoding = 'utf-8' # 确保中文正常
                text = resp.text
                
                # 1. 检查是否重定向到了登录页 (HTML 页面特征)
                if "<!DOCTYPE html>" in text or "<html" in text:
                    # 尝试提取 Title
                    title_match = re.search(r'<title>(.*?)</title>', text, re.IGNORECASE)
                    page_title = title_match.group(1) if title_match else "未知页面"
                    
                    if "登入" in page_title or "Login" in page_title or "登入" in text:
                        return False, f"会话失效 (Title: {page_title}, URL: {resp.url})"
                    
                    # 提取部分正文用于提示
                    clean_text = re.sub(r'<[^>]+>', '', text).strip()[:100]
                    return False, f"返回了HTML页面: {page_title} - {clean_text}"

                # 2. 尝试解析 JSON 错误 (如果服务器返回 JSON)
                try:
                    res_json = resp.json()
                    if isinstance(res_json, list) and len(res_json) > 0:
                        data = res_json[0]
                        if str(data.get('code')) != '200':
                             return False, f"API错误: {data.get('msg', '未知错误')}"
                except:
                    pass

                # 3. 如果以上都没拦截，姑且认为成功
                return True, "下单请求已发送"
            
            return False, f"HTTP异常 {resp.status_code}"
        except Exception as e:
            return False, f"程序异常: {str(e)}"


# ================= Bot Handlers: 主菜单 =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示主菜单"""
    user = update.effective_user
    
    welcome_text = (
        f"👋 **欢迎回来，{user.first_name}！**\n\n"
        "我是 Yanci 自动助手。请选择操作："
    )
    
    keyboard = [
        [InlineKeyboardButton("🚀 开始新任务", callback_data="btn_new_task")],
        [InlineKeyboardButton("👤 个人信息", callback_data="btn_my_info")]
    ]
    
    # 管理员可见按钮
    if ADMIN_ID and user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👮 管理员面板", callback_data="btn_admin_panel")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 如果是 CallbackQuery (点击返回菜单)，用 edit_text；如果是 /start，用 reply_text
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    return ConversationHandler.END

# ================= Bot Handlers: 普通任务流程 =================

async def task_start_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """点击[开始新任务]后，提示输入邮箱"""
    query = update.callback_query
    user = update.effective_user
    await query.answer()

    # 权限检查
    if not user_manager.is_authorized(user.id):
        await query.edit_message_text(
            f"🚫 **无权访问**\n您的 ID `{user.id}` 未经授权。\n请联系管理员。",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]])
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "📝 **请输入目标邮箱地址：**\n\n"
        "（请直接发送邮箱，或点击下方按钮取消）",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_conv")]])
    )
    return WAITING_EMAIL

async def task_receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收用户输入的邮箱，并开始执行任务"""
    email = update.message.text.strip()
    user = update.effective_user
    
    # 简单的邮箱验证
    if "@" not in email or "." not in email:
        await update.message.reply_text("❌ 邮箱格式看似不正确，请重新输入，或输入 /cancel 取消。")
        return WAITING_EMAIL

    # 开始执行
    status_msg = await update.message.reply_text(f"🚀 收到邮箱 `{email}`，正在初始化任务...", parse_mode='Markdown')
    
    # 记录使用
    user_manager.increment_usage(user.id, user.first_name)
    
    # 后台执行逻辑
    try:
        phone = YanciBotLogic.generate_taiwan_phone()
        
        # 1. 获取 Session
        session, verify_id, _ = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.get_initial_session)
        if not session:
            await status_msg.edit_text("❌ 初始化网络连接失败，请稍后重试。")
            return ConversationHandler.END

        # 2. 注册
        await status_msg.edit_text(f"⏳ 正在注册账号 (ID: {verify_id})...")
        reg_success, final_id, reg_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.register_loop, session, email, phone, verify_id
        )
        
        if not reg_success:
            await status_msg.edit_text(f"❌ 注册失败: {reg_msg}")
            return ConversationHandler.END

        # 3. 发验证信
        await status_msg.edit_text("⏳ 正在请求验证邮件...")
        send_success, _ = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.send_verify_email, session, final_id
        )
        
        if not send_success:
            await status_msg.edit_text("❌ 发信失败。")
            return ConversationHandler.END
            
        # 保存上下文供后续步骤使用
        context.user_data['session'] = session
        context.user_data['email'] = email
        context.user_data['phone'] = phone
        
        # 4. 提示用户验证
        keyboard = [
            [InlineKeyboardButton("✅ 我已点击验证链接", callback_data="verify_done")],
            [InlineKeyboardButton("❌ 放弃任务", callback_data="cancel_task_button")] # 注意区分 Conversation 的 cancel
        ]
        
        await status_msg.edit_text(
            f"📩 **验证信已发送！**\n\n"
            f"📬 邮箱: `{email}`\n"
            f"📱 临时手机: `{phone}`\n\n"
            f"请去邮箱点击链接，然后点击下方【✅ 我已点击验证链接】按钮。",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(traceback.format_exc())
        await status_msg.edit_text(f"💥 发生错误: {str(e)}")

    return ConversationHandler.END

# ================= Bot Handlers: 任务后续按钮 =================

async def task_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 [验证完成] 或 [放弃] 按钮"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_task_button":
        await query.edit_message_text("🚫 任务已取消。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]]))
        return

    if query.data == "verify_done":
        session = context.user_data.get('session')
        email = context.user_data.get('email')
        phone = context.user_data.get('phone')
        
        if not session:
            await query.edit_message_text("⚠️ 任务会话已过期，请重新创建任务。")
            return

        await query.edit_message_text("⏳ 正在登录并补全资料...")
        
        # 登录
        login_ok, l_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.login, session, email)
        if not login_ok:
            # 允许重试
            kb = [[InlineKeyboardButton("🔄 再试一次", callback_data="verify_done")], [InlineKeyboardButton("❌ 放弃", callback_data="cancel_task_button")]]
            await query.edit_message_text(f"❌ {l_msg} (可能是还没点验证链接？)", reply_markup=InlineKeyboardMarkup(kb))
            return

        # 更新资料
        upd_ok, name = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.update_profile, session, phone)
        
        # 下单
        await query.edit_message_text(f"✅ 资料完善 ({name})\n⏳ 正在提交订单...")
        order_ok, o_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.place_order, session)
        
        if order_ok:
            result_text = f"🎉 **任务成功！**\n\n邮箱: `{email}`\n状态: {o_msg}"
        else:
            result_text = f"⚠️ **下单失败**\n原因: {o_msg}"
            
        await query.edit_message_text(
            result_text, 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]])
        )

# ================= Bot Handlers: 管理员流程 =================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ 添加授权用户", callback_data="admin_add_user")],
        [InlineKeyboardButton("➖ 移除授权用户", callback_data="admin_del_user")],
        [InlineKeyboardButton("📊 查看统计数据", callback_data="admin_view_stats")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]
    ]
    await query.edit_message_text("👮 **管理员控制面板**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ConversationHandler.END

async def admin_prompt_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("➕ 请输入要授权的 **Telegram ID** (数字):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_conv")]]))
    return WAITING_ADD_ID

async def admin_do_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.isdigit():
        user_manager.authorize_user(int(text))
        await update.message.reply_text(f"✅ 用户 `{text}` 已授权！", parse_mode='Markdown')
        # 稍微延迟后显示面板
        await asyncio.sleep(1)
        # 这里为了简单，直接发个新菜单消息，或者让用户手动回去
        await update.message.reply_text("如需继续操作，请使用 /start 唤起菜单。")
    else:
        await update.message.reply_text("❌ ID 必须是数字。")
    return ConversationHandler.END

async def admin_prompt_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("➖ 请输入要移除权限的 **Telegram ID**:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_conv")]]))
    return WAITING_DEL_ID

async def admin_do_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.isdigit():
        user_manager.revoke_user(int(text))
        await update.message.reply_text(f"🚫 用户 `{text}` 权限已移除。", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ ID 必须是数字。")
    return ConversationHandler.END

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = user_manager.get_all_stats()
    msg = "📊 **用户统计**\n\n"
    if not data: msg += "无数据。"
    for uid, info in data.items():
        icon = "✅" if info.get('authorized') else "🚫"
        msg += f"{icon} `{uid}` ({info.get('name')}): {info.get('count', 0)}次\n"
    
    kb = [[InlineKeyboardButton("🔄 刷新", callback_data="admin_view_stats")], [InlineKeyboardButton("🔙 返回", callback_data="btn_admin_panel")]]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

# ================= 通用 Handlers =================

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """通用的取消对话操作"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🚫 操作已取消。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]]))
    return ConversationHandler.END

async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    await query.answer()
    status = "✅ 已授权" if user_manager.is_authorized(user.id) else "🚫 未授权"
    await query.edit_message_text(
        f"👤 **个人信息**\n\nID: `{user.id}`\n状态: {status}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]])
    )

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """返回主菜单 Wrapper"""
    # 复用 start 函数逻辑，但 context 有点不同，直接调用即可
    await start(update, context)
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # 1. 任务创建的对话处理器
    task_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(task_start_prompt, pattern='^btn_new_task$')],
        states={
            WAITING_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, task_receive_email),
                CallbackQueryHandler(cancel_conv, pattern='^cancel_conv$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conv)]
    )

    # 2. 管理员添加用户的对话处理器
    admin_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_prompt_add, pattern='^admin_add_user$')],
        states={
            WAITING_ADD_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_do_add),
                CallbackQueryHandler(cancel_conv, pattern='^cancel_conv$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conv)]
    )

    # 3. 管理员删除用户的对话处理器
    admin_del_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_prompt_del, pattern='^admin_del_user$')],
        states={
            WAITING_DEL_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_do_del),
                CallbackQueryHandler(cancel_conv, pattern='^cancel_conv$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conv)]
    )

    # 注册 Handlers
    app.add_handler(CommandHandler("start", start))
    
    # 优先注册对话 Handler
    app.add_handler(task_conv)
    app.add_handler(admin_add_conv)
    app.add_handler(admin_del_conv)
    
    # 注册普通按钮 Handler
    app.add_handler(CallbackQueryHandler(my_info, pattern='^btn_my_info$'))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern='^btn_admin_panel$'))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern='^admin_view_stats$'))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern='^back_to_main$'))
    app.add_handler(CallbackQueryHandler(task_button_callback, pattern='^(verify_done|cancel_task_button)$'))
    
    print("🤖 Bot 已启动 (全按钮交互版)...")
    app.run_polling()

if __name__ == '__main__':
    main()
