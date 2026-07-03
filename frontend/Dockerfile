FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
# Full install (incl. devDeps) is required: `npm run build` runs `tsc -b`,
# which typechecks the colocated *.test.ts files, so vitest/testing-library
# type packages must be present. Do NOT switch to `npm ci --omit=dev` here —
# it would break the build typecheck. (vite build itself never bundles the
# test files, so the shipped dist is unaffected either way.)
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
