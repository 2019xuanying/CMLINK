import logging
import requests
import re
import random
import time
import json
import os
import sys
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# ================= 环境配置 =================
# 加载 .env 文件中的环境变量
load_dotenv()

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ 错误：未找到 TG_BOT_TOKEN 环境变量。请检查 .env 文件。")
    sys.exit(1)

# 配置日志 (输出到控制台，Systemd 会自动收集)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= 固定数据区 =================
FIXED_PASSWORD = "Pass1234"
FIXED_NAME = "測試人員"
FIXED_ADDRESS = {
    "city": "臺東縣",
    "area": "蘭嶼鄉",
    "addr": "電子信箱電子信箱",
    "zip": "952"
}
PRODUCT_ID = '974'

URLS = {
    "entry": "https://www.yanci.com.tw/register",
    "register": "https://www.yanci.com.tw/storeregd",
    "login": "https://www.yanci.com.tw/login",
    "update": "https://www.yanci.com.tw/updateopt",
    "order": "https://www.yanci.com.tw/gives"
}

# 基础 Headers
HEADERS_BASE = {
    'Host': 'www.yanci.com.tw',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://www.yanci.com.tw',
}

# ================= 业务逻辑核心 =================

def generate_taiwan_phone():
    return f"09{random.randint(10000000, 99999999)}"

def extract_id_from_html(html):
    match = re.search(r'vc=Y(?:&amp;|&)(\d{5})', html)
    if match: return match.group(1)
    match_b = re.search(r'vc=Y\D{0,10}(\d{5})', html)
    if match_b: return match_b.group(1)
    return None

def core_get_session_id(session):
    try:
        logger.info("正在获取会话 ID...")
        response = session.get(URLS['entry'], headers=HEADERS_BASE, allow_redirects=True, timeout=15)
        match_url = re.search(r'[&?](\d{5})$', response.url)
        if match_url:
            return match_url.group(1), "URL捕获"
        
        real_id = extract_id_from_html(response.text)
        if real_id:
            return real_id, "源码捕获"
            
        random_id = str(random.randint(20000, 30000))
        return random_id, "随机生成"
    except Exception as e:
        logger.error(f"获取会话失败: {e}")
        return None, str(e)

def core_register(session, email, phone, verify_id):
    headers = HEADERS_BASE.copy()
    headers['Referer'] = f"{URLS['entry']}?lg=tw&vc=Y&{verify_id}"
    
    payload = {
        'userMode': 'normal', 'userACC': email, 'userPWD': FIXED_PASSWORD,
        'userPhn': phone, 'userChk': 'true', 'userPage': ''
    }

    try:
        logger.info(f"提交注册: {email}")
        response = session.post(URLS['register'], headers=headers, data=payload)
        response.encoding = 'utf-8'
        
        if response.text.strip().startswith("<!DOCTYPE html>"):
            correct_id = extract_id_from_html(response.text)
            if correct_id and correct_id != verify_id:
                logger.info(f"ID失效，自愈重试: {correct_id}")
                retry_res, new_id, msg = core_register_retry(session, email, phone, correct_id)
                return retry_res, new_id, f"自愈重试({msg})"
            return False, verify_id, "注册被弹回且无法获取ID"

        try:
            res_json = response.json()
            if isinstance(res_json, list) and res_json[0].get('code') == '400':
                msg = res_json[0].get('msg', '')
                if "唯一" in msg or "重複" in msg or "重复" in msg:
                    return True, verify_id, "账号已存在(跳过)"
                return False, verify_id, f"服务器错误: {msg}"
        except:
            pass

        return True, verify_id, "注册成功"
    except Exception as e:
        return False, verify_id, str(e)

def core_register_retry(session, email, phone, correct_id):
    headers = HEADERS_BASE.copy()
    headers['Referer'] = f"{URLS['entry']}?lg=tw&vc=Y&{correct_id}"
    payload = {
        'userMode': 'normal', 'userACC': email, 'userPWD': FIXED_PASSWORD,
        'userPhn': phone, 'userChk': 'true', 'userPage': ''
    }
    try:
        response = session.post(URLS['register'], headers=headers, data=payload)
        response.encoding = 'utf-8'
        if "code" in response.text and "400" in response.text:
             if "唯一" in response.text or "重複" in response.text:
                 return True, correct_id, "账号已存在"
             return False, correct_id, "重试失败"
        return True, correct_id, "重试成功"
    except:
        return False, correct_id, "重试异常"

def core_send_verify(session, verify_id):
    url = f"https://www.yanci.com.tw/sendvcurl{verify_id}"
    headers = HEADERS_BASE.copy()
    headers['Accept'] = 'application/json, text/plain, */*'
    headers['Referer'] = f"{URLS['entry']}?lg=tw&vc=Y&{verify_id}"
    
    try:
        logger.info(f"发送验证信 ID: {verify_id}")
        time.sleep(1.5)
        res = session.post(url, headers=headers, data='Y')
        if res.status_code == 200 and "400" not in res.text:
            return True, "发送成功"
        return False, f"发送失败(Status: {res.status_code})"
    except Exception as e:
        return False, str(e)

