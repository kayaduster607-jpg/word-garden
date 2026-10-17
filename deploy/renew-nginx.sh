#!/bin/sh
# 安装到 Certbot 的 renewal-hooks/deploy 后，仅在证书续期成功时重载 Nginx。
set -eu
nginx -t
systemctl reload nginx
