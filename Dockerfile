FROM alpine:latest

# GStreamer and its Python bindings come from Alpine; Mopidy itself comes
# from PyPI (requirements.txt), as the Alpine mopidy package lags behind.
RUN apk update \
    && apk upgrade \
    && apk add --no-cache \
            gstreamer \
            gst-plugins-base \
            gst-plugins-good \
            gst-plugins-ugly \
            gst-plugins-bad \
            py3-gobject3 \
            py3-gst \
            py-pip \
            alpine-sdk \
            python3-dev\
            dumb-init \
            curl \
    && adduser -S -D -H -h /home/mopidy -G audio mopidy

# pip installs into the system Python so it can use the GStreamer bindings
# from apk. Alpine marks it as externally managed (PEP 668), hence
# --break-system-packages.
COPY docker/config/requirements.txt requirements.txt
RUN pip3 install --break-system-packages -r requirements.txt \
    && rm -rf ~/.cache/pip

ADD . /src
RUN pip3 install --break-system-packages /src/ \
    && rm -rf ~/.cache/pip

# Set default environment variables
ENV TZ=Europe/Budapest
ENV HOME=/home/mopidy

# Create directories
RUN mkdir -p /music $HOME

# Copy mopidy.conf
COPY docker/config/mopidy.conf $HOME/.config/mopidy/mopidy.conf

# Set flie permissions
RUN chown mopidy:audio -R /music $HOME

# Optional: add user mopidy to wheel group to enable sudo
#RUN apk add --no-cache sudo && addgroup mopidy wheel

# Run as user mopidy
USER mopidy

# Basic check,
RUN /usr/bin/dumb-init /usr/bin/mopidy --version

EXPOSE 6680

ENTRYPOINT ["/usr/bin/dumb-init"]
CMD ["/usr/bin/mopidy"]

HEALTHCHECK --interval=5s --timeout=2s --retries=20 \
    CMD curl --connect-timeout 5 --silent --show-error --fail http://localhost:6680/ || exit 1
