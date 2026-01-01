import requests
import random
import time
import sys
import re
import json

# ================= 核心配置区 (固定数据) =================
FIXED_PASSWORD = "Pass1234"  
FIXED_NAME = "測試人員"                   
FIXED_ADDRESS = {                         
    "city": "臺東縣",
    "area": "蘭嶼鄉",
    "addr": "電子信箱電子信箱",
    "zip": "952"
}
PRODUCT_ID = '974'                        

# ================= URL 配置 =================
URLS = {
    "entry": "https://www.yanci.com.tw/register",       
    "register": "https://www.yanci.com.tw/storeregd",   
    "login": "https://www.yanci.com.tw/login",          
    "update": "https://www.yanci.com.tw/updateopt",     
    "order": "https://www.yanci.com.tw/gives"           
}

# 全局 Session
session = requests.Session()

# 基础 Headers
HEADERS = {
    'Host': 'www.yanci.com.tw',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://www.yanci.com.tw',
}

# ================= 工具函数 =================
def generate_taiwan_phone():
    return f"09{random.randint(10000000, 99999999)}"

def extract_id_from_html(html):
    """从 HTML 源码中提取 5 位数字 ID"""
    match = re.search(r'vc=Y(?:&amp;|&)(\d{5})', html)
    if match:
        return match.group(1)
    match_b = re.search(r'vc=Y\D{0,10}(\d{5})', html)
    if match_b:
        return match_b.group(1)
    return None

def get_server_session_and_id():
    """获取初始 ID"""
    print("   [系统] 正在连接服务器获取会话 ID...")
    try:
        response = session.get(URLS['entry'], headers=HEADERS, allow_redirects=True, timeout=15)
        
        match_url = re.search(r'[&?](\d{5})$', response.url)
        if match_url:
            real_id = match_url.group(1)
            print(f"   [成功] 从 URL 获取 ID: {real_id}")
            return real_id
            
        real_id = extract_id_from_html(response.text)
        if real_id:
            print(f"   [成功] 从源码捕获真实 ID: {real_id}")
            return real_id
            
        print("   [警告] 未发现 ID，使用随机生成...")
        return str(random.randint(20000, 30000))
            
    except Exception as e:
        print(f"   [错误] 获取会话失败: {e}")
        sys.exit()

# ================= 流程函数 =================

def register_request(email, phone, verify_id):
    """发送注册请求的底层函数"""
    current_referer = f'https://www.yanci.com.tw/register?lg=tw&vc=Y&{verify_id}'
    headers = HEADERS.copy()
    headers['Referer'] = current_referer
    
    payload = {
        'userMode': 'normal',
        'userACC': email,
        'userPWD': FIXED_PASSWORD,
        'userPhn': phone,
        'userChk': 'true',
        'userPage': ''
    }
    
    return session.post(URLS['register'], headers=headers, data=payload)

def step1_register(email, phone, verify_id):
    print(f"\n[1/6] 正在提交注册信息 (ID: {verify_id})...")
    
    try:
        response = register_request(email, phone, verify_id)
        response.encoding = 'utf-8'
        
        if response.text.strip().startswith("<!DOCTYPE html>"):
            print("   ⚠️ 警告：注册被服务器弹回 (ID可能无效)，正在尝试从返回页面获取正确ID...")
            
            correct_id = extract_id_from_html(response.text)
            
            if correct_id and correct_id != verify_id:
                print(f"   ✅ 发现正确 ID: {correct_id}，正在自动重试注册...")
                
                global GLOBAL_VERIFY_ID 
                GLOBAL_VERIFY_ID = correct_id
                
                retry_response = register_request(email, phone, correct_id)
                retry_response.encoding = 'utf-8'
                
                if retry_response.text.strip().startswith("<!DOCTYPE html>"):
                    print("   ❌ 重试依然失败 (返回HTML)。")
                    return False
                
                try:
                    res_json = retry_response.json()
                    if isinstance(res_json, list) and len(res_json) > 0:
                        res_data = res_json[0]
                        if res_data.get('code') == '400':
                            msg = res_data.get('msg', '')
                            if "唯一" in msg or "重複" in msg or "重复" in msg:
                                print("   💡 提示：该账号已存在，跳过注册，直接尝试后续步骤...")
                                return True
                            print(f"   ❌ 重试失败: {msg}")
                            return False
                except:
                    pass
                    
                print("   ✅ 重试成功！注册通过。")
                return True
            else:
                print("   ❌ 无法获取正确 ID，注册失败。")
                return False

        try:
            res_json = response.json()
            if isinstance(res_json, list) and len(res_json) > 0:
                res_data = res_json[0]
                if res_data.get('code') == '400':
                    msg = res_data.get('msg', '')
                    if "唯一" in msg or "重複" in msg or "重复" in msg:
                        print("   💡 提示：该账号已存在，跳过注册，直接尝试后续步骤...")
                        return True
                    print(f"   ❌ 注册失败: {msg}")
                    return False
        except:
            pass

        print("   ✅ 注册数据提交成功。")
        return True
        
    except Exception as e:
        print(f"   >>> 错误: {e}")
        return False

