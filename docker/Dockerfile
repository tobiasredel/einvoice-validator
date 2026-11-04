# E-Invoice Validator & Viewer: Mustang + KoSIT + Python-App in einem Image, ohne Laufzeit-Downloads.
# Alle Fremdartefakte sind per Version und SHA-256 festgelegt.
FROM eclipse-temurin:24-jre-noble@sha256:b416d02335e702b0403ff280de9475a3348e29382285969c9d4e17862ce632e7 AS base

FROM base AS fetch
ARG MUSTANG_VERSION=2.26.0
ARG KOSIT_VERSION=1.6.3
ARG KOSIT_CONFIG_TAG=v2026-08-31
ARG KOSIT_CONFIG_ZIP=xrechnung-3.0.2-validator-configuration-2026-08-31.zip
ARG VIEWER_TAG=v2026-10-13
ARG VIEWER_ZIP=xrechnung-3.0.2-visualization-2026-10-13.zip
ADD --checksum=sha256:42d7868cb68264874a7b8cab4c3587b03b23ccc7cd72373da917f66758bb9736 \
    https://github.com/ZUGFeRD/mustangproject/releases/download/core-${MUSTANG_VERSION}/Mustang-CLI-${MUSTANG_VERSION}.jar /fetch/mustang.jar
ADD --checksum=sha256:799e64befca97d4080e03608c80b85dd5a5ecc5f4ae4f35d1116ec2855b9a7c9 \
    https://github.com/itplr-kosit/validator/releases/download/v${KOSIT_VERSION}/validator-${KOSIT_VERSION}-standalone.jar /fetch/kosit.jar
ADD --checksum=sha256:2530cd107c414511c5d0462ec10f886910395abfca820db82e83d70bf01221a8 \
    https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/download/${KOSIT_CONFIG_TAG}/${KOSIT_CONFIG_ZIP} /fetch/config.zip
ADD --checksum=sha256:ecf3913029218822ee4c90a86a3e23689768bf3568a061cf9bc742115e52264e \
    https://github.com/itplr-kosit/xrechnung-visualization/releases/download/${VIEWER_TAG}/${VIEWER_ZIP} /fetch/viewer.zip
COPY tools/split_scenarios.py /fetch/split_scenarios.py
RUN apt-get update && apt-get install -y --no-install-recommends unzip python3 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /opt/einvoice/kosit-config /opt/einvoice/viewer \
 && cp /fetch/mustang.jar /fetch/kosit.jar /opt/einvoice/ \
 && unzip -q /fetch/config.zip -d /opt/einvoice/kosit-config \
 && unzip -q /fetch/viewer.zip 'xsl/*' -d /opt/einvoice/viewer \
 && python3 -I /fetch/split_scenarios.py /opt/einvoice/kosit-config \
 && find /opt/einvoice -type d -exec chmod 755 {} + && find /opt/einvoice -type f -exec chmod 644 {} +

FROM base
ARG APP_VERSION=dev
LABEL org.opencontainers.image.title="E-Invoice Validator & Viewer" \
      org.opencontainers.image.description="Self-hosted validator and viewer for e-invoices (ZUGFeRD, Factur-X, XRechnung, UBL, CII) based on Mustang and the KoSIT validator. Nothing is stored." \
      org.opencontainers.image.source="https://github.com/tobiasredel/einvoice-validator" \
      org.opencontainers.image.licenses="Apache-2.0"
COPY docker/requirements.txt /tmp/requirements.txt
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv \
 && python3 -m venv /opt/py \
 && /opt/py/bin/pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
 && /opt/py/bin/pip uninstall -y pip \
 && rm -rf /var/lib/apt/lists/* /root/.cache /tmp/requirements.txt
COPY --from=fetch /opt/einvoice /opt/einvoice
COPY src /app/src
COPY web /app/web
COPY LICENSE NOTICE THIRD-PARTY-LICENSES.md /app/
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin einvoice \
 && chmod -R a-w /app /opt/einvoice
ENV PATH=/opt/py/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TMPDIR=/tmp \
    MUSTANG_VERSION=2.26.0 KOSIT_VERSION=1.6.3 KOSIT_CONFIG_VERSION=2026-08-31 VIEWER_VERSION=2026-10-13 APP_VERSION=${APP_VERSION}
USER 10001:10001
WORKDIR /tmp
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-I", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]
ENTRYPOINT ["python", "/app/src/server.py"]
