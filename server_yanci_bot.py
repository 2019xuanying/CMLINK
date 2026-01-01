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
    "send_verify": "https://www.yanci.com.tw/sendvcurl", # 后续需拼接ID
    "login": "https://www.yanci.com.tw/login",
    "update": "https://www.yanci.com.tw/updateopt",
    "order": "https://www.yanci.com.tw/gives"
}

# 伪装浏览器 Header
HEADERS_BASE = {
    'Host': 'www.yanci.com.tw',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://www.yanci.com.tw',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

# ================= 逻辑工具类 =================

class YanciBotLogic:
    """封装核心业务逻辑，确保 Session 和状态管理清晰"""
    
    @staticmethod
    def generate_taiwan_phone():
        return f"09{random.randint(10000000, 99999999)}"

    @staticmethod
    def generate_random_name():
        """生成随机姓名（包含中文和英文，增加随机性）"""
        # 30% 概率生成英文名，70% 概率生成中文名
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
        # 台湾主要县市及其常用行政区与邮编
        locations = [
            {"city": "臺北市", "area": "信義區", "zip": "110"},
            {"city": "臺北市", "area": "大安區", "zip": "106"},
            {"city": "臺北市", "area": "中山區", "zip": "104"},
            {"city": "新北市", "area": "板橋區", "zip": "220"},
            {"city": "新北市", "area": "中和區", "zip": "235"},
            {"city": "新北市", "area": "新莊區", "zip": "242"},
            {"city": "桃園市", "area": "桃園區", "zip": "330"},
            {"city": "桃園市", "area": "中壢區", "zip": "320"},
            {"city": "臺中市", "area": "西屯區", "zip": "407"},
            {"city": "臺中市", "area": "北屯區", "zip": "406"},
            {"city": "臺南市", "area": "東區", "zip": "701"},
            {"city": "臺南市", "area": "永康區", "zip": "710"},
            {"city": "高雄市", "area": "左營區", "zip": "813"},
            {"city": "高雄市", "area": "三民區", "zip": "807"},
        ]
        
        # 常见路名库
        roads = ["中正路", "中山路", "中華路", "建國路", "復興路", "三民路", "民生路", "信義路", "和平路", "成功路", "文化路", "民族路"]
        
        loc = random.choice(locations)
        road = random.choice(roads)
        section = f"{random.randint(1, 5)}段" if random.random() > 0.5 else "" # 50%概率有段号
        no = f"{random.randint(1, 500)}號"
        floor = f"{random.randint(2, 20)}樓" if random.random() > 0.3 else "" # 70%概率有楼层
        
        full_addr = f"{road}{section}{no}{floor}"
        
        return {
            "city": loc["city"],
            "area": loc["area"],
            "zip": loc["zip"],
            "addr": full_addr
        }

    @staticmethod
    def extract_id(text_or_url):
        """从 URL 或 HTML 文本中提取 ID (vc=Y&xxxxx)"""
        # 匹配 URL 参数形式: &12345 或 ?12345
        match_url = re.search(r'[&?](\d{5})(?:$|&)', text_or_url)
        if match_url:
            return match_url.group(1)
        
        # 匹配 HTML 中的特定模式 vc=Y&12345
        match_html = re.search(r'vc=Y(?:&amp;|&)(\d{5})', text_or_url)
        if match_html:
            return match_html.group(1)
            
        return None

    @staticmethod
    def get_initial_session():
        """初始化会话并获取第一个 ID"""
        session = requests.Session()
        session.headers.update(HEADERS_BASE)
        
        try:
            logger.info("正在访问入口页面获取初始 ID...")
            resp = session.get(URLS['entry'] + "?lg=tw", timeout=15, allow_redirects=True)
            
            # 1. 尝试从最终 URL 获取
            found_id = YanciBotLogic.extract_id(resp.url)
            
            # 2. 尝试从 HTML 内容获取
            if not found_id:
                found_id = YanciBotLogic.extract_id(resp.text)
            
            if found_id:
                logger.info(f"成功获取 ID: {found_id}")
                return session, found_id, "成功"
            else:
                # 备用：生成随机 ID (虽然这步成功率低，但好过没有)
                random_id = str(random.randint(20000, 30000))
                logger.warning(f"未找到 ID，使用随机 ID: {random_id}")
                return session, random_id, "随机生成"
                
        except Exception as e:
            logger.error(f"初始化连接失败: {e}")
            return None, None, f"网络错误: {str(e)}"

    @staticmethod
    def register_loop(session, email, phone, start_id):
        """核心注册循环：支持 ID 自动纠错重试"""
        current_id = start_id
        max_retries = 3
        
        for attempt in range(max_retries):
            logger.info(f"注册尝试 {attempt+1}/{max_retries} (ID: {current_id}) -> {email}")
            
            # 构造注册 Payload
            payload = {
                'userMode': 'normal',
                'userACC': email,
                'userPWD': FIXED_PASSWORD,
                'userPhn': phone,
                'userChk': 'true',  # 关键参数
                'userPage': ''
            }
            
            # 这里的 Referer 必须带上当前的 ID
            headers = HEADERS_BASE.copy()
            headers['Referer'] = f"{URLS['entry']}?lg=tw&vc=Y&{current_id}"
            
            try:
                resp = session.post(URLS['register'], headers=headers, data=payload, timeout=20)
                resp.encoding = 'utf-8'
                
                # 情况 A: 成功 (通常是 JSON 格式，或者状态码 200 且无 HTML 错误页)
                # 注意：有些服务器成功时不返回 JSON，而是空或者特定文本，这里主要通过是否包含错误特征来判断
                
                # 检查 JSON 错误返回
                try:
                    res_json = resp.json()
                    if isinstance(res_json, list) and len(res_json) > 0:
                        code = res_json[0].get('code')
                        msg = res_json[0].get('msg', '')
                        if code == '400':
                            if "唯一" in msg or "重複" in msg or "重复" in msg:
                                return True, current_id, "账号已存在(视为成功)"
                            return False, current_id, f"服务器拒绝: {msg}"
                except ValueError:
                    # 不是 JSON，可能是 HTML
                    pass

                # 情况 B: 失败，返回了 HTML 页面 (通常意味着 ID 不对，服务器重定向回注册页)
                if "<!DOCTYPE html>" in resp.text or "vc=Y" in resp.text:
                    # 尝试从返回的 HTML 中提取新的正确 ID
                    new_id = YanciBotLogic.extract_id(resp.text)
                    if not new_id:
                        # 看看 URL 有没有变
                        new_id = YanciBotLogic.extract_id(resp.url)
                        
                    if new_id and new_id != current_id:
                        logger.info(f"检测到 ID 变更 (旧: {current_id} -> 新: {new_id})，准备重试...")
                        current_id = new_id
                        time.sleep(1) # 稍作休息
                        continue # 进入下一次循环重试
                    else:
                        return False, current_id, "注册被拒绝且无法获取新ID"

                # 如果状态码 200 且没有明显的错误特征，我们假设成功
                if resp.status_code == 200:
                    return True, current_id, "注册请求已发送"
                
                return False, current_id, f"HTTP状态异常: {resp.status_code}"

            except Exception as e:
                logger.error(f"注册请求异常: {e}")
                return False, current_id, f"请求异常: {str(e)}"
        
        return False, current_id, "超过最大重试次数"

    @staticmethod
    def send_verify_email(session, verify_id):
        """发送验证邮件"""
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
        """登录"""
        headers = HEADERS_BASE.copy()
        headers['Referer'] = URLS['login']
        headers['X-Requested-With'] = 'XMLHttpRequest'
        
        payload = {
            'userMode': 'normal',
            'userACC': email,
            'userPWD': FIXED_PASSWORD,
            'userRem': 'true',
            'userPage': ''
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
        """更新个人资料（使用随机生成的数据）"""
        # 生成随机数据
        name = YanciBotLogic.generate_random_name()
        addr_data = YanciBotLogic.generate_random_address()
        sex = '男性' if random.random() > 0.5 else '女性' # 随机性别
        
        headers = HEADERS_BASE.copy()
        headers['Referer'] = 'https://www.yanci.com.tw/member_edit'
        headers['X-Requested-With'] = 'XMLHttpRequest'
        
        payload = {
            'userName': name,
            'userSex': sex,
            'userPhn': phone,
            'userTel': phone,
            'userZip': addr_data['zip'],
            'userCity': addr_data['city'],
            'userArea': addr_data['area'],
            'userAddr': addr_data['addr']
        }
        
        logger.info(f"正在更新资料: {name} | {addr_data['city']}{addr_data['area']}{addr_data['addr']}")
        
        try:
            resp = session.post(URLS['update'], headers=headers, data=payload, timeout=20)
            return resp.status_code == 200, name
        except:
            return False, name

    @staticmethod
    def place_order(session):
        """下单"""
        headers = HEADERS_BASE.copy()
        headers['Referer'] = 'https://www.yanci.com.tw/product_give'
        headers['X-Requested-With'] = 'XMLHttpRequest'
        
        payload = {'given': PRODUCT_ID, 'giveq': '1'}
        try:
            resp = session.post(URLS['order'], headers=headers, data=payload, timeout=20)
            resp.encoding = 'utf-8'
            
            # 判断逻辑：如果被重定向回 login 或 title 包含登录，说明 Session 失效
            if "login" in resp.url or "會員登入" in resp.text:
                return False, "登录失效，无法下单"
            
            if resp.status_code == 200:
                return True, "下单请求发送成功"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

# ================= Telegram Bot Handlers =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Yanci 自动助手 (V12.2 资料随机化版)**\n\n"
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

        # 1. 获取 ID 和 Session
        # FIX: 使用 asyncio.get_running_loop() 替代 context.application.loop
        session, verify_id, init_msg = await asyncio.get_running_loop().run_in_executor(None, YanciBotLogic.get_initial_session)
        
        if not session or not verify_id:
            await msg.edit_text(f"❌ 初始化失败: {init_msg}")
            return
            
        # 保存到 context，供后续步骤使用
        context.user_data['session'] = session
        context.user_data['email'] = email
        context.user_data['phone'] = phone
        
        await msg.edit_text(f"✅ 获取 ID: {verify_id}\n⏳ 正在执行智能注册 (可能需要尝试多次)...")

        # 2. 执行注册循环
        # FIX: 使用 asyncio.get_running_loop() 替代 context.application.loop
        reg_success, final_id, reg_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.register_loop, session, email, phone, verify_id
        )
        
        if not reg_success:
            await msg.edit_text(f"❌ 注册失败: {reg_msg}")
            return

        # 更新最终使用的 ID (可能在注册过程中变了)
        context.user_data['verify_id'] = final_id
        
        # 3. 发送验证信
        await msg.edit_text(f"✅ 注册通过 (最终ID: {final_id})\n⏳ 正在申请验证邮件...")
        
        # FIX: 使用 asyncio.get_running_loop() 替代 context.application.loop
        send_success, send_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.send_verify_email, session, final_id
        )
        
        if not send_success:
            await msg.edit_text(f"❌ 发信失败: {send_msg}")
            return

        # 4. 展示交互按钮
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

        # 1. 登录
        # FIX: 使用 asyncio.get_running_loop() 替代 context.application.loop
        login_success, login_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.login, session, email
        )
        if not login_success:
            await query.edit_message_text(f"❌ {login_msg}\n(如果刚验证完，请稍等几秒再试，或检查是否真验证成功)")
            return

        # 2. 完善资料
        await query.edit_message_text("✅ 登录成功，正在生成并完善随机资料...")
        # FIX: 使用 asyncio.get_running_loop() 替代 context.application.loop
        update_success, name = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.update_profile, session, phone
        )
        
        if not update_success:
            await query.edit_message_text("❌ 资料保存失败，停止下单。")
            return

        # 3. 下单
        await query.edit_message_text(f"✅ 资料已保存 (姓名: {name})\n⏳ 正在尝试下单...")
        # FIX: 使用 asyncio.get_running_loop() 替代 context.application.loop
        order_success, order_msg = await asyncio.get_running_loop().run_in_executor(
            None, YanciBotLogic.place_order, session
        )
        
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
