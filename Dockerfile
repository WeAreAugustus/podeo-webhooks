# Podeo Upload - Flask app that converts podcast MP3 → MP4 and uploads to Smashi/Lovin
# Base: Python 3.12 on Debian (slim = smaller image, no ffmpeg by default)
FROM python:3.12-slim

# Install ffmpeg (required for MP3→MP4 conversion)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching when code changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and static data
COPY app.py .
COPY image.png .
COPY resources/ resources/
COPY utils/ utils/
COPY webhook/ webhook/
COPY data/ data/

# Optional: run as non-root (create user and chown)
# RUN useradd -m appuser && chown -R appuser:appuser /app
# USER appuser

EXPOSE 5000

# Flask listens on 0.0.0.0 so it accepts connections from outside the container
ENV FLASK_APP=app.py
CMD ["python", "app.py"]
