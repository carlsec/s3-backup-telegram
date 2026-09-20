FROM python:3.12-slim

ENV SUPERCRONIC_VERSION=v0.2.49 \
    SUPERCRONIC_SHA1SUM_AMD64=e63c11a9726b775a6a11801e81af4f3fb926aa68 \
    SUPERCRONIC_SHA1SUM_ARM64=0b6c5bb743e0b0dafed1132198c81807927ac413

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

# AWS CLI v2, official installer (not `pip install awscli`) so `aws s3 sync`
# behaves exactly as it does in production elsewhere.
RUN ARCH="$(dpkg --print-architecture)" \
    && case "$ARCH" in \
        amd64) AWSCLI_ARCH="x86_64" ;; \
        arm64) AWSCLI_ARCH="aarch64" ;; \
        *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${AWSCLI_ARCH}.zip" -o /tmp/awscliv2.zip \
    && unzip -q /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/awscliv2.zip /tmp/aws

# supercronic, pinned + checksummed against the official release
# (https://github.com/aptible/supercronic/releases/tag/v0.2.49)
RUN ARCH="$(dpkg --print-architecture)" \
    && case "$ARCH" in \
        amd64) SUPERCRONIC_BIN="supercronic-linux-amd64"; SHA1="$SUPERCRONIC_SHA1SUM_AMD64" ;; \
        arm64) SUPERCRONIC_BIN="supercronic-linux-arm64"; SHA1="$SUPERCRONIC_SHA1SUM_ARM64" ;; \
        *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSLO "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/${SUPERCRONIC_BIN}" \
    && echo "${SHA1}  ${SUPERCRONIC_BIN}" | sha1sum -c - \
    && chmod +x "${SUPERCRONIC_BIN}" \
    && mv "${SUPERCRONIC_BIN}" /usr/local/bin/supercronic

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY docker/crontab.template ./docker/crontab.template
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
