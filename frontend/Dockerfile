# =============================================================================
# Frontend — Production Dockerfile
# Build: vite → static files → nginx
# =============================================================================

# ── Build ─────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

# Accept build arg so VITE_API_URL is baked into the bundle
ARG VITE_API_URL=http://localhost:8000/api/v1
ENV VITE_API_URL=$VITE_API_URL

COPY package.json ./
# npm ci requires a lockfile; npm install works without one
RUN npm install
COPY . .
RUN npm run build

# ── Serve ─────────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# nginx listens on 80; docker-compose maps it to host:3000
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
