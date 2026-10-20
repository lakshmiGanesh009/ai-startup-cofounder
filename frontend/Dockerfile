# The web app: Next.js's standalone server.
#
# One stage installs the locked packages and builds; the image that runs holds
# only the standalone server and its static files, as the unprivileged node
# user. Where the API is (BACKEND_URL) and its key (API_KEY) are read by the
# server when it runs, so one image serves any environment and holds no
# secret: .dockerignore keeps .env files out of the build.

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN BUILD_STANDALONE=1 npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
CMD ["node", "server.js"]
