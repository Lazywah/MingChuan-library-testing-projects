#!/bin/bash
# ==============================================================================
# AI 訓練平台 - GPU 伺服器 SSH 安全強化腳本
# 適用場景：GPU 伺服器暴露於外網時使用
# 執行：sudo bash ssh-hardening.sh
# ==============================================================================

set -e

SSH_PORT=${1:-2222}  # 預設使用 2222，可傳入參數自訂

echo "======================================"
echo "  SSH 安全強化開始 (Port: $SSH_PORT)"
echo "======================================"

# 備份原始設定
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
echo "[✓] 已備份 sshd_config"

# 修改 SSH 設定
sudo sed -i "s/^#\?Port .*/Port $SSH_PORT/" /etc/ssh/sshd_config
sudo sed -i "s/^#\?PermitRootLogin .*/PermitRootLogin no/" /etc/ssh/sshd_config
sudo sed -i "s/^#\?PasswordAuthentication .*/PasswordAuthentication no/" /etc/ssh/sshd_config
sudo sed -i "s/^#\?MaxAuthTries .*/MaxAuthTries 3/" /etc/ssh/sshd_config
echo "[✓] SSH 設定已更新"

# 重啟 SSH
sudo systemctl restart sshd
echo "[✓] SSH 服務已重啟"

# 設定防火牆
sudo apt install -y ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow $SSH_PORT/tcp
sudo ufw --force enable
echo "[✓] 防火牆已啟用 (僅開放 Port $SSH_PORT)"

# 安裝 Fail2Ban
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
echo "[✓] Fail2Ban 已安裝並啟動"

echo "======================================"
echo "  ✅ SSH 安全強化完成！"
echo ""
echo "  SSH Port 已改為: $SSH_PORT"
echo "  連線指令: ssh -p $SSH_PORT gpu_admin@本機IP"
echo ""
echo "  ⚠️ 請確認您的金鑰已部署，否則將無法登入！"
echo "======================================"
