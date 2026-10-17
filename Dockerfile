# Python 小版本随基础镜像更新；唯一应用依赖通过 requirements.txt 固定版本。
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 wordgarden \
    && useradd --uid 10001 --gid wordgarden --no-create-home wordgarden
COPY backend/ ./backend/
COPY data/ ./data/
COPY public/ ./public/
COPY serve.py manage.py ./
# Windows ZIP 解压得到的源文件可能只有 root 可读；镜像内明确设置运行所需的权限。
RUN find /app/backend /app/data /app/public -type d -exec chmod 755 {} + \
    && find /app/backend /app/data /app/public -type f -exec chmod 644 {} + \
    && chmod 644 /app/serve.py /app/manage.py \
    && mkdir -p /app/storage \
    && chown wordgarden:wordgarden /app/storage
USER wordgarden
# 构建时就用实际运行用户导入应用、读取页面，权限错误必须在交付镜像前暴露。
RUN python -c "import backend.web; from pathlib import Path; Path('public/index.html').read_text(encoding='utf-8'); print('Runtime source access OK')"
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=3)" || exit 1
CMD ["python", "serve.py", "--host", "0.0.0.0", "--port", "8765"]
