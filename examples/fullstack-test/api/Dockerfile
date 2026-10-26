FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY server.js ./
USER node
# npm start 대신 node 로 직접 실행 (읽기 전용 파일시스템에서 npm 이 로그를 쓰다 실패하지 않게)
CMD ["node", "server.js"]
