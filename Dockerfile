FROM python:3.11-slim

RUN apt-get update && apt-get install -y wget grep firefox-esr && rm -rf /var/lib/apt/lists/*

RUN GECKO_VERSION=$(wget -qO- https://api.github.com/repos/mozilla/geckodriver/releases/latest | grep tag_name | cut -d '"' -f4) && \
    wget -q https://github.com/mozilla/geckodriver/releases/download/${GECKO_VERSION}/geckodriver-${GECKO_VERSION}-linux64.tar.gz && \
    tar -xzf geckodriver-${GECKO_VERSION}-linux64.tar.gz && \
    mv geckodriver /usr/local/bin/ && \
    chmod +x /usr/local/bin/geckodriver && \
    rm geckodriver-*.tar.gz

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

CMD ["python", "app.py"]
