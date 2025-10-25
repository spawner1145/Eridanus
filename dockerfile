FROM python:3.11-slim AS builder

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        git \
        build-essential \
        pkg-config \
        libcairo2-dev \
        libjpeg-dev \
        libffi-dev \
        python3-dev \
        cmake \
        meson; \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash -; \
    apt-get install -y --no-install-recommends nodejs; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /build/requirements.txt
RUN pip config set global.index-url https://pypi.org/simple/ \
    && pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install \
        -r /build/requirements.txt \
        PyJWT \
        brotli \
        qrcode \
        qrcode_terminal \
        flask_sock

FROM python:3.11-slim

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        ffmpeg \
        libjpeg-dev \
        zlib1g-dev \
        libpq-dev \
        libcairo2 \
        tzdata \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && ln -fs /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && dpkg-reconfigure --frontend noninteractive tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && npm cache clean --force

COPY --from=builder /install /usr/local
COPY . /app/Eridanus
RUN sed -i 's|ws://127.0.0.1:3001|ws://napcat:3001|g' /app/Eridanus/run/common_config/basic_config.yaml
RUN sed -i 's|redis_ip: default|redis_ip: "redis"|g' /app/Eridanus/run/common_config/basic_config.yaml

WORKDIR /app
ENV PYTHONPATH=/usr/local/lib/python3.11/site-packages
ENV TZ=Asia/Shanghai

EXPOSE 5007
CMD ["python", "Eridanus/main.py"]
