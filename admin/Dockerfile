FROM node:24-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./frontend/
COPY admin/package.json admin/package-lock.json ./admin/
RUN npm ci --prefix frontend --no-audit --no-fund && npm ci --prefix admin --no-audit --no-fund
COPY frontend/src ./frontend/src
COPY frontend/public ./frontend/public
COPY admin ./admin
WORKDIR /app/admin
ARG VITE_ADMIN_BASE=/
ARG VITE_WORKSPACE_URL=/
ENV VITE_ADMIN_BASE=$VITE_ADMIN_BASE
ENV VITE_WORKSPACE_URL=$VITE_WORKSPACE_URL
RUN npm run build

FROM nginx:1.28-alpine
COPY admin/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/admin/dist /usr/share/nginx/html
EXPOSE 80
