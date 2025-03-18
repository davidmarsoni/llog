# Use Python 3.10 slim image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Generate the static CSS files
RUN apt-get update && apt-get install -y nodejs npm
RUN npm install
RUN npx tailwindcss -i ./static/src/input.css -o ./static/css/tailwind.css

# Set environment variables
ENV FLASK_APP=app.py
ENV PORT=8080

# Create a startup script with GCS connectivity check and proper Gunicorn config
RUN echo '#!/bin/sh\n\
echo "Checking GCS connectivity..."\n\
python -c "import os; from google.cloud import storage; \
client = storage.Client(); \
try: \
    bucket = client.bucket(os.environ[\"GCS_BUCKET_NAME\"]); \
    print(f\"Connected to bucket {os.environ[\"GCS_BUCKET_NAME\"]}\"); \
except Exception as e: \
    print(f\"Error connecting to GCS: {str(e)}\"); \
    exit(1)\
"\n\
# Run with increased max request size and timeout\n\
exec gunicorn --bind :$PORT \
    --timeout 600 \
    --workers 2 \
    --threads 8 \
    --worker-tmp-dir /dev/shm \
    --max-requests 500 \
    --max-requests-jitter 50 \
    --limit-request-line 0 \
    --limit-request-fields 0 \
    --limit-request-field_size 0 \
    --worker-class gthread \
    app:app' > /app/startup.sh && chmod +x /app/startup.sh

CMD ["/app/startup.sh"]