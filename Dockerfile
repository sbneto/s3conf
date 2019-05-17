FROM python:3.6-alpine

ENV PYINSTALLER_VERSION=3.4

RUN apk --update --no-cache add \
    zlib-dev \
    musl-dev \
    libc-dev \
    gcc \
    git \
    pwgen \
    && pip install --upgrade pip

#RUN apt-get update \
#    && echo "deb http://ftp.linux-foundation.org/pub/lsb/repositories/debian lsb-4.0 main" >> /etc/apt/sources.list \
#    && apt-get update \
#    && apt-get install -y --no-install-recommends --allow-unauthenticated \
#        build-essential \
#        libc6-dev \
#        zlib1g-dev \
#        git \
#        lsb lsb-build-cc \
#    && apt-get autoremove -yqq \
#    && apt-get clean \
#    && rm -Rf /tmp/* /var/tmp/* /var/lib/apt/lists/*

# Install pycrypto so --key can be used with PyInstaller
RUN pip install \
    pycrypto pyinstaller

# Build bootloader for alpine
# https://github.com/six8/pyinstaller-alpine/pull/6
RUN mkdir /tmp/pyinstaller \
    && cd /tmp/pyinstaller \
    && wget https://github.com/pyinstaller/pyinstaller/archive/v$PYINSTALLER_VERSION.zip \
    && unzip -d . v$PYINSTALLER_VERSION.zip \
    && cd /tmp/pyinstaller/pyinstaller-$PYINSTALLER_VERSION/bootloader \
    && CFLAGS="-Wno-stringop-overflow" python ./waf --no-lsb configure all \
    && pip install .. \
    && rm -Rf /tmp/pyinstaller