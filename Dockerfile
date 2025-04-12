FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    wget gnupg xvfb libnss3 libgconf-2-4 libfontconfig1 libxss1 \
    libasound2 libxtst6 libglib2.0-0 libgtk-3-0 libgbm1 libcups2 \
    libdrm2 libxcomposite1 libxrandr2 --no-install-recommends \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub \
    | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN chmod +x /app
RUN echo '#!/bin/bash\nXvfb :99 -screen 0 1920x1080x24 &\nexport DISPLAY=:99\npython bot.py' > entrypoint.sh && chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
