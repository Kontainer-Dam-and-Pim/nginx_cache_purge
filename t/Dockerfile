# check=skip=InvalidDefaultArgInFrom
# t/Dockerfile — build context is always the repo root
#
#   docker build -f t/Dockerfile --build-arg NGINX_VERSION=x.y.z --build-arg UBUNTU_VERSION=24.04 .
#   ... --build-arg CC=clang --build-arg SANITIZE=asan,ubsan     nginx and the module under sanitizers
ARG UBUNTU_VERSION
FROM ubuntu:${UBUNTU_VERSION} AS base

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential clang cppcheck gdb jq llvm \
        libpcre2-dev libssl-dev zlib1g-dev \
        $(apt-cache show libpcre3-dev >/dev/null 2>&1 && echo libpcre3-dev) \
        $(apt-cache show libclang-rt-dev >/dev/null 2>&1 && echo libclang-rt-dev) \
        ca-certificates wget curl perl cpanminus make python3 valgrind \
    && rm -rf /var/lib/apt/lists/*

RUN cpanm --notest \
    Test::Nginx \
    Test::More \
    Test::Base \
    Test::LongString \
    List::MoreUtils

FROM base

ARG NGINX_VERSION
RUN test -n "${NGINX_VERSION}" \
    && wget -q https://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz \
    && tar xzf nginx-${NGINX_VERSION}.tar.gz \
    && mv nginx-${NGINX_VERSION} /nginx-src \
    && rm nginx-${NGINX_VERSION}.tar.gz

COPY t/ci/build-nginx.sh /ci/
COPY t/ci/lsan /ci/lsan/
COPY config ngx_cache_purge_module.c /module/

ARG CC=gcc
ARG SANITIZE=
RUN /ci/build-nginx.sh /nginx-src "${SANITIZE}" \
        --with-cc="${CC}" \
        --prefix=/etc/nginx \
        --sbin-path=/usr/sbin/nginx \
        --conf-path=/etc/nginx/nginx.conf \
        --error-log-path=/var/log/nginx/error.log \
        --http-log-path=/var/log/nginx/access.log \
        --pid-path=/var/run/nginx.pid \
        --lock-path=/var/run/nginx.lock \
        --http-client-body-temp-path=/var/cache/nginx/client_temp \
        --http-proxy-temp-path=/var/cache/nginx/proxy_temp \
        --http-fastcgi-temp-path=/var/cache/nginx/fastcgi_temp \
        --http-uwsgi-temp-path=/var/cache/nginx/uwsgi_temp \
        --http-scgi-temp-path=/var/cache/nginx/scgi_temp \
        --with-http_ssl_module \
        --with-http_realip_module \
        --with-http_addition_module \
        --with-http_sub_module \
        --with-http_dav_module \
        --with-http_flv_module \
        --with-http_mp4_module \
        --with-http_gunzip_module \
        --with-http_gzip_static_module \
        --with-http_random_index_module \
        --with-http_secure_link_module \
        --with-http_stub_status_module \
        --with-http_auth_request_module \
        --with-threads \
        --with-stream \
        --with-stream_ssl_module \
        --with-stream_ssl_preread_module \
        --with-stream_realip_module \
        --with-http_slice_module \
        --with-file-aio \
        --with-http_v2_module \
        --add-module=/module \
    && mkdir -p /var/cache/nginx/client_temp \
        /var/cache/nginx/proxy_temp \
        /var/cache/nginx/fastcgi_temp \
        /var/cache/nginx/uwsgi_temp \
        /var/cache/nginx/scgi_temp

WORKDIR /src

CMD ["t/ci/run-suite.sh"]
