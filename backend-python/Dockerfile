FROM python:3.12-slim-bookworm

WORKDIR /app

# System dependencies for Playwright Chromium + PDF processing
# libasound2 was renamed to libasound2t64 in newer Debian — install whichever exists
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libwayland-client0 \
    libglib2.0-0 \
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-unifont \
    poppler-utils \
    tesseract-ocr \
    build-essential \
    curl \
    && (apt-get install -y --no-install-recommends libasound2t64 2>/dev/null \
        || apt-get install -y --no-install-recommends libasound2 2>/dev/null \
        || true) \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser binary
RUN playwright install chromium

# Copy application code
COPY . .

RUN mkdir -p /app/chroma_data /app/logs

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
