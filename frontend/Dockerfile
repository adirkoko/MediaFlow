FROM nginx:1.27-alpine

WORKDIR /usr/share/nginx/html

COPY index.html ./index.html
COPY js ./js
COPY assets ./assets
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.d/40-runtime-config.sh /docker-entrypoint.d/40-runtime-config.sh

RUN chmod +x /docker-entrypoint.d/40-runtime-config.sh

EXPOSE 80
