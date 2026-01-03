#!/bin/bash

# ================= 配置区 =================
# ⚠️ 请务必修改这里！替换为你 GitHub 仓库的 "Raw" 基础地址
# 这里的地址应该指向你存放 server_yanci_bot.py 和 requirements.txt 的目录
REPO_URL="https://raw.githubusercontent.com/2019xuanying/CMLINK/main"
# 安装路径
INSTALL_DIR="/root/yanci_bot"

# ================= 脚本逻辑 =================

# 检查是否为 Root 用户
if [[ $EUID -ne 0 ]]; then
   echo "❌ 错误：请使用 root 权限运行此脚本！" 
   echo "👉 请先运行: sudo -i"
   exit 1
fi

echo "======================================"
echo "   扬奇抢单机器人 - GitHub 远程部署"
echo "======================================"

# 1. 环境安装
echo "[1/6] 更新系统并安装 Python 环境..."
apt-get update -y
apt-get install -y python3 python3-pip python3-venv curl

# 2. 准备目录
echo "[2/6] 创建安装目录: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR" || exit

# 3. 从 GitHub 下载核心文件
echo "[3/6] 正在从 GitHub 拉取代码..."
echo "      源地址: $REPO_URL"

# 下载主程序
curl -s -O "$REPO_URL/server_yanci_bot.py"
if [[ ! -f "server_yanci_bot.py" ]]; then
    echo "❌ 下载 server_yanci_bot.py 失败！请检查 REPO_URL 是否正确。"
    exit 1
fi

# 下载依赖表
curl -s -O "$REPO_URL/requirements.txt"
if [[ ! -f "requirements.txt" ]]; then
    echo "❌ 下载 requirements.txt 失败！请检查文件是否存在于仓库中。"
    exit 1
fi

echo "      ✅ 文件下载成功。"

# 4. 创建虚拟环境并安装依赖
echo "[4/6] 配置 Python 虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# 升级 pip 并安装依赖
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 5. 配置 Bot Token 和 管理员 ID
echo "[5/6] 配置机器人参数..."
ENV_FILE=".env"

if [ -f "$ENV_FILE" ]; then
    echo "      ⚠️ 检测到现有配置文件 (.env)。"
    echo "      跳过配置录入，将继续使用旧配置。"
    echo "      (如果想重置，请先运行: rm $INSTALL_DIR/.env)"
else
    # --- 录入 Token ---
    echo ""
    echo "👉 [1/2] 请输入你的 Telegram Bot Token (从 BotFather 获取):"
    read -r input_token
    if [[ -z "$input_token" ]]; then
        echo "❌ Token 不能为空！"
        exit 1
    fi

    # --- 录入 Admin ID ---
    echo ""
    echo "👉 [2/2] 请输入管理员的 Telegram ID (用于管理权限，必须是数字):"
    echo "   (如果你不知道自己的 ID，可以先在 TG 上搜 @userinfobot 获取)"
    read -r input_admin_id
    
    # 简单的数字校验
    if ! [[ "$input_admin_id" =~ ^[0-9]+$ ]]; then
        echo "❌ 错误：管理员 ID 必须是纯数字！"
        exit 1
    fi

    # --- 写入配置 ---
    echo "TG_BOT_TOKEN=$input_token" > "$ENV_FILE"
    echo "TG_ADMIN_ID=$input_admin_id" >> "$ENV_FILE"
    echo "      ✅ 配置已保存到 .env"
fi

# 6. 配置 Systemd 服务
echo "[6/6] 配置后台服务 (Systemd)..."
SERVICE_FILE="/etc/systemd/system/yanci_bot.service"

cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Yanci TG Bot Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/server_yanci_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 重载并启动服务
systemctl daemon-reload
systemctl enable yanci_bot
systemctl restart yanci_bot

echo "======================================"
echo "   🎉 部署成功！机器人已启动"
echo "======================================"
echo "管理命令："
echo "  - 查看日志: journalctl -u yanci_bot -f"
echo "  - 重启服务: systemctl restart yanci_bot"
echo "  - 停止服务: systemctl stop yanci_bot"
echo "======================================"
