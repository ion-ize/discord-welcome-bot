# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# --no-cache-dir: Disables the cache, which can reduce image size.
# --trusted-host pypi.python.org: Sometimes needed in certain network environments.
RUN pip install --no-cache-dir --trusted-host pypi.python.org -r requirements.txt

# Copy the bot code into the container at /app
COPY bot.py .

# Set environment variables (these will be overridden by AWS settings or docker run -e flags)
# It's good practice to set defaults or placeholders here if any.
ENV WELCOME_CHANNEL_ID="0"
ENV VERIFIED_ROLE_NAME="verified"
ENV VERIFICATION_TIMEOUT_SECONDS="300"
ENV MIN_ACCOUNT_AGE_DAYS="90"
# DISCORD_BOT_TOKEN should NOT be hardcoded here. It must be provided at runtime.

# Inform Docker that the container listens on a specific port (optional, informational)
# For a Discord bot, it doesn't listen on a port for incoming HTTP, but connects outbound.
# So, EXPOSE is not strictly necessary here.

# Define the command to run your bot when the container starts
CMD ["python", "bot.py"]
