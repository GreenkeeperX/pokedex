FROM python:3.13-alpine

# Unprivilegierter Benutzer; /data gehört ihm, damit ein neues Volume beschreibbar ist
RUN addgroup -g 10001 app && adduser -D -H -u 10001 -G app app \
    && mkdir /data && chown app:app /data

WORKDIR /srv
COPY app ./app
COPY extra ./extra
ENV DATA_DIR=/data PORT=8789 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
VOLUME /data
EXPOSE 8789
USER 10001:10001
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s CMD wget -qO- http://127.0.0.1:8789/healthz >/dev/null || exit 1
CMD ["python", "-m", "app.server"]
