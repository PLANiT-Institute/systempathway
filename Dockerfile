# Base image with Python
FROM python:3.11-slim

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies for HiGHS
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Python dependencies including HiGHS via highspy
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install highspy

# Copy project files
COPY . .

# Run your model
CMD ["python", "main.py"]