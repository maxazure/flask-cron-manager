#!/bin/bash
# 变量配置，请根据实际情况修改
APP_DIR="/path/to/your/app"         # 应用所在目录（存放 app.py 的目录）
APP_FILE="app.py"                   # Flask 应用入口文件
SERVICE_NAME="flask-cron-manager"            # 服务名称
PYTHON_BIN="/usr/bin/env python3"   # Python 可执行文件路径

# 生成 systemd 服务文件
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
sudo tee ${SERVICE_FILE} > /dev/null <<EOF
[Unit]
Description=Flask 定时任务管理系统
After=network.target

[Service]
User=$(whoami)
Group=$(id -gn)
WorkingDirectory=${APP_DIR}
ExecStart=${PYTHON_BIN} ${APP_FILE} --port 8989
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 重新加载 systemd 配置，并启用服务
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}.service
sudo systemctl start ${SERVICE_NAME}.service

echo "服务已启动并设置为开机自启，监听端口 8989。"