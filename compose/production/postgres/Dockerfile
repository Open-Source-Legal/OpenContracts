FROM pgvector/pgvector:0.8.2-pg15

# init.sql enables the pgvector extension and configures HNSW iterative scan
# settings on fresh databases. Existing databases get these via migration 0063.
COPY ./compose/production/postgres/init.sql /docker-entrypoint-initdb.d/init.sql

# Shared postgres config (single source of truth) + entrypoint wrapper that
# injects shared.conf values as postgres -c flags on every startup.
COPY ./compose/postgres/shared.conf /etc/postgresql-custom/shared.conf
COPY ./compose/postgres/docker-entrypoint-wrapper.sh /usr/local/bin/docker-entrypoint-wrapper.sh
RUN chmod +x /usr/local/bin/docker-entrypoint-wrapper.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint-wrapper.sh"]
CMD ["postgres"]

COPY ./compose/production/postgres/maintenance /usr/local/bin/maintenance
RUN chmod +x /usr/local/bin/maintenance/*
RUN mv /usr/local/bin/maintenance/* /usr/local/bin \
    && rmdir /usr/local/bin/maintenance
