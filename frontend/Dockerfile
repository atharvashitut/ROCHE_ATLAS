FROM node:22-alpine AS builder

WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

COPY --from=builder --chown=nginx:nginx /app/dist /usr/share/nginx/html
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf

USER nginx
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 CMD wget --quiet --spider http://127.0.0.1:8080/healthz || exit 1
