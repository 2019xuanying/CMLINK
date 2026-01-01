import logging
import requests
import re
import random
import time
import json
import os
import sys
import traceback
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# ================= 环境配置 =================
load_dotenv()

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
# 允许手动填入 Token 方便调试（如果 .env 读取失败）
if not BOT_TOKEN:
    # 你可以在这里临时填入 Token 进行测试，但生产环境建议用 .env
    BOT_TOKEN = "" 

if not BOT_TOKEN:
    print("❌ 错误：未找到 TG_BOT_TOKEN。")
    sys.exit(1)

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= 固定数据区 =================
FIXED_PASSWORD = "Pass1234"
# FIXED_NAME 已移除，改为动态随机生成
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

def generate_random_name():
    """随机生成中文或英文姓名"""
    if random.choice([True, False]):
        # 生成英文名
        first_names = ["James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles", "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan", "Jessica", "Sarah", "Karen", "Lisa", "Nancy", "Betty", "Helen", "Sandra"]
        last_names = ["Smith", "Johnson", "Williams", "Jones", "Brown", "Davis", "Miller", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin", "Thompson", "Garcia", "Martinez", "Robinson"]
        return f"{random.choice(first_names)} {random.choice(last_names)}"
    else:
        # 生成中文名
        last_names = ["李", "王", "張", "劉", "陳", "楊", "趙", "黃", "周", "吳", "徐", "孫", "胡", "朱", "高", "林", "何", "郭", "馬", "羅", "梁", "宋", "鄭", "謝", "韓"]
        chars = "明國華建文平志偉東海強曉亮信生光福春芬芳燕紅蘭鳳潔梅秀英娜雅婷怡君志明宗翰家豪冠宇"
        first_name = "".join(random.choices(chars, k=random.choice([1, 2])))
        return f"{random.choice(last_names)}{first_name}"

def extract_id_from_html(html):
    try:
        match = re.search(r'vc=Y(?:&amp;|&)(\d{5})', html)
        if match: return match.group(1)
        match_b = re.search(r'vc=Y\D{0,10}(\d{5})', html)
        if match_b: return match_b.group(1)
    except:
        pass
    return None

def core_get_session_id(session):
    try:
        logger.info("正在连接网站获取 ID...")
        # 增加 headers，模拟真实请求
        response = session.get(URLS['entry'], headers=HEADERS_BASE, allow_redirects=True, timeout=20)
        
        # 打印状态码调试
        logger.info(f"网站响应状态码: {response.status_code}")
        
        match_url = re.search(r'[&?](\d{5})$', response.url)
        if match_url:
            return match_url.group(1), "URL捕获"
        
        real_id = extract_id_from_html(response.text)
        if real_id:
            return real_id, "源码捕获"
            
        random_id = str(random.randint(20000, 30000))
        return random_id, "随机生成(备用)"
    except Exception as e:
        logger.error(f"获取会话异常: {e}")
        # 返回详细错误信息
        return None, f"连接错误: {str(e)}"

def core_register(session, email, phone, verify_id):
    headers = HEADERS_BASE.copy()
    headers['Referer'] = f"{URLS['entry']}?lg=tw&vc=Y&{verify_id}"
    
    payload = {
        'userMode': 'normal', 'userACC': email, 'userPWD': FIXED_PASSWORD,
        'userPhn': phone, 'userChk': 'true', 'userPage': ''
    }

    try:
        logger.info(f"提交注册: {email} (ID: {verify_id})")
        response = session.post(URLS['register'], headers=headers, data=payload, timeout=20)
        response.encoding = 'utf-8'
        
        # 处理被弹回HTML的情况（ID自愈）
        if response.text.strip().startswith("<!DOCTYPE html>"):
            correct_id = extract_id_from_html(response.text)
            if correct_id and correct_id != verify_id:
                logger.info(f"ID失效，尝试自愈重试: {correct_id}")
                return core_register_retry(session, email, phone, correct_id)
            return False, verify_id, "注册请求被拒绝(HTML)"

        # 检查JSON错误
        try:
            res_json = response.json()
            if isinstance(res_json, list) and len(res_json) > 0:
                res_obj = res_json[0]
                if res_obj.get('code') == '400':
                    msg = res_obj.get('msg', '')
                    if "唯一" in msg or "重複" in msg or "重复" in msg:
                        return True, verify_id, "账号已存在(自动跳过)"
                    return False, verify_id, f"服务器返回错误: {msg}"
        except:
            pass

        if response.status_code == 200:
            return True, verify_id, "注册成功"
        return False, verify_id, f"HTTP状态码: {response.status_code}"

    except Exception as e:
        logger.error(f"注册异常: {e}")
        return False, verify_id, f"注册异常: {str(e)}"

def core_register_retry(session, email, phone, correct_id):
    headers = HEADERS_BASE.copy()
    headers['Referer'] = f"{URLS['entry']}?lg=tw&vc=Y&{correct_id}"
    payload = {
        'userMode': 'normal', 'userACC': email, 'userPWD': FIXED_PASSWORD,
        'userPhn': phone, 'userChk': 'true', 'userPage': ''
    }
    try:
        response = session.post(URLS['register'], headers=headers, data=payload, timeout=20)
        response.encoding = 'utf-8'
        if "code" in response.text and "400" in response.text:
             if "唯一" in response.text or "重複" in response.text:
                 return True, correct_id, "账号已存在(重试检测)"
             return False, correct_id, "重试失败"
        return True, correct_id, "重试成功"
    except Exception as e:
        return False, correct_id, f"重试异常: {str(e)}"

def core_send_verify(session, verify_id):
    url = f"https://www.yanci.com.tw/sendvcurl{verify_id}"
    headers = HEADERS_BASE.copy()
    headers['Accept'] = 'application/json, text/plain, */*'
    headers['Referer'] = f"{URLS['entry']}?lg=tw&vc=Y&{verify_id}"
    
    try:
        time.sleep(2)
        res = session.post(url, headers=headers, data='Y', timeout=20)
        if res.status_code == 200 and "400" not in res.text:
            return True, "发送成功"
        return False, f"发送失败(Code {res.status_code})"
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
        res = session.post(URLS['login'], headers=headers, data=payload, timeout=20)
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
        res = session.post(URLS['update'], headers=headers, data=payload, timeout=20)
        return res.status_code == 200
    except:
        return False

def core_place_order(session):
    headers = HEADERS_BASE.copy()
    headers['X-Requested-With'] = 'XMLHttpRequest'
    headers['Referer'] = 'https://www.yanci.com.tw/product_give'
    
    payload = {'given': PRODUCT_ID, 'giveq': '1'}
    try:
        res = session.post(URLS['order'], headers=headers, data=payload, timeout=20)
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
        "👋 欢迎使用扬奇抢单助手 V12.1 (增强版)！\n\n"
        "请发送 `/new 邮箱地址` 开始任务。\n"
        "例如：`/new test@zenvex.edu.pl`"
    )

