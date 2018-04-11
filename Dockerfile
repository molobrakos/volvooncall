FROM python:3.6-slim

WORKDIR /app

RUN set -x \
&& apt-get update \
&& apt-get -y install git libsodium13 \
&& apt-get -y autoremove \
&& apt-get -y clean \
&& rm -rf /var/lib/apt/lists/* \
&& rm -rf /tmp/* \
&& rm -rf /var/tmp/* \
&& useradd -M --home-dir /app voc \
  ;

COPY requirements.txt ./

RUN pip --no-cache-dir --trusted-host pypi.org install -r requirements.txt coloredlogs libnacl \
  && rm requirements.txt \
  ;

USER voc

COPY voc volvooncall.py mqtt.py ./
