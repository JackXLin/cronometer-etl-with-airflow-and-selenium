FROM apache/airflow:2.9.2

USER root

# Install dependencies
RUN apt-get update && apt-get install -y \
    firefox-esr \
    wget \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libxt6 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxi6 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libnss3 \
    libxss1 \
    libx11-xcb1 \
    libxcb-glx0 \
    libdbus-1-3 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# Install the latest compatible version of geckodriver for Firefox 115.*
RUN wget https://github.com/mozilla/geckodriver/releases/download/v0.34.0/geckodriver-v0.34.0-linux64.tar.gz \
    && tar -xvzf geckodriver-v0.34.0-linux64.tar.gz \
    && mv geckodriver /usr/local/bin/ \
    && rm geckodriver-v0.34.0-linux64.tar.gz

COPY requirements.txt /requirements.txt
RUN chown airflow: /requirements.txt

USER airflow
RUN pip install --no-cache-dir -r /requirements.txt
