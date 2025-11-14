FROM ghcr.io/nginxinc/nginx-unprivileged:latest

# Copiar arquivo HTML de 600KB
COPY index.html /usr/share/nginx/html/

# Configurar nginx para desabilitar cache
RUN echo 'server {' > /etc/nginx/conf.d/default.conf && \
    echo '    listen 80;' >> /etc/nginx/conf.d/default.conf && \
    echo '    server_name localhost;' >> /etc/nginx/conf.d/default.conf && \
    echo '    location / {' >> /etc/nginx/conf.d/default.conf && \
    echo '        root /usr/share/nginx/html;' >> /etc/nginx/conf.d/default.conf && \
    echo '        index index.html;' >> /etc/nginx/conf.d/default.conf && \
    echo '        add_header Cache-Control "no-cache, no-store, must-revalidate" always;' >> /etc/nginx/conf.d/default.conf && \
    echo '        add_header Pragma "no-cache" always;' >> /etc/nginx/conf.d/default.conf && \
    echo '        add_header Expires "0" always;' >> /etc/nginx/conf.d/default.conf && \
    echo '    }' >> /etc/nginx/conf.d/default.conf && \
    echo '}' >> /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]