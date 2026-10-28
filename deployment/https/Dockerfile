FROM caddy:2.11.7-alpine@sha256:eb4d35b7452d1ab6171fbdbe8d9275b2301dad6dad92115d91e19fb9b24d510f
RUN setcap -r /usr/bin/caddy && addgroup -g 10001 nexo && adduser -D -u 10001 -G nexo nexo && chown -R nexo:nexo /data /config
USER 10001:10001
