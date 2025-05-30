import discord
import os
import asyncio
from datetime import datetime, timedelta, timezone

# --- Configuration ---
# Load from environment variables. Ensure these are set in your Docker environment.
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
WELCOME_CHANNEL_ID = int(os.getenv('WELCOME_CHANNEL_ID', '0')) # Channel ID to send welcome/goodbye messages
VERIFIED_ROLE_NAME = os.getenv('VERIFIED_ROLE_NAME', 'verified') # Name of the role to check for
VERIFICATION_TIMEOUT_SECONDS = int(os.getenv('VERIFICATION_TIMEOUT_SECONDS', '600')) # e.g., 600 for 10 minutes
MIN_ACCOUNT_AGE_DAYS = int(os.getenv('MIN_ACCOUNT_AGE_DAYS', '90')) # e.g., 90 for 3 months

# Example WELCOME_MESSAGE: "Welcome {member_mention} to {guild_name}! Please check out {specific_channel_mention}."
# If {specific_channel_mention} is used, also set MENTION_CHANNEL_NAME.
WELCOME_MESSAGE = os.getenv('WELCOME_MESSAGE', 'Welcome {member_mention} to {guild_name}!')
MENTION_CHANNEL_NAME = os.getenv('MENTION_CHANNEL_NAME', None) # Name of a specific channel to mention

# Example GOODBYE_MESSAGE: "{member_name} has left {guild_name}."
GOODBYE_MESSAGE = os.getenv('GOODBYE_MESSAGE', '{member_name} just left {guild_name}.')

# Bot status
BOT_STATUS_MESSAGE = os.getenv('BOT_STATUS_MESSAGE', 'Monitoring new members') # Default status message

# --- Bot Setup ---
intents = discord.Intents.default()
intents.members = True  # Required to receive member join/update events and access member.created_at
intents.guilds = True   # Required for guild information

client = discord.Client(intents=intents)

# In-memory store for members pending verification.
# Stores member_id: asyncio.Task (the kick_if_not_verified task)
pending_verification_tasks = {}

# --- Helper Functions ---
def get_log_prefix():
    return f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}]"

async def kick_member(member, reason):
    """Helper function to kick a member and log the action."""
    try:
        await member.kick(reason=reason)
        print(f"{get_log_prefix()} Kicked member {member.name}#{member.discriminator} (ID: {member.id}). Reason: {reason}")
    except discord.Forbidden:
        print(f"{get_log_prefix()} ERROR: Bot lacks permission to kick {member.name}#{member.discriminator} (ID: {member.id}).")
    except discord.HTTPException as e:
        print(f"{get_log_prefix()} ERROR: Failed to kick {member.name}#{member.discriminator} (ID: {member.id}): {e}")


# --- Core Logic Task ---
async def kick_if_not_verified(member: discord.Member):
    """
    Waits for VERIFICATION_TIMEOUT_SECONDS. If the member is still in the server
    and does not have the VERIFIED_ROLE_NAME, they are kicked.
    This task is cancelled if the member gets verified before the timeout.
    """
    await asyncio.sleep(VERIFICATION_TIMEOUT_SECONDS)

    if member.id not in pending_verification_tasks:
        print(f"{get_log_prefix()} Verification task for {member.name}#{member.discriminator} (ID: {member.id}) no longer relevant or already handled.")
        return

    try:
        guild = member.guild
        fresh_member = await guild.fetch_member(member.id)

        if fresh_member:
            verified_role = discord.utils.get(fresh_member.roles, name=VERIFIED_ROLE_NAME)
            if not verified_role:
                timeout_reason = f"Not verified with the '{VERIFIED_ROLE_NAME}' role within {VERIFICATION_TIMEOUT_SECONDS / 60:.1f} minutes."
                await kick_member(fresh_member, timeout_reason)
            else:
                print(f"{get_log_prefix()} Member {fresh_member.name}#{fresh_member.discriminator} (ID: {fresh_member.id}) was already verified by timeout check. Welcome should have been sent by on_member_update.")
        else:
            print(f"{get_log_prefix()} Member {member.name}#{member.discriminator} (ID: {member.id}) left before verification timeout.")

    except discord.NotFound:
        print(f"{get_log_prefix()} Member {member.name}#{member.discriminator} (ID: {member.id}) not found. Likely left or was kicked before verification timeout.")
    except discord.Forbidden:
        print(f"{get_log_prefix()} ERROR: Bot lacks permission to fetch or kick member {member.name}#{member.discriminator} (ID: {member.id}) during timeout check.")
    except Exception as e:
        print(f"{get_log_prefix()} ERROR: An unexpected error occurred in kick_if_not_verified for {member.name}#{member.discriminator} (ID: {member.id}): {e}")
    finally:
        if member.id in pending_verification_tasks:
            del pending_verification_tasks[member.id]
            print(f"{get_log_prefix()} Removed verification task for {member.name}#{member.discriminator} (ID: {member.id}) after timeout check.")


