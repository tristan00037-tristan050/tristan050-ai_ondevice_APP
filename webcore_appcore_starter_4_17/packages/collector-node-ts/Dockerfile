# Collector Dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

# 의존성 설치
COPY package*.json ./
COPY packages/collector-node-ts/package*.json ./packages/collector-node-ts/
RUN npm ci --workspace=@appcore/collector-node-ts

# 소스 코드 복사 및 빌드
COPY packages/collector-node-ts ./packages/collector-node-ts
COPY contracts ./contracts
RUN npm run build --workspace=@appcore/collector-node-ts

# 프로덕션 이미지
FROM node:20-alpine

WORKDIR /app

# 프로덕션 의존성만 설치
COPY package*.json ./
COPY packages/collector-node-ts/package*.json ./packages/collector-node-ts/
RUN npm ci --workspace=@appcore/collector-node-ts --omit=dev

# 빌드된 파일 복사
COPY --from=builder /app/packages/collector-node-ts/dist ./packages/collector-node-ts/dist
COPY --from=builder /app/packages/collector-node-ts/src/db/schema.sql ./packages/collector-node-ts/src/db/schema.sql

# 환경 변수
ENV NODE_ENV=production
ENV PORT=9090

# 헬스 체크
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:9090/health', (r) => {process.exit(r.statusCode === 200 ? 0 : 1)})"

EXPOSE 9090

CMD ["node", "packages/collector-node-ts/dist/index.js"]

