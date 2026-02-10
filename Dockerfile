# 1. Use an official Python runtime as a parent image
FROM python:3.11-slim

# 2. Install system dependencies (FFmpeg is crucial here!)
RUN apt-get update && \
    apt-get install -y ffmpeg git && \
    rm -rf /var/lib/apt/lists/*

# 3. Set the working directory in the container
WORKDIR /app

# 4. Copy the requirements file into the container
COPY requirements.txt .

# 5. Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of the code
COPY . .

# 7. Create the static directory (just in case)
RUN mkdir -p static

# 8. Expose the port the app runs on
EXPOSE 8000

# 9. Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