# --- Event Handlers ---
@client.event
async def on_ready():
    print(f'{get_log_prefix()} Bot logged in as {client.user.name}')
    print(f'{get_log_prefix()} Watching for new members...')
    if WELCOME_CHANNEL_ID == 0:
        print(f"{get_log_prefix()} WARNING: WELCOME_CHANNEL_ID is not set. Welcome/Goodbye messages will not be sent.")
    if not VERIFIED_ROLE_NAME:
        print(f"{get_log_prefix()} WARNING: VERIFIED_ROLE_NAME is not set. Role verification might not work as expected.")
    if MENTION_CHANNEL_NAME:
        print(f"{get_log_prefix()} Will attempt to mention channel '{MENTION_CHANNEL_NAME}' in welcome messages if placeholder is used.")

    # Set bot's online status and activity using the environment variable
    await client.change_presence(activity=discord.Game(name=BOT_STATUS_MESSAGE), status=discord.Status.online)
    print(f"{get_log_prefix()} Bot status set to Online with activity '{BOT_STATUS_MESSAGE}'.")


@client.event
async def on_member_join(member: discord.Member):
    print(f"{get_log_prefix()} Member joined: {member.name}#{member.discriminator} (ID: {member.id}, Account Created: {member.created_at})")

    account_age = datetime.now(timezone.utc) - member.created_at
    if account_age.days < MIN_ACCOUNT_AGE_DAYS:
        age_kick_reason = f"Account is too new (created {account_age.days} days ago, minimum is {MIN_ACCOUNT_AGE_DAYS} days)."
        await kick_member(member, age_kick_reason)
        return

    if member.id in pending_verification_tasks:
        print(f"{get_log_prefix()} Warning: Verification task already exists for {member.name}#{member.discriminator} (ID: {member.id}). This might indicate a rapid rejoin or an issue.")

    task = asyncio.create_task(kick_if_not_verified(member))
    pending_verification_tasks[member.id] = task
    print(f"{get_log_prefix()} Scheduled verification timeout task for {member.name}#{member.discriminator} (ID: {member.id}). Timeout: {VERIFICATION_TIMEOUT_SECONDS}s.")


@client.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if after.id not in pending_verification_tasks:
        return

    guild = after.guild
    verified_role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)

    if not verified_role:
        print(f"{get_log_prefix()} ERROR: Verified role '{VERIFIED_ROLE_NAME}' not found in guild '{guild.name}'. Cannot process verification.")
        return

    was_verified_before = verified_role in before.roles
    is_verified_now = verified_role in after.roles

    if not was_verified_before and is_verified_now:
        print(f"{get_log_prefix()} Member {after.name}#{after.discriminator} (ID: {after.id}) received the '{VERIFIED_ROLE_NAME}' role.")

        task = pending_verification_tasks.pop(after.id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                print(f"{get_log_prefix()} Successfully cancelled verification timeout task for {after.name}#{after.discriminator} (ID: {after.id}).")
        else:
            print(f"{get_log_prefix()} Warning: No pending verification task found to cancel for {after.name}#{after.discriminator} (ID: {after.id}) upon role update. Welcome will still be sent.")

        if WELCOME_CHANNEL_ID != 0:
            target_welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID) # Get the channel object

            if target_welcome_channel and isinstance(target_welcome_channel, discord.TextChannel): # Check if channel was found and is a text channel
                try:
                    specific_channel_mention_str = ""
                    if MENTION_CHANNEL_NAME:
                        target_mention_channel_obj = discord.utils.get(guild.text_channels, name=MENTION_CHANNEL_NAME)
                        if target_mention_channel_obj:
                            specific_channel_mention_str = target_mention_channel_obj.mention
                        else:
                            specific_channel_mention_str = f"#{MENTION_CHANNEL_NAME}"
                            print(f"{get_log_prefix()} WARNING: Channel named '{MENTION_CHANNEL_NAME}' not found in guild '{guild.name}'. Using plain text as fallback.")
                    
                    formatted_welcome_message = WELCOME_MESSAGE.format(
                        member_mention=after.mention,
                        guild_name=guild.name,
                        specific_channel_mention=specific_channel_mention_str
                    )
                    await target_welcome_channel.send(formatted_welcome_message) # Use the correctly named channel object
                    print(f"{get_log_prefix()} Sent welcome message for {after.name}#{after.discriminator} (ID: {after.id}) to channel ID {WELCOME_CHANNEL_ID}.")
                except discord.Forbidden:
                    print(f"{get_log_prefix()} ERROR: Bot lacks permission to send messages to welcome channel ID {WELCOME_CHANNEL_ID}.")
                except discord.HTTPException as e:
                    print(f"{get_log_prefix()} ERROR: Failed to send welcome message for {after.name}#{after.discriminator} (ID: {after.id}): {e}")
            else:
                print(f"{get_log_prefix()} ERROR: Welcome channel ID {WELCOME_CHANNEL_ID} not found or is not a text channel.")
        else:
            print(f"{get_log_prefix()} Welcome channel ID not configured. Skipping welcome message for {after.name}#{after.discriminator} (ID: {after.id}).")

