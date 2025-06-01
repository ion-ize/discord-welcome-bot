# Welcome Bot
This is a discord bot that is built with python using the discord python module and is designed to be run inside of a docker container. This bot only makes outbound network connections so it can be self hosted without much concern.

# Features:

- This is a discord bot that will set a timeout period from when a user joins the server for them to verify before they are kicked.
- This will also send a welcome message AFTER they are verified.
- If a verified user leaves the server then it will also send a goodbye message.
- If a user's account is not older than the minimum required account age then it will automatically kick them.

# Additional Note(s): 

On our server we use this bot in tandom with the MEE6 bot that runs the actual verification process. This should work with any other verification bot as long as there is a role added to a user as part of the verification that you specify in an environment variable. This bot does not process verifications on its own.

# Intents
Go to the [Discord Developer Portal](https://discord.com/developers/applications) and select your bot. Now move to the bot tab and scroll down. There you should see ```Priveledged Gateway Intents```. Enable all of the intents listed.

# Before we begin
As mentioned above, this is ideally run inside a docker container on a host server to ensure the bot is always running, but this can be run locally as well. See [here](#docker-instructions) for the docker instructions.

# Easy: How to install the hole-welcome-bot on a home computer:
Make sure that you've installed Python 3.6 or higher before beginning this.

# Linux
First, we want to clone the repository using git clone:

```
git clone https://github.com/ion-ize/hole-welcome-bot.git
cd hole-welcome-bot
```

Secondly, we want to make sure python is installed on your os. This varies by distribution so I won't list instructions for that here.

Next, we will install all of the requirements:

```pip install -r requirments.txt```

Our final thing to do is run the script:

```python3 bot.py```

# Windows
You can download the latest python release from [here](https://www.python.org/downloads/windows/). We now want to download and extract this repository. 

After extracting, you can navigate into the folder and just double-click the file.

# Docker Instructions
## How to install the hole-welcome-bot as a docker container on a linux server
### Building the image
Copy the folder containing the Dockerfile onto the server. Go to the directory that has the Dockerfile and run the following command to build the Docker image from the source code:

```docker build -t hole-welcome-bot .```

The image will now be listed by Docker. You can confirm this by running:

```docker images```

### Create a writeable container from the image

```docker create --name hole-welcome-bot hole-welcome-bot```

This will use the default environment variables and will not work natively due to missing the bot API token. To create this with the enviroment variables you will need to specific the designed -e parameters, for example:
```
-e 'WELCOME_CHANNEL_ID'='[channel id here]'
-e 'VERIFIED_ROLE_NAME'='verified'
-e 'VERIFICATION_TIMEOUT_SECONDS'='600'
-e 'MIN_ACCOUNT_AGE_DAYS'='90'
-e 'WELCOME_MESSAGE'='Welcome {member_mention} to **{guild_name}**! Please check out {specific_channel_mention}!'
-e 'GOODBYE_MESSAGE'='**{member_name}** just left **{guild_name}**.'
-e 'DISCORD_BOT_TOKEN'='[Bot API token here]'
-e 'MENTION_CHANNEL_NAME'='[specific channel name here]'
-e 'BOT_STATUS_MESSAGE'='[bot status message here]'
```
See the docker documentation [here](https://docs.docker.com/reference/cli/docker/container/run/#env) for more details on setting those environment variables up.

### Run the image
```docker run hole-welcome-bot```
