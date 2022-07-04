FROM alpine:latest

RUN apk update \
    && apk upgrade \
    && apk add --no-cache \
            gstreamer \
            mopidy \
            py-pip \
            alpine-sdk \
            python3-dev\
            dumb-init \
            curl

# Default configuration
RUN pip3 install --upgrade pip

COPY docker/config/requirements.txt requirements.txt
RUN pip3 install -r requirements.txt \
    && rm -rf ~/.cache/pip

ADD . /src
RUN pip3 install /src/

# Set default environment variables
ENV TZ=Europe/Budapest
ENV HOME=/home/mopidy

# Create directories
RUN mkdir -p /music $HOME

# Copy mopidy.conf
COPY docker/config/mopidy.conf $HOME/.config/mopidy/mopidy.conf

# Set flie permissions
RUN chown mopidy:audio -R /music $HOME

# Add user mopidy to group audio
RUN addgroup mopidy audio

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
