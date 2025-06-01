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

# Set environment variables (these will be overridden by docker run -e flags)
# It's good practice to set defaults or placeholders here if any.
# DISCORD_BOT_TOKEN should NOT be hardcoded here. It must be provided at runtime.
ENV WELCOME_CHANNEL_ID="0"
ENV VERIFIED_ROLE_NAME="verified"
ENV VERIFICATION_TIMEOUT_SECONDS="300"
ENV MIN_ACCOUNT_AGE_DAYS="90"
ENV BOT_STATUS_MESSAGE="Watching for new members..."
ENV OFFLINE_CATCHUP_WINDOW_SECONDS="1200"
ENV WELCOME_MESSAGE="Welcome {member_mention} to **{guild_name}**! Please check out {specific_channel_mention}!"
ENV GOODBYE_MESSAGE="**{member_name}** just left **{guild_name}**."
ENV BATCH_WELCOME_MESSAGE="While the bot was offline, the following members joined: **{member_mentions_list}**, welcome to **{guild_name}**!"
ENV BATCH_GOODBYE_MESSAGE="While the bot was offline, the following members left: **{member_names_list}**."

# Inform Docker that the container listens on a specific port (optional, informational)
# For a Discord bot, it doesn't listen on a port for incoming HTTP, but connects outbound.
# So, EXPOSE is not strictly necessary here.

# Define the command to run your bot when the container starts
CMD ["python", "bot.py"]
