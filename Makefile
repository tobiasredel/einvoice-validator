VERSION ?= 1.0.0
IMAGE := einvoice-validator:$(VERSION)

.PHONY: build test release
build:
	docker build -f docker/Dockerfile --build-arg APP_VERSION=$(VERSION) -t $(IMAGE) .
test: build
	python3 -I tests/test_unit.py
	python3 -I tests/test_image.py $(IMAGE)
release:
	sh tools/release.sh $(VERSION)
