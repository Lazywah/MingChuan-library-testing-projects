FROM python:3.11-slim

WORKDIR /app

# Install docker CLI so we can spawn siblings
RUN apt-get update && \
    apt-get install -y docker.io curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .
# ZH: v3.6 內建訓練腳本（使用者只上傳資料時由平台提供的程式）。
#     worker 會在每次任務時把它複製到共享儲存，讓訓練容器讀得到。
# EN: v3.6 built-in training scripts; the worker copies them into shared storage per job.
COPY builtin_scripts/ ./builtin_scripts/

CMD ["python", "-u", "worker.py"]
