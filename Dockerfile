# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code
COPY . .

# Create necessary directories for the app if they don't exist (though main.py handles this too)
RUN mkdir -p uploads outputs

# Expose the port that the app runs on
EXPOSE 4444

# Prevent Python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE 1
# Ensure python output is sent straight to terminal (container logs) without buffering
ENV PYTHONUNBUFFERED 1

# Copy the startup script and make it executable
COPY run_railway.sh .
RUN chmod +x run_railway.sh

# Define the command to run the app using the script
CMD ["./run_railway.sh"]