async def new_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 增加全局 try-except，防止任何未捕获的错误导致机器人无反应
    try:
        if not context.args:
            await update.message.reply_text("❌ 请输入邮箱，例如：\n`/new abc@gmail.com`")
            return

        email = context.args[0]
        phone = generate_taiwan_phone()
        
        msg = await update.message.reply_text(f"🚀 开始处理：{email}\n📱 模拟手机：{phone}\n⏳ 正在初始化...")

        # 1. 创建 Session
        session = requests.Session()
        context.user_data['session'] = session 
        context.user_data['email'] = email
        context.user_data['phone'] = phone

        # 2. 获取 ID (后台运行)
        logger.info(f"User {update.effective_user.id} requested ID fetch.")
        verify_id, id_source = await context.application.loop.run_in_executor(None, core_get_session_id, session)
        
        if not verify_id:
            # 这里捕获到了初始化失败的具体原因
            await msg.edit_text(f"❌ 初始化失败：{id_source}\n(请检查服务器网络是否能访问目标网站)")
            return
            
        await msg.edit_text(f"✅ 初始化成功 (ID: {verify_id})\n⏳ 正在注册...")

        # 3. 注册
        reg_success, final_id, reg_msg = await context.application.loop.run_in_executor(None, core_register, session, email, phone, verify_id)
        context.user_data['verify_id'] = final_id
        
        if not reg_success:
            await msg.edit_text(f"❌ 注册失败：{reg_msg}")
            return

        await msg.edit_text(f"✅ {reg_msg}\n⏳ 正在申请验证信...")
        
        # 4. 发信
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
    except Exception as e:
        logger.error(f"严重错误: {traceback.format_exc()}")
        await update.message.reply_text(f"💥 机器人发生内部错误: {str(e)}\n请检查服务器日志。")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        if query.data == "cancel_task":
            await query.edit_message_text("🚫 任务已取消。")
            return

        if query.data == "verify_done":
            session = context.user_data.get('session')
            email = context.user_data.get('email')
            phone = context.user_data.get('phone')
            
            if not session:
                await query.edit_message_text("❌ 会话已过期，请重新发送 /new 命令。")
                return

            await query.edit_message_text("⏳ 正在登录并执行后续操作...")

            login_success, login_msg = await context.application.loop.run_in_executor(None, core_login, session, email)
            if not login_success:
                await query.edit_message_text(f"❌ {login_msg}")
                return
                
            # 生成随机姓名
            random_name = generate_random_name()
            await context.application.loop.run_in_executor(None, core_update_profile, session, random_name, phone)
            
            await query.edit_message_text(f"✅ 登录成功\n✅ 资料已保存 (姓名: {random_name})\n⏳ 正在下单...")
            
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
    except Exception as e:
        logger.error(f"回调错误: {traceback.format_exc()}")
        await query.edit_message_text(f"💥 处理时发生错误: {str(e)}")

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_task))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("Bot is running...")
    application.run_polling()
