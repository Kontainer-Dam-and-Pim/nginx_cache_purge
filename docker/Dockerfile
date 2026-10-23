# check=skip=InvalidDefaultArgInFrom
# docker/Dockerfile -- nginx with this module loaded: the official nginx
# image (Debian, or Alpine), or Rocky Linux with the nginx.org RPM.
# Build context: the repo root.
#
#   docker build -f docker/Dockerfile --build-arg NGINX_VERSION=1.31.8 .
#   ... --build-arg VARIANT=-alpine
#   ... --build-arg VARIANT=-rocky
ARG NGINX_VERSION
ARG VARIANT=

FROM nginx:${NGINX_VERSION} AS base

FROM nginx:${NGINX_VERSION}-alpine AS base-alpine

FROM rockylinux/rockylinux:9 AS base-rocky
ARG NGINX_VERSION
COPY docker/nginx.repo /etc/yum.repos.d/nginx.repo
RUN dnf -y install "nginx-${NGINX_VERSION}" && \
    dnf clean all && \
    ln -sf /dev/stdout /var/log/nginx/access.log && \
    ln -sf /dev/stderr /var/log/nginx/error.log
EXPOSE 80
STOPSIGNAL SIGQUIT
CMD ["nginx", "-g", "daemon off;"]

FROM base${VARIANT} AS build
COPY docker/build-module.sh /build-module.sh
COPY config ngx_cache_purge_module.c /module/
RUN /build-module.sh

FROM base${VARIANT}
COPY --from=build /out/ /
RUN sed -i '1i load_module modules/ngx_http_cache_purge_module.so;' /etc/nginx/nginx.conf
