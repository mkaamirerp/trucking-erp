FROM nginx:1.27-alpine

# cleanup default nginx html
RUN rm -rf /usr/share/nginx/html/*

# copy dist files into nginx
COPY apps/web/dist/ /usr/share/nginx/html/

# copy nginx config
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
