# Stages: `production` serves the built SPA with Caddy; the final `development`
# stage (the default target) runs the Vite dev server for the local stack.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM deps AS build
COPY . .
# Empty means same-origin API calls (Caddy routes /api/* to the backend).
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM caddy:2-alpine AS production
COPY caddy/frontend.Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
EXPOSE 8173

FROM deps AS development
COPY . .
EXPOSE 8173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
