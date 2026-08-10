# Use Microsoft's official Playwright Python image which contains all browser system dependencies
FROM mcr.microsoft.com/playwright/python:v1.62.0-jammy

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Expose backend port
EXPOSE 5000

# Run with Gunicorn WSGI server, 120s timeout to allow for deep image scrolling
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "120", "app:app"]
