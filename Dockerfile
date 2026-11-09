# Stufe 1: PokéAPI-Daten und Sprites einmalig beim Build holen
FROM node:22-alpine AS data
RUN apk add --no-cache git
WORKDIR /build
COPY scripts/ scripts/
RUN node scripts/build-data.mjs /out/data
RUN git clone --quiet --depth 1 --filter=blob:none --no-checkout https://github.com/PokeAPI/sprites.git spr \
 && cd spr && git sparse-checkout set --no-cone '/sprites/pokemon/*.png' && git checkout --quiet \
 && mkdir -p /out/sprites && cp sprites/pokemon/*.png /out/sprites/

# Stufe 2: statische Auslieferung
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY --from=data /out/ /usr/share/nginx/html/
HEALTHCHECK --interval=60s --timeout=5s CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