def step2_send_verify(verify_id):
    print(f"[2/6] 正在申请发送验证信 (ID={verify_id})...")
    
    verify_url = f"https://www.yanci.com.tw/sendvcurl{verify_id}"
    
    headers = HEADERS.copy()
    headers['Accept'] = 'application/json, text/plain, */*'
    headers['Referer'] = f'https://www.yanci.com.tw/register?lg=tw&vc=Y&{verify_id}'
    
    try:
        time.sleep(2)
        response = session.post(verify_url, headers=headers, data='Y')
        response.encoding = 'utf-8'
        
        print(f"   [调试] 发信服务器回应: {response.text}")
        
        if response.status_code == 200:
            if "400" in response.text:
                print("   ❌ 发信失败：服务器拒绝。")
                return False
            else:
                print("   ✅ 成功！服务器已接受发信请求。")
                return True
        else:
            print(f"   ❌ 失败：状态码 {response.status_code}")
            return False
    except Exception as e:
        print(f"   >>> 错误: {e}")
        return False

def step3_wait_for_user():
    print("\n" + "="*50)
    print(" 🛑  流程暂停：请去邮箱验证  🛑")
    print(" 1. 请前往邮箱查收验证信。")
    print(" 2. 点击链接完成验证。")
    print(" 3. 验证成功后，回来这里按回车。")
    print("="*50)
    input(" >>> 完成后请按 [回车键] 继续...")
    print("="*50 + "\n")

def step4_login(email):
    print(f"[4/6] 正在登录...")
    
    payload = {
        'userMode': 'normal',
        'userACC': email,
        'userPWD': FIXED_PASSWORD,
        'userRem': 'true',
        'userPage': ''
    }
    headers = HEADERS.copy()
    headers['Accept'] = 'application/json, text/javascript, */*; q=0.01'
    headers['X-Requested-With'] = 'XMLHttpRequest'
    headers['Referer'] = URLS['login']

    try:
        response = session.post(URLS['login'], headers=headers, data=payload)
        if response.status_code == 200 and "alert" not in response.text:
            print("   ✅ 登录成功。")
            return True
        else:
            print(f"   ❌ 登录失败: {response.text[:100]}")
            return False
    except:
        return False

def step5_update_profile(name, phone):
    print(f"[5/6] 正在保存地址资料...")
    payload = {
        'userName': name,
        'userSex': '男性',
        'userPhn': phone,
        'userTel': phone,
        'userZip': FIXED_ADDRESS['zip'],
        'userCity': FIXED_ADDRESS['city'],
        'userArea': FIXED_ADDRESS['area'],
        'userAddr': FIXED_ADDRESS['addr']
    }
    headers = HEADERS.copy()
    # 增加 Ajax 标识
    headers['X-Requested-With'] = 'XMLHttpRequest'
    headers['Referer'] = 'https://www.yanci.com.tw/member_edit'
    
    try:
        response = session.post(URLS['update'], headers=headers, data=payload)
        if response.status_code == 200:
            print("   ✅ 资料已保存。")
            return True
        else:
            print("   ❌ 资料保存失败。")
            return False
    except:
        return False

def step6_place_order():
    print(f"[6/6] 正在提交订单 (ID: {PRODUCT_ID})...")
    payload = {'given': PRODUCT_ID, 'giveq': '1'}
    headers = HEADERS.copy()
    # 增加 Ajax 标识 (关键修复)
    headers['X-Requested-With'] = 'XMLHttpRequest'
    headers['Referer'] = 'https://www.yanci.com.tw/product_give'

    try:
        response = session.post(URLS['order'], headers=headers, data=payload)
        response.encoding = 'utf-8'
        
        # 调试：打印详细的下单结果，看看服务器到底说了什么
        print(f"   [调试] 下单回应: {response.text[:200]}")
        
        if response.status_code == 200:
            # 放宽判断：只要没有明确跳转到 login 页面，就算成功
            if "<title>出國上網最安心｜會員登入</title>" in response.text:
                print("   ❌ 失败：登录失效 (服务器重定向到了登录页)。")
            elif "login" in response.url:
                 print("   ❌ 失败：被重定向到了登录 URL。")
            else:
                print("   ✅ 下单请求已发送！(请登录网页确认订单是否生成)")
        else:
            print(f"   ❌ 失败：{response.status_code}")
    except Exception as e:
        print(f"   ❌ 错误: {e}")

# ================= 主程序 =================
GLOBAL_VERIFY_ID = "" 

if __name__ == "__main__":
    print("=== 扬奇全自动脚本 V12 (下单Header修复版) ===")
    
    target_email = input("请输入邮箱: ").strip()
    if "@" not in target_email:
        print("邮箱无效")
        sys.exit()

    random_phone = generate_taiwan_phone()
    
    # 1. 获取 ID
    initial_id = get_server_session_and_id()
    GLOBAL_VERIFY_ID = initial_id
    
    print(f"准备就绪: ID={initial_id} | 手机={random_phone}")
    time.sleep(1)

    # 2. 注册 
    if step1_register(target_email, random_phone, initial_id):
        final_id = GLOBAL_VERIFY_ID
        print(f"   [提示] 当前生效的会话 ID: {final_id}")
        
        # 3. 发信
        if step2_send_verify(final_id):
            # 4. 等待
            step3_wait_for_user()
            
            # 5. 登录 & 后续
            if step4_login(target_email):
                time.sleep(1)
                step5_update_profile(FIXED_NAME, random_phone)
                time.sleep(1)
                step6_place_order()
            else:
                print("登录失败，流程结束。")
        else:
            print("发信失败，流程结束。")
    else:
        print("注册最终失败。")
