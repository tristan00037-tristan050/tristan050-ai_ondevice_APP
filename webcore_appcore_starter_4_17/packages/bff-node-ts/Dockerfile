# BFF Dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

# 의존성 설치
COPY package*.json ./
COPY packages/bff-node-ts/package*.json ./packages/bff-node-ts/
RUN npm ci --workspace=@appcore/bff-node-ts

# 소스 코드 복사 및 빌드
COPY packages/bff-node-ts ./packages/bff-node-ts
RUN npm run build --workspace=@appcore/bff-node-ts

# 프로덕션 이미지
FROM node:20-alpine

WORKDIR /app

# 프로덕션 의존성만 설치
COPY package*.json ./
COPY packages/bff-node-ts/package*.json ./packages/bff-node-ts/
RUN npm ci --workspace=@appcore/bff-node-ts --omit=dev

# 빌드된 파일 복사
COPY --from=builder /app/packages/bff-node-ts/dist ./packages/bff-node-ts/dist

# 환경 변수
ENV NODE_ENV=production
ENV PORT=8080

# 헬스 체크
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:8080/health', (r) => {process.exit(r.statusCode === 200 ? 0 : 1)})"

EXPOSE 8080

CMD ["node", "packages/bff-node-ts/dist/index.js"]


