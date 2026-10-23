# check=skip=InvalidDefaultArgInFrom
# docker/Dockerfile -- the official nginx image with this module loaded.
# Build context: the repo root.
#
#   docker build -f docker/Dockerfile --build-arg NGINX_VERSION=1.31.8 .
#   ... --build-arg VARIANT=-alpine
ARG NGINX_VERSION
ARG VARIANT=

FROM nginx:${NGINX_VERSION}${VARIANT} AS build
COPY docker/build-module.sh /build-module.sh
COPY config ngx_cache_purge_module.c /module/
RUN /build-module.sh

FROM nginx:${NGINX_VERSION}${VARIANT}
COPY --from=build /out/ngx_http_cache_purge_module.so /usr/lib/nginx/modules/
RUN sed -i '1i load_module modules/ngx_http_cache_purge_module.so;' /etc/nginx/nginx.conf