@client.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    # --- New logic to check for verified role ---
    verified_role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)
    member_was_verified = verified_role and verified_role in member.roles # Check if the member had the verified role

    if member.id in pending_verification_tasks:
        task = pending_verification_tasks.pop(member.id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            print(f"{get_log_prefix()} Member {member.name}#{member.discriminator} (ID: {member.id}) left/was kicked. Cancelled their pending verification task.")
    # --- Only send goodbye message if the member was verified AND WELCOME_CHANNEL_ID is set ---
    elif member_was_verified: # Added this condition
        if WELCOME_CHANNEL_ID != 0:
            target_goodbye_channel = guild.get_channel(WELCOME_CHANNEL_ID)
            if target_goodbye_channel and isinstance(target_goodbye_channel, discord.TextChannel):
                try:
                    formatted_goodbye_message = GOODBYE_MESSAGE.format(
                        member_name=member.display_name,
                        guild_name=guild.name
                    )
                    await target_goodbye_channel.send(formatted_goodbye_message)
                    print(f"{get_log_prefix()} Sent goodbye message for {member.display_name} (ID: {member.id}) to channel ID {WELCOME_CHANNEL_ID}.")
                except discord.Forbidden:
                    print(f"{get_log_prefix()} ERROR: Bot lacks permission to send messages to channel ID {WELCOME_CHANNEL_ID} for goodbye.")
                except discord.HTTPException as e:
                    print(f"{get_log_prefix()} ERROR: Failed to send goodbye message for {member.display_name} (ID: {member.id}): {e}")
            else:
                print(f"{get_log_prefix()} ERROR: Channel ID {WELCOME_CHANNEL_ID} not found or is not a text channel for goodbye message.")
        else:
            print(f"{get_log_prefix()} Welcome channel ID not configured. Skipping goodbye message for {member.display_name} (ID: {member.id}).")
    else: # This else block handles members who left but were not verified
        print(f"{get_log_prefix()} Member {member.name}#{member.discriminator} (ID: {member.id}) left and was not verified. Skipping goodbye message.")


# --- Main Execution ---
if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print(f"{get_log_prefix()} ERROR: DISCORD_BOT_TOKEN environment variable not set. Bot cannot start.")
    elif WELCOME_CHANNEL_ID == 0:
        print(f"{get_log_prefix()} WARNING: WELCOME_CHANNEL_ID environment variable is not set or is invalid. Welcome/goodbye messages will not be sent to a specific channel.")
    elif not VERIFIED_ROLE_NAME:
        print(f"{get_log_prefix()} WARNING: VERIFIED_ROLE_NAME environment variable is not set. Role verification may not work as expected.")
    else:
        try:
            client.run(DISCORD_BOT_TOKEN)
        except discord.LoginFailure:
            print(f"{get_log_prefix()} ERROR: Login failed. Check if DISCORD_BOT_TOKEN is correct.")
        except Exception as e:
            print(f"{get_log_prefix()} ERROR: An unexpected error occurred while trying to run the bot: {e}")