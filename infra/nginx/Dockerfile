FROM nginx:1.27-alpine

# cleanup default nginx html
RUN rm -rf /usr/share/nginx/html/*

# copy dist files into nginx
COPY apps/web/dist/ /usr/share/nginx/html/

# copy nginx config
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf

# Static error pages (502/503/504); compose may also bind-mount this path in dev
COPY infra/nginx/error-pages/ /usr/share/nginx/error-pages/
