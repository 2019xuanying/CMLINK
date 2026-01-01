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
# from bs4 import BeautifulSoup  <-- 已移除此行，避免报错
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# ================= 环境配置 =================
load_dotenv()

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
# 如果本地测试没有 .env，可以在这里填入 token（生产环境请勿填写）
# BOT_TOKEN = "YOUR_TOKEN_HERE"

if not BOT_TOKEN:
    print("❌ 错误：未找到 TG_BOT_TOKEN。请检查环境变量或 .env 文件。")
    sys.exit(1)

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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

# [关键修复]：严格对齐 yanci_final_v4.py 的 Headers
# 移除了 'Upgrade-Insecure-Requests'，防止 AJAX 请求被识别为页面访问
HEADERS_BASE = {
    'Host': 'www.yanci.com.tw',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://www.yanci.com.tw',
}

# ================= 逻辑工具类 =================

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

    @staticmethod
    def get_initial_session():
        session = requests.Session()
        session.headers.update(HEADERS_BASE)
        try:
            # 这里的 get 需要 allow_redirects=True 才能获取到跳转后的 ID
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
                
                # 检查 JSON 错误
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

                # HTML 错误 / ID 纠错
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
        # [关键修复] 严格对齐 yanci_final_v4.py 的 Accept，模拟 jQuery
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
        # 注意：这里保持默认 Accept 即可，原代码就是 copy()
        
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

        # [关键修复] 完全移除多余的预访问，直接对齐原代码逻辑
        # headers 严格对齐原代码
        headers = HEADERS_BASE.copy()
        headers['Referer'] = 'https://www.yanci.com.tw/product_give'
        headers['X-Requested-With'] = 'XMLHttpRequest'
        
        # 确保没有 Upgrade-Insecure-Requests (虽然 HEADERS_BASE 已经移除了，这里双重保险)
        if 'Upgrade-Insecure-Requests' in headers:
            del headers['Upgrade-Insecure-Requests']

        payload = {'given': PRODUCT_ID, 'giveq': '1'}
        try:
            resp = session.post(URLS['order'], headers=headers, data=payload, timeout=20)
            resp.encoding = 'utf-8'
            
            logger.info(f"下单接口返回: Status={resp.status_code} | Body Len={len(resp.text)}")

            # 1. 优先尝试解析 JSON (成功情况)
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
                pass # 不是 JSON，继续往下

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
                    
                    return False, f"服务器返回页面: {page_title} (可能是: {page_text})"
                
                return True, "请求发送成功 (未返回错误)"
                
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

# ================= Telegram Bot Handlers =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Yanci 自动助手 (V12.6 自动重连版)**\n\n"
        "指令列表：\n"
        "`/new <邮箱>` - 开始新任务 (自动注册->发信)\n\n"
        "示例：`/new test@example.com`",
        parse_mode='Markdown'
    )

async def new_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ 请输入邮箱，例如：\n`/new abc@gmail.com`")
            return

        email = context.args[0]
        phone = YanciBotLogic.generate_taiwan_phone()
        
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
    await query.answer()

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

        # [新增] 自动重试机制：如果是因为登录失效，则尝试重新登录一次
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
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("🤖 Bot 已启动...")
    application.run_polling()
