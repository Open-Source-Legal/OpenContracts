# => Build Container
FROM node:26-alpine as builder

WORKDIR /app
COPY package.json .
COPY yarn.lock .
RUN npm install --global yarn@1.22.22 && yarn install --frozen-lockfile
COPY . .
RUN yarn build

# => Run container
FROM nginx:1.27.5-alpine

LABEL version="1.0"
LABEL description="Base docker image for Open Contracts GUI"
LABEL maintainer = ["JSIV"]

# Nginx config
RUN rm -rf /etc/nginx/conf.d
COPY conf /etc/nginx

# Static build
COPY --from=builder /app/dist /usr/share/nginx/html/

# Default Port for HTTP
EXPOSE 3000

# COPY .env file and shell script to container
WORKDIR /usr/share/nginx/html
COPY ./env.sh .

# Convert line endings and make script executable
RUN sed -i 's/\r$//' env.sh && chmod +x env.sh

# Create entrypoint script
RUN echo "#!/bin/sh" > entrypoint.sh
RUN echo "echo 'Entrypoint: Starting container'" >> entrypoint.sh
RUN echo "echo 'Entrypoint: Running env.sh'" >> entrypoint.sh
RUN echo "./env.sh" >> entrypoint.sh
RUN echo "echo 'Entrypoint: Starting Nginx'" >> entrypoint.sh
RUN echo "exec nginx -g 'daemon off;'" >> entrypoint.sh
RUN chmod +x entrypoint.sh

# Set the entrypoint
ENTRYPOINT ["/bin/sh", "/usr/share/nginx/html/entrypoint.sh"]
