FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci || npm install
COPY . .
ARG UPLOAD_HOST
ARG PUBLIC_HOST
ENV EXPO_PUBLIC_UPLOAD_HOST=$UPLOAD_HOST EXPO_PUBLIC_PUBLIC_HOST=$PUBLIC_HOST
RUN npx expo export -p web

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
