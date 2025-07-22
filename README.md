# Discord Welcome Bot
This is a discord bot that is built with python using the discord python module and is designed to be run inside of a docker container. This bot only makes outbound network connections so it can be self hosted without much concern.

# Features:

- This is a discord bot that will set a timeout period from when a user joins the server for them to verify before they are kicked.
- This will also send a welcome message AFTER they are verified.
- If a verified user leaves the server then it will also send a goodbye message.
- If a user's account is not older than the minimum required account age then it will automatically kick them.

# Additional Note(s): 

On our server we use this bot in tandom with the [MEE6 bot](https://mee6.xyz/) that runs the actual verification process. This should work with any other verification bot as long as there is a role added to a user as part of the verification that you specify in an environment variable. This bot does not process verifications on its own.

# Intents
Go to the [Discord Developer Portal](https://discord.com/developers/applications) and select your bot. Now move to the bot tab and scroll down. There you should see ```Priveledged Gateway Intents```. Enable all of the intents listed.

### Environment Variables
This will use the default environment variables and will not work natively due to missing the bot API token. The following parameters are available to be set:
- DISCORD_BOT_TOKEN
  - The API token of the bot from the [Discord Developer Portal](https://discord.com/developers/applications).
- WELCOME_CHANNEL_ID
  - The channel ID of the desired discord channel that will have the different messages sent into it.
- VERIFIED_ROLE_NAME
  - The name of the role used to check user verification.
- VERIFICATION_TIMEOUT_SECONDS
  - The time in seconds after witch to kick a user if they did not become verified. This defaults to 300 seconds (5 minutes) if no value is set.
- MIN_ACCOUNT_AGE_DAYS
  - The minimum account age required to join the server. This is not the persons age but rather how long it has been since they created their discord account.
- MENTION_CHANNEL_NAME
  - The name of the specific channel to mention if you use this in your welcome message. This is the plain text name not the channel ID since it will output the plain text channel name if the channel could not be mentioned.
- BOT_STATUS_MESSAGE
  - The status message to have the bot display, for fun.
- OFFLINE_CATCHUP_WINDOW_SECONDS
  - This is the default catchup window that the bot will look back to check for events prior to starting if no last online status was saved. This will default to VERIFICATION_TIMEOUT_SECONDS * 2.
- WELCOME_MESSAGE
  - The welcome message to send in the specified channel. The following variables are accepted: {member_mention}, {guild_name}, and {specific_channel_mention}. Discord formatting is processed, here is an example message:
```Welcome {member_mention} to **{guild_name}**! Please check out {specific_channel_mention}!```
- GOODBYE_MESSAGE
  - The goodbye message to send in the specified channel. The following variables are accepted: {member_name}, and {guild_name}. Same as above, discord formatting is accepted, here is an example message:
```**{member_name}** just left **{guild_name}**.```
- QUICK_LEAVE_TIMEOUT_SECONDS
  - The time in seconds after a user joins that a special goodbye message will be used if they leave. This defaults to 600 seconds (10 minutes) if no value is set.
- QUICK_LEAVE_GOODBYE_MESSAGE
  - The special goodbye message to send if a user leaves within the `QUICK_LEAVE_TIMEOUT_SECONDS` window. If this is not set, the standard `GOODBYE_MESSAGE` will always be used. It accepts the same variables as `GOODBYE_MESSAGE`. Here is an example:
```**{member_name}** just left **{guild_name}**. https://tenor.com/view/grandpa-abe-exit-confused-bye-bart-gif-7694184```
- BATCH_WELCOME_MESSAGE
  - The batch welcome message to send in the specified channel if multiple users joined and became verfified while the bot was offline. The following variables are accepted: {member_mentions_list}, {guild_name}, and {specific_channel_mention}. Discord formatting is processed, here is an example message:
```While the bot was offline, the following members joined: **{member_mentions_list}**, welcome to **{guild_name}**!```
- BATCH_GOODBYE_MESSAGE
  - The batch goodbye message to send in the specified channel if multiple users that were verfified left while the bot was offline. The following variables are accepted: {member_names_list}. Discord formatting is processed, here is an example message:
```While the bot was offline, the following members left: **{member_names_list}**.```

While you can hard code these variables into the bot script, that is not ideal, especially with the API token.

# Docker Instructions
## Install the hole-welcome-bot as a docker container on a linux server
### Building the image
Clone the repository onto the docker host in your desired location:
```
git clone https://github.com/ion-ize/discord-welcome-bot.git
cd discord-welcome-bot
```

Run the following command to build the Docker image from the source code:

```docker build -t discord-welcome-bot .```

The image will now be listed by Docker. You can confirm this by running:

```docker images```

### Create a writeable container from the image

```docker create --name discord-welcome-bot discord-welcome-bot```

Please set up the environment variables listed above [here](#environment-variables) on your docker container for this bot to properly run.

See the docker documentation [here](https://docs.docker.com/reference/cli/docker/container/run/#env) for more details on setting those environment variables up.

### Run the image
```docker run discord-welcome-bot```

# Local install instructions
As mentioned above, this is ideally run inside a docker container on a host server to ensure the bot is always running, but this can be run locally as well. See [here](#docker-instructions) for the docker instructions.

Make sure that you've installed Python 3.6 or higher before beginning this.

## Linux
First, we want to clone the repository using git clone:

```
git clone https://github.com/ion-ize/discord-welcome-bot.git
cd discord-welcome-bot
```

Secondly, we want to make sure python is installed on your os. This varies by distribution so I won't list instructions for that here.

Next, we will install all of the requirements:

```pip install -r requirments.txt```

Our final thing to do is run the script:

```python3 bot.py```

## Windows
You can download the latest python release from [here](https://www.python.org/downloads/windows/). 

We now want to download and extract this repository. 

After extracting, you can navigate into the folder and just double-click the bot.py file or run the following command in a terminal window ```python .\bot.py```.
