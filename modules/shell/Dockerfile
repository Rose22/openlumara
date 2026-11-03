FROM debian:stable

# env variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# update
RUN apt-get update

# Set locale to en_US.UTF-8 and timezone to UTC
# thanks to agentzero's team (https://github.com/agent0ai/agent-zero) for figuring this out,
# i copied it from them
RUN apt-get install -y locales tzdata
RUN sed -i -e 's/# \(en_US\.UTF-8 .*\)/\1/' /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=en_US.UTF-8 LANGUAGE=en_US:en LC_ALL=en_US.UTF-8
RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime
RUN echo "UTC" > /etc/timezone
RUN dpkg-reconfigure -f noninteractive tzdata
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV TZ=UTC

# install base tools
RUN apt-get install -y --no-install-recommends \
# -------------------------------------------------------------------------------
#    enable these if you want more network connectivity,
#    but note that some of these (especially curl) make the shell more insecure
#    due to the risk of prompt injection
# -------------------------------------------------------------------------------
#    curl \
#    wget \
#    git \
#    cron \
#    procps \
#    ssh \
#    iputils-ping \
#    iproute2 \
#    net-tools \
#    lsof \
#    dnsutils \
# -------------------------------------------------------------------------------
    zip \
    unzip \
    7zip \
    tar \
    jq \
    file \
    tree \
    python3 python3-venv python3-pip \
    nodejs npm 
RUN apt-get clean

# create user and set up virtual environment
ARG UID=1000
ARG GID=1000
RUN useradd -m -u "${UID}" -s /bin/bash lumara && chown -R "${UID}:${GID}" /home/lumara
USER lumara

# set environment
ENV HOME=/home/lumara

# working directory
WORKDIR /home/lumara

# keep the container alive
CMD ["tail", "-f", "/dev/null"]
