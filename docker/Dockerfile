FROM python:3.12-slim

ENV SUPERCRONIC_VERSION=v0.2.49 \
    SUPERCRONIC_SHA1SUM_AMD64=e63c11a9726b775a6a11801e81af4f3fb926aa68 \
    SUPERCRONIC_SHA1SUM_ARM64=0b6c5bb743e0b0dafed1132198c81807927ac413 \
    S5CMD_VERSION=v2.3.0 \
    S5CMD_SHA256SUM_AMD64=de0fdbfa3aceae55e069ba81a0fc17b2026567637603734a387b2fca06c299b4 \
    S5CMD_SHA256SUM_ARM64=1439f0d00ecedcd2a2f1f2c6749bbb0152b2257bf5086f29646ec8ae38798e24

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# s5cmd, pinned + checksummed against the official release
# (https://github.com/peak/s5cmd/releases/tag/v2.3.0). Used instead of
# `aws s3 sync`: for buckets with hundreds of thousands of objects, the
# Python/GIL-bound aws-cli is documented to be an order of magnitude slower
# than s5cmd's parallel Go implementation for this exact workload shape
# (many objects, not few huge ones) — see README.md "Why s5cmd".
RUN ARCH="$(dpkg --print-architecture)" \
    && case "$ARCH" in \
        amd64) S5CMD_ARCH="Linux-64bit"; SHA256="$S5CMD_SHA256SUM_AMD64" ;; \
        arm64) S5CMD_ARCH="Linux-arm64"; SHA256="$S5CMD_SHA256SUM_ARM64" ;; \
        *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;; \
    esac \
    && S5CMD_TARBALL="s5cmd_${S5CMD_VERSION#v}_${S5CMD_ARCH}.tar.gz" \
    && curl -fsSLO "https://github.com/peak/s5cmd/releases/download/${S5CMD_VERSION}/${S5CMD_TARBALL}" \
    && echo "${SHA256}  ${S5CMD_TARBALL}" | sha256sum -c - \
    && tar -xzf "${S5CMD_TARBALL}" s5cmd \
    && chmod +x s5cmd \
    && mv s5cmd /usr/local/bin/s5cmd \
    && rm -f "${S5CMD_TARBALL}"

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
