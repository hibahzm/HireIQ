FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Where the browser reaches the API/WebSocket. Left empty for local Docker Compose,
# where the code falls back to the same-origin "/api" + "/ws" nginx proxy. In prod,
# pass --build-arg VITE_API_URL=https://<api-fqdn> --build-arg VITE_WS_URL=wss://<api-fqdn>
# so the candidate's browser calls the API directly (see docs/DEPLOYMENT_AZURE.md §10e).
ARG VITE_API_URL=""
ARG VITE_WS_URL=""
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
