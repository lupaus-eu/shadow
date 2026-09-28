FROM docker.io/library/node:22-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS base

WORKDIR /app

ENV PNPM_HOME="/pnpm"
ENV PATH="${PNPM_HOME}:${PATH}"

RUN corepack enable && corepack prepare pnpm@10.12.1 --activate

COPY package.json pnpm-lock.yaml ./

FROM base AS deps
RUN pnpm install --frozen-lockfile

FROM deps AS dev
ENV NODE_ENV=development
COPY . .
EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0"]

FROM deps AS build
COPY . .
RUN pnpm build

FROM docker.io/library/caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648 AS production

# Drop the upstream file capability: no-new-privileges with cap_drop ALL refuses
# to execute capability-bearing binaries. Compose instead allows ports 80/443
# through the namespaced net.ipv4.ip_unprivileged_port_start sysctl.
RUN cp /usr/bin/caddy /tmp/caddy \
    && mv /tmp/caddy /usr/bin/caddy \
    && chmod 0755 /usr/bin/caddy \
    && mkdir -p /data /config \
    && chown 10001:10001 /data /config \
    && chmod 0700 /data /config

COPY Caddyfile /etc/caddy/Caddyfile
COPY --chmod=755 caddy-entrypoint.sh /usr/local/bin/schatten-caddy-entrypoint
COPY --from=build /app/dist /srv

ENV XDG_CONFIG_HOME=/config
ENV XDG_DATA_HOME=/data
ENV CADDY_TLS_MODE=acme

EXPOSE 80 443

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD wget --quiet --spider http://127.0.0.1:8081/health || exit 1

USER 10001:10001

ENTRYPOINT ["/usr/local/bin/schatten-caddy-entrypoint"]
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]

FROM base AS preview
ENV NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY package.json pnpm-lock.yaml ./
EXPOSE 4173
CMD ["pnpm", "exec", "vite", "preview", "--host", "0.0.0.0", "--port", "4173"]
