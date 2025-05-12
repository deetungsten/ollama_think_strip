FROM openresty/openresty:jammy

RUN apt-get update && \
    apt-get install -y git && \
    cd /tmp && \
    git clone https://github.com/ledgetech/lua-resty-http && \
    cd lua-resty-http && \
    cp -r lib/resty /usr/local/openresty/lualib/ && \
    rm -rf /tmp/lua-resty-http && \
    apt-get remove -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*