FROM python:3.6.8-alpine3.8

ENV PYINSTALLER_VERSION=3.4

RUN apk --update --no-cache add \
    zlib-dev \
    musl-dev \
    libc-dev \
    gcc \
    git \
    pwgen \
    make \
    g++ \
    && pip install --upgrade pip

# Install pycrypto so --key can be used with PyInstaller
RUN pip install \
    pycrypto

# Build bootloader for alpine
# https://github.com/six8/pyinstaller-alpine/pull/6
RUN mkdir /tmp/pyinstaller \
    && cd /tmp/pyinstaller \
    && wget https://github.com/pyinstaller/pyinstaller/archive/v$PYINSTALLER_VERSION.zip \
    && unzip -d . v$PYINSTALLER_VERSION.zip \
    && cd /tmp/pyinstaller/pyinstaller-$PYINSTALLER_VERSION/bootloader \
    && CFLAGS="-Wno-stringop-overflow -no-pie" python ./waf distclean all --no-lsb --gcc -v \
    && cd .. \
    && python setup.py install \
    && rm -Rf /tmp/pyinstaller

COPY . /app
WORKDIR /app

RUN ln -s /lib/ld-musl-x86_64.so.1 ldd \
    && pip install -r requirements.txt \
    && pyinstaller pyinstaller.py --name s3conf-$(uname -s)-$(uname -m)-alpine --onefile --hidden-import=configparser --additional-hooks-dir=hooks

# Someday it might work...
#RUN pip install patchelf-wrapper scons \
#    && CC="/usr/bin/x86_64-alpine-linux-musl-gcc" CFLAGS="-Wno-stringop-overflow -no-pie" pip https://github.com/JonathonReinhart/staticx/archive/master.zip \
#    && staticx --debug --strip dist/s3conf-$(uname -s)-$(uname -m)-alpine dist/s3conf
