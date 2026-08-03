FROM python:3.12-slim

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libopus0 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./
RUN useradd --create-home botuser \
    && mkdir -p /app/data /app/logs \
    && chown -R botuser:botuser /app
USER botuser

CMD ["python", "bot.py"]
