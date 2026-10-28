# Include inside the existing HTTPS domain server block. Root Flowly routes stay intact.
location = /agriscan { return 301 /agriscan/; }
location /agriscan/api/ {
    proxy_pass http://127.0.0.1:18000/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 2050m;
    client_body_timeout 180s;
    proxy_connect_timeout 10s;
    proxy_send_timeout 180s;
    proxy_read_timeout 300s;
    add_header X-Content-Type-Options nosniff always;
}
location /agriscan/workspace/ {
    root /var/www/sites;
    try_files $uri $uri/ /agriscan/workspace/index.html;
    add_header X-Content-Type-Options nosniff always;
}
location /agriscan/admin/ {
    root /var/www/sites;
    try_files $uri $uri/ /agriscan/admin/index.html;
    add_header X-Content-Type-Options nosniff always;
}
location /agriscan/downloads/ {
    root /var/www/sites;
    try_files $uri =404;
    default_type application/octet-stream;
    types { application/vnd.android.package-archive apk; application/json json; }
    add_header Cache-Control no-cache;
    add_header X-Content-Type-Options nosniff always;
}
location /agriscan/ {
    root /var/www/sites;
    try_files $uri $uri/ =404;
    index index.html;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy same-origin always;
}
