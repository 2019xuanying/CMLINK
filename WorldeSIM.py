import requests
import json
import random
import string
import re
import html
import time
from urllib.parse import unquote

# --- 辅助函数 ---
def generate_random_string(length=8):
    letters = string.ascii_letters
    return ''.join(random.choice(letters) for i in range(length))

def generate_random_password():
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for i in range(12))

def random_sleep(min_s=2, max_s=5, task_name="操作"):
    """模拟人类操作延迟"""
    delay = random.uniform(min_s, max_s)
    print(f"[*] (模拟人类) 正在{task_name}... 等待 {delay:.1f} 秒")
    time.sleep(delay)

def get_headers(csrf_token=None, csrf_key='X-CSRF-TOKEN', is_livewire=True, referer='https://world-esim.com/login'):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html, application/xhtml+xml, application/json',
        'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Origin': 'https://world-esim.com',
        'Referer': referer,
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }
    
    if csrf_token:
        if is_livewire:
            headers[csrf_key] = csrf_token
            headers['X-Livewire'] = 'true'
            headers['Content-Type'] = 'application/json'
        else:
            # 普通表单提交
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            headers['Sec-Fetch-Dest'] = 'document'
            headers['Sec-Fetch-Mode'] = 'navigate'
            headers['Sec-Fetch-Site'] = 'same-origin'
            headers['Upgrade-Insecure-Requests'] = '1'
            
    return headers

def merge_livewire_memo(original_memo, response_memo):
    if not response_memo:
        return original_memo
    new_memo = original_memo.copy()
    if 'checksum' in response_memo:
        new_memo['checksum'] = response_memo['checksum']
    if 'data' in response_memo and isinstance(response_memo['data'], dict):
        if 'data' not in new_memo:
            new_memo['data'] = {}
        for key, value in response_memo['data'].items():
            new_memo['data'][key] = value
    if 'errors' in response_memo:
        new_memo['errors'] = response_memo['errors']
    if 'htmlHash' in response_memo:
        new_memo['htmlHash'] = response_memo['htmlHash']
    return new_memo

def run_flow(target_email):
    session = requests.Session()
    print(f"[*] 正在初始化，目标邮箱: {target_email}")
    
    # ================= 步骤 1: 获取初始状态 =================
    try:
        response = session.get('https://world-esim.com/login', headers=get_headers(is_livewire=False))
        
        csrf_token = None
        csrf_header_key = 'X-CSRF-TOKEN'

        # 提取 Token
        csrf_match = re.search(r'<meta\s+name=["\']csrf-token["\']\s+content=["\'](.*?)["\']', response.text)
        if csrf_match:
            csrf_token = csrf_match.group(1)
        elif 'XSRF-TOKEN' in session.cookies:
            csrf_token = unquote(session.cookies['XSRF-TOKEN'])
            csrf_header_key = 'X-XSRF-TOKEN'
        else:
            print("[!] 无法获取 CSRF Token。")
            return

        # 提取组件
        livewire_match = re.search(r'wire:initial-data="([^"]+otp-verification[^"]+)"', response.text)
        if not livewire_match:
            livewire_match = re.search(r'wire:initial-data="({.*?})"', response.text)
        if not livewire_match:
            print("[!] 无法提取 Livewire 组件。")
            return

        initial_data = json.loads(html.unescape(livewire_match.group(1)))
        fingerprint = initial_data['fingerprint']
        current_server_memo = initial_data['serverMemo'] 
        print(f"[*] 初始化成功 (组件ID: {fingerprint['id']})")

    except Exception as e:
        print(f"[!] 初始化异常: {e}")
        return

    random_sleep(2, 4, "填写注册表单")

    # ================= 步骤 2: 提交注册信息 =================
    first_name = generate_random_string(5).capitalize()
    last_name = generate_random_string(6).capitalize()
    password = generate_random_password()
    
    register_payload = {
        "fingerprint": fingerprint,
        "serverMemo": current_server_memo,
        "updates": [
            {
                "type": "callMethod",
                "payload": {
                    "id": generate_random_string(4).lower(),
                    "method": "generateOtp",
                    "params": [{
                        "_token": csrf_token,
                        "given_name": first_name,
                        "family_name": last_name,
                        "country_id": str(random.randint(1, 240)),
                        "email": target_email,
                        "password": password,
                        "password_confirmation": password,
                        "birth_year": str(random.randint(1980, 2005)),
                        "birth_month": str(random.randint(1, 12)),
                        "birth_date": str(random.randint(1, 28)),
                        "sex": random.choice(["male", "female"]),
                        "is_receive_emails": "1",
                        "agreement": "1"
                    }]
                }
            }
        ]
    }

    print("[*] 正在发送注册请求...")
    target_url = 'https://world-esim.com/livewire/message/otp-verification'
    
    try:
        resp = session.post(target_url, headers=get_headers(csrf_token, csrf_header_key, True), json=register_payload)
        if resp.status_code != 200:
            print(f"[!] 注册请求失败: {resp.status_code}")
            return

        resp_json = resp.json()
        response_memo = resp_json.get('serverMemo', {})
        current_server_memo = merge_livewire_memo(current_server_memo, response_memo)
        
        if not current_server_memo['data'].get('showOtpForm'):
            errors = current_server_memo.get('errors', [])
            print(f"[!] 注册未通过，服务器错误信息: {errors}")
            return
            
        print(f"[+] ✅ 注册信息已提交！密码: {password}")
        
    except Exception as e:
        print(f"[!] 注册过程出错: {e}")
        return

    # ================= 步骤 3: 输入并验证 OTP =================
    otp_code = input("\n>>> 请输入您邮件收到的验证码 (5位数字): ").strip()
    
    verify_payload = {
        "fingerprint": fingerprint,
        "serverMemo": current_server_memo,
        "updates": [
            {
                "type": "syncInput",
                "payload": {
                    "id": generate_random_string(4).lower(),
                    "name": "otp",
                    "value": otp_code
                }
            },
            {
                "type": "callMethod",
                "payload": {
                    "id": generate_random_string(4).lower(),
                    "method": "verifyOtp", 
                    "params": []
                }
            }
        ]
    }
    
    print(f"[*] 正在提交验证码: {otp_code} ...")
    
    try:
        random_sleep(1, 2, "点击验证按钮")
        otp_resp = session.post(target_url, headers=get_headers(csrf_token, csrf_header_key, True), json=verify_payload)
        
        if otp_resp.status_code == 200:
            otp_json = otp_resp.json()
            effects = otp_json.get('effects', {})
            redirect_url = effects.get('redirect')
            
            if redirect_url:
                print(f"[+] ✅ 验证成功！登录 Session 已建立。")
                
                random_sleep(2, 4, "跳转个人主页")
                print(f"[*] 正在跳转到个人页面 (Mypage)...")
                
                # 访问重定向链接，更新 Referer
                headers_mypage = get_headers(is_livewire=False, referer='https://world-esim.com/login')
                mypage_resp = session.get(redirect_url, headers=headers_mypage)
                
                # 更新 CSRF Token
                new_csrf_match = re.search(r'<meta\s+name=["\']csrf-token["\']\s+content=["\'](.*?)["\']', mypage_resp.text)
                if new_csrf_match:
                    current_csrf_token = new_csrf_match.group(1)
                else:
                    current_csrf_token = csrf_token
                
                # ================= 步骤 4 & 5: 自动下单并确认 =================
                place_and_confirm_order(session, current_csrf_token)
                
            else:
                response_memo_otp = otp_json.get('serverMemo', {})
                current_server_memo = merge_livewire_memo(current_server_memo, response_memo_otp)
                errors = current_server_memo.get('errors', [])
                print(f"[!] 验证失败: {errors}")
                return
        else:
             print(f"[!] 验证请求失败，状态码: {otp_resp.status_code}")
             return
             
    except Exception as e:
        print(f"[!] 验证过程出错: {e}")
        return

def place_and_confirm_order(session, csrf_token):
    """
    步骤 4: 加入购物车
    步骤 5: 确认支付
    """
    random_sleep(3, 5, "浏览商品并加入购物车")
    
    # --- 步骤 4: 加入购物车 ---
    store_url = 'https://world-esim.com/store'
    order_data = {
        '_token': csrf_token,
        'plan_id': '10',          # 中国商店
        'quantity': '1',
        'plan_name': 'China eSIM 500MB 1 Day',
        'is_hawaii': '0',
        'wireless_company_id': '1', 
        'quantity_update': '1',
        'plan_detail_id': '7885'  # 500MB 1 Day 套餐 ID
    }

    print(f"\n[*] 步骤 4: 正在下单 'China eSIM 500MB 1 Day'...")
    try:
        headers_store = get_headers(is_livewire=False, referer='https://world-esim.com/mypage')
        resp_store = session.post(store_url, data=order_data, headers=headers_store)
        
        if resp_store.status_code == 200:
            print("[+] 加入购物车成功，进入支付确认页面。")
            
            # --- 步骤 5: 提取支付会话 ID 并确认支付 ---
            payment_page_html = resp_store.text
            
            # 1. 提取 payment_session_id
            session_match = re.search(r'name="payment_session_id" value="([^"]+)"', payment_page_html)
            if not session_match:
                print("[!] 错误: 无法在支付页面找到 payment_session_id。")
                return

            payment_session_id = session_match.group(1)
            print(f"[*] 获取到支付会话 ID: {payment_session_id}")

            # 2. 提取最新 token (确保使用当前页面的 token)
            token_match = re.search(r'name="_token" value="([^"]+)"', payment_page_html)
            final_token = token_match.group(1) if token_match else csrf_token
            
            # 构造最终支付请求 (根据抓包数据)
            capture_url = 'https://world-esim.com/regist/payment/capture'
            capture_data = {
                '_token': final_token,
                'payment_session_id': payment_session_id,
                'quantity_update': '1',
                'reg_site': '',
                'departure_day': '',
                'return_day': '',
                'receive_air_time': '',
                'place_receive_name': '',
                'receive_place_id': '',
                'place_return_name': '',
                'payment_type': '3', # 3 = 全额折扣 (0元购)
                'purpose': '1',      # 1 = 闲暇 (必填)
                'agreement': '1',    # 必选
                'coupon_code': '',
                'postage_money': ''
            }
            
            # 关键：大幅增加延迟，模拟人类阅读条款 (5-10秒)
            random_sleep(5, 10, "阅读条款并确认订单 (防429)") 
            
            print("[*] 步骤 5: 正在提交最终订单确认...")
            
            # 关键修改：Referer 必须是 payment 页面
            headers_capture = get_headers(is_livewire=False, referer='https://world-esim.com/regist/payment')
            
            resp_capture = session.post(capture_url, data=capture_data, headers=headers_capture)
            
            # 429 重试逻辑
            if resp_capture.status_code == 429:
                print("[!] ⚠️ 触发频率限制 (429)。等待 15 秒后自动重试...")
                time.sleep(15)
                resp_capture = session.post(capture_url, data=capture_data, headers=headers_capture)

            if resp_capture.status_code == 200:
                if "complete" in resp_capture.url:
                     print(f"[+] 🎉🎉🎉 成功到达订单完成页！")
                     print(f"[+] 最终 URL: {resp_capture.url}")
                     
                     order_num_match = re.search(r'num_completed.*?span.*?(\d+)', resp_capture.text, re.DOTALL)
                     if order_num_match:
                         print(f"[+] 📦 订单号: {order_num_match.group(1)}")
                     
                     print(f"[+] ✅ 流程结束：确认邮件应该已触发发送。")
                else:
                    print(f"[?] 警告：请求成功但未跳转到 complete 页面，当前 URL: {resp_capture.url}")
            else:
                print(f"[!] 最终支付请求失败: {resp_capture.status_code}")
                # print(resp_capture.text[:500])

        else:
            print(f"[!] 下单失败，状态码: {resp_store.status_code}")

    except Exception as e:
        print(f"[!] 下单过程出错: {e}")

if __name__ == "__main__":
    print("=== World eSIM 全流程脚本 v7 (Verified Payload) ===")
    email_input = input("请输入新邮箱: ").strip()
    if "@" in email_input:
        run_flow(email_input)
    else:
        print("邮箱格式错误")