def core_login(session, email):
    headers = HEADERS_BASE.copy()
    headers['Accept'] = 'application/json, text/javascript, */*; q=0.01'
    headers['X-Requested-With'] = 'XMLHttpRequest'
    headers['Referer'] = URLS['login']
    
    payload = {
        'userMode': 'normal', 'userACC': email, 'userPWD': FIXED_PASSWORD, 
        'userRem': 'true', 'userPage': ''
    }
    try:
        logger.info(f"尝试登录: {email}")
        res = session.post(URLS['login'], headers=headers, data=payload)
        if res.status_code == 200 and "alert" not in res.text:
            return True, "登录成功"
        return False, "登录失败"
    except Exception as e:
        return False, str(e)

def core_update_profile(session, name, phone):
    headers = HEADERS_BASE.copy()
    headers['X-Requested-With'] = 'XMLHttpRequest'
    headers['Referer'] = 'https://www.yanci.com.tw/member_edit'
    
    payload = {
        'userName': name, 'userSex': '男性', 'userPhn': phone, 'userTel': phone,
        'userZip': FIXED_ADDRESS['zip'], 'userCity': FIXED_ADDRESS['city'],
        'userArea': FIXED_ADDRESS['area'], 'userAddr': FIXED_ADDRESS['addr']
    }
    try:
        res = session.post(URLS['update'], headers=headers, data=payload)
        return res.status_code == 200
    except:
        return False

def core_place_order(session):
    headers = HEADERS_BASE.copy()
    headers['X-Requested-With'] = 'XMLHttpRequest'
    headers['Referer'] = 'https://www.yanci.com.tw/product_give'
    
    payload = {'given': PRODUCT_ID, 'giveq': '1'}
    try:
        logger.info("提交订单...")
        res = session.post(URLS['order'], headers=headers, data=payload)
        res.encoding = 'utf-8'
        if res.status_code == 200:
            if "login" in res.text or "<title>" in res.text:
                return False, "登录失效"
            return True, "请求发送成功"
        return False, f"HTTP {res.status_code}"
    except Exception as e:
        return False, str(e)

# ================= 机器人 Handler =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 欢迎使用扬奇抢单助手！\n\n"
        "请发送 `/new 邮箱地址` 开始一个新的任务。\n"
        "例如：`/new test@zenvex.edu.pl`"
    )

async def new_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ 请输入邮箱，例如：\n`/new abc@gmail.com`")
        return

    email = context.args[0]
    phone = generate_taiwan_phone()
    
    msg = await update.message.reply_text(f"🚀 开始处理：{email}\n📱 生成手机：{phone}\n⏳ 正在初始化...")

    session = requests.Session()
    context.user_data['session'] = session 
    context.user_data['email'] = email
    context.user_data['phone'] = phone

    verify_id, id_source = await context.application.loop.run_in_executor(None, core_get_session_id, session)
    
    if not verify_id:
        await msg.edit_text(f"❌ 初始化失败：{id_source}")
        return
        
    await msg.edit_text(f"✅ 初始化成功 (ID: {verify_id})\n⏳ 正在注册...")

    reg_success, final_id, reg_msg = await context.application.loop.run_in_executor(None, core_register, session, email, phone, verify_id)
    context.user_data['verify_id'] = final_id
    
    if not reg_success:
        await msg.edit_text(f"❌ 注册失败：{reg_msg}")
        return

    await msg.edit_text(f"✅ {reg_msg}\n⏳ 正在申请验证信...")
    
    send_success, send_msg = await context.application.loop.run_in_executor(None, core_send_verify, session, final_id)
    
    if not send_success:
        await msg.edit_text(f"❌ 发信失败：{send_msg}")
        return

    keyboard = [
        [InlineKeyboardButton("✅ 我已在邮箱完成验证", callback_data="verify_done")],
        [InlineKeyboardButton("❌ 取消任务", callback_data="cancel_task")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await msg.edit_text(
        f"📩 **验证信已发送！**\n\n"
        f"1. 请前往邮箱 `{email}`\n"
        f"2. 点击邮件中的验证链接\n"
        f"3. 验证成功后，点击下方按钮继续。",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_task":
        await query.edit_message_text("🚫 任务已取消。")
        return

    if query.data == "verify_done":
        session = context.user_data.get('session')
        email = context.user_data.get('email')
        phone = context.user_data.get('phone')
        
        if not session:
            await query.edit_message_text("❌ 会话已过期，请重新开始。")
            return

        await query.edit_message_text("⏳ 正在登录并执行后续操作...")

        login_success, login_msg = await context.application.loop.run_in_executor(None, core_login, session, email)
        if not login_success:
            await query.edit_message_text(f"❌ {login_msg}")
            return
            
        update_res = await context.application.loop.run_in_executor(None, core_update_profile, session, FIXED_NAME, phone)
        await query.edit_message_text("✅ 登录成功\n✅ 资料已保存\n⏳ 正在下单...")
        
        order_success, order_msg = await context.application.loop.run_in_executor(None, core_place_order, session)
        
        if order_success:
             await query.edit_message_text(
                 f"🎉 **任务完成！**\n\n"
                 f"📧 账号: `{email}`\n"
                 f"✅ 状态: 下单请求已发送\n"
                 f"请登录网页确认订单。",
                 parse_mode='Markdown'
             )
        else:
             await query.edit_message_text(f"❌ 下单失败: {order_msg}")

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_task))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("Bot is running...")
    application.run_polling()
