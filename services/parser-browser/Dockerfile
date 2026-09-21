FROM mcr.microsoft.com/playwright:v1.49.1-jammy

WORKDIR /app

ENV NODE_OPTIONS=--dns-result-order=ipv4first
ENV npm_config_registry=https://registry.npmmirror.com
ENV npm_config_fetch_retries=10
ENV npm_config_fetch_retry_mintimeout=20000
ENV npm_config_fetch_retry_maxtimeout=180000
ENV npm_config_audit=false
ENV npm_config_fund=false

COPY package.json package-lock.json* ./

RUN npm install --prefer-online

COPY server.js ./
COPY sessions.js ./

EXPOSE 3000

CMD ["bash", "-lc", "Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp & export DISPLAY=:99 && node /app/server.js"]
