FROM nginx:alpine

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom Nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy dashboard HTML files
COPY dashboard.html /usr/share/nginx/html/dashboard.html
COPY k8s-dashboard.html /usr/share/nginx/html/k8s-dashboard.html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
