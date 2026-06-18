FROM python:3.11-slim

RUN apt-get update && apt-get install -y firefox-esr wget && rm -rf /var/lib/apt/lists/*

RUN wget -q https://github.com/mozilla/geckodriver/releases/download/v0.36.0/geckodriver-v0.36.0-linux64.tar.gz \
    && tar -xzf geckodriver-v0.36.0-linux64.tar.gz \
    && mv geckodriver /usr/local/bin/geckodriver \
    && chmod +x /usr/local/bin/geckodriver \
    && rm geckodriver-v0.36.0-linux64.tar.gz

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

CMD ["python", "app.py"]
