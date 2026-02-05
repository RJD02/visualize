FROM node:20-alpine

RUN apk add --no-cache chromium nss freetype harfbuzz ttf-freefont
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=1
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser

RUN ln -s /usr/bin/chromium /usr/bin/chromium-browser || true

RUN npm install -g @mermaid-js/mermaid-cli

COPY render.sh /render.sh
RUN chmod +x /render.sh

ENTRYPOINT ["/render.sh"]
