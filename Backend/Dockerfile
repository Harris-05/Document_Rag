# Backend image for Fly.io (or any container host).
#
# One instance only: documents live in SQLite and the search index is cached in this process, so the
# data directory must be a persistent volume mounted at /data and the app must not be scaled out.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data

# Liberation Sans (regular, bold and italic) is the font the PDF export uses, so accented letters and
# typographic quotes are not lost. DejaVu's core package has no italic, so it is not used here.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8080

# A single worker on purpose (see above). The platform's proxy provides TLS.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
