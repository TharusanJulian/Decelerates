FROM python:3.11-slim

# Set working directory
WORKDIR /app

# System deps for psycopg2
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Environment
ENV PYTHONUNBUFFERED=1

# Expose port for FastAPI
EXPOSE 8000

# Default command: run FastAPI (uvicorn)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
