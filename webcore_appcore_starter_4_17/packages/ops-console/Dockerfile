# Ops Console Dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

# 의존성 설치
COPY package*.json ./
COPY packages/ops-console/package*.json ./packages/ops-console/
RUN npm ci --workspace=@appcore/ops-console

# 소스 코드 복사 및 빌드
COPY packages/ops-console ./packages/ops-console
RUN npm run build --workspace=@appcore/ops-console

# 프로덕션 이미지 (Nginx)
FROM nginx:alpine

# 빌드된 파일 복사
COPY --from=builder /app/packages/ops-console/dist /usr/share/nginx/html

# Nginx 설정
COPY packages/ops-console/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

