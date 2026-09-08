# Use an official Python runtime as a parent image
FROM python:3.11-slim-bookworm

# Set environmental variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Set the working directory inside the container
WORKDIR /app

# Copy requirements and wheelhouse into the container
COPY requirements.txt .
COPY wheelhouse ./wheelhouse

# Install Python dependencies using local wheels offline
RUN pip install --no-cache-dir --no-index --find-links ./wheelhouse -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the API port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
