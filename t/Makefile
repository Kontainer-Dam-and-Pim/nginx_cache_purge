# t/Makefile — run from the t/ directory
# Build context for Docker is always the repo root (one level up).
.PHONY: help build build-sanitize test test-all compat sanitize valgrind analyze test-compat versions clean shell

NGINX_VERSION  ?= $(shell ci/nginx_versions.py latest)
UBUNTU_VERSION ?= 24.04
IMAGE          := ngx-cache-purge-test:$(NGINX_VERSION)-$(UBUNTU_VERSION)
SAN_IMAGE      := $(IMAGE)-asan-ubsan
ROOT           := $(abspath $(CURDIR)/..)
RUN            := docker run --rm -v "$(ROOT):/src"

GREEN  := \033[0;32m
YELLOW := \033[1;33m
NC     := \033[0m

help:
	@echo "$(GREEN)ngx_cache_purge test commands$(NC) (run from t/)"
	@echo ""
	@echo "$(YELLOW)Targets:$(NC)"
	@echo "  build          Build the test image"
	@echo "  test           basic.t + config.t"
	@echo "  test-all       Every Test::Nginx suite"
	@echo "  compat         Struct layout check against this nginx (full and minimal build)"
	@echo "  sanitize       Every suite under AddressSanitizer + UndefinedBehaviorSanitizer"
	@echo "  valgrind       Every suite under valgrind memcheck"
	@echo "  analyze        Strict warnings, cppcheck, clang and gcc static analyzers"
	@echo "  test-compat    compat + test-all for every version in nginx-versions.json"
	@echo "  versions       Apply new nginx releases to nginx-versions.json and the README"
	@echo "  shell          Interactive shell in the test container"
	@echo "  clean          Remove the Test::Nginx server root"
	@echo ""
	@echo "$(YELLOW)Variables:$(NC)"
	@echo "  NGINX_VERSION  (default: newest in nginx-versions.json, now $(NGINX_VERSION))"
	@echo "  UBUNTU_VERSION (default: $(UBUNTU_VERSION))"

build:
	docker build -f Dockerfile \
	    --build-arg NGINX_VERSION=$(NGINX_VERSION) \
	    --build-arg UBUNTU_VERSION=$(UBUNTU_VERSION) \
	    -t $(IMAGE) ..

build-sanitize:
	docker build -f Dockerfile \
	    --build-arg NGINX_VERSION=$(NGINX_VERSION) \
	    --build-arg UBUNTU_VERSION=$(UBUNTU_VERSION) \
	    --build-arg CC=clang --build-arg SANITIZE=asan,ubsan \
	    -t $(SAN_IMAGE) ..

test: build
	$(RUN) $(IMAGE) t/ci/run-suite.sh t/basic.t t/config.t

test-all: build
	$(RUN) $(IMAGE)

compat: build
	$(RUN) $(IMAGE) t/ci/compat.sh

sanitize: build-sanitize
	$(RUN) $(SAN_IMAGE)

valgrind: build
	$(RUN) -e VALGRIND=1 $(IMAGE)

analyze: build
	docker run --rm -v "$(ROOT):$(ROOT)" -w "$(ROOT)" $(IMAGE) \
	    t/ci/analyze.sh /nginx-src t/analysis

test-compat:
	@ci/nginx_versions.py pairs | while read -r nginx ubuntu; do \
	    echo "$(YELLOW)--- nginx $$nginx on Ubuntu $$ubuntu ---$(NC)"; \
	    $(MAKE) --no-print-directory NGINX_VERSION=$$nginx UBUNTU_VERSION=$$ubuntu compat test-all || exit 1; \
	done

versions:
	ci/nginx_versions.py update

shell: build
	docker run --rm -it -v "$(ROOT):/src" $(IMAGE) bash

clean:
	docker run --rm -v "$(CURDIR):/t" ubuntu:$(UBUNTU_VERSION) rm -rf /t/servroot /t/analysis
