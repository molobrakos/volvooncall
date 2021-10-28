FROM python:3.10-slim-bullseye

ADD . /app
WORKDIR /app

RUN set -x \
&& apt-get update \
&& apt-get -y --no-install-recommends install dumb-init libsodium18 \
&& apt-get -y autoremove \
&& apt-get -y clean \
&& rm -rf /var/lib/apt/lists/* \
&& rm -rf /tmp/* \
&& rm -rf /var/tmp/* \
&& useradd -M --home-dir /app voc \
  ;

RUN pip --no-cache-dir --trusted-host pypi.org install --upgrade -r /app/requirements.txt pip coloredlogs libnacl \
  && pip install /app && rm -rf /app \
  ;

USER voc

ENTRYPOINT ["dumb-init", "--", "voc", "mqtt"]
