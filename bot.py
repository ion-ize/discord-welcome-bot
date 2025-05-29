import discord
import os
import asyncio
from datetime import datetime, timedelta, timezone

# --- Configuration ---
# Load from environment variables. Ensure these are set in your Docker environment.
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
WELCOME_CHANNEL_ID = int(os.getenv('WELCOME_CHANNEL_ID', '0')) # Channel ID to send welcome messages
VERIFIED_ROLE_NAME = os.getenv('VERIFIED_ROLE_NAME', 'verified') # Name of the role to check for
VERIFICATION_TIMEOUT_SECONDS = int(os.getenv('VERIFICATION_TIMEOUT_SECONDS', '600')) # e.g., 300 for 5 minutes
MIN_ACCOUNT_AGE_DAYS = int(os.getenv('MIN_ACCOUNT_AGE_DAYS', '90')) # e.g., 90 for 3 months
WELCOME_MESSAGE = os.getenv('WELCOME_MESSAGE', 'Welcome {member.mention} to {guild.name}!}') # Welcome message customized in env variable
GOODBYE_MESSAGE = os.getenv('GOODBYE_MESSAGE', '{member.name} just left {guild.name}.') # Goodbye message customized in env variable


# --- Bot Setup ---
intents = discord.Intents.default()
intents.members = True  # Required to receive member join/update events and access member.created_at
intents.guilds = True   # Required for guild information
# Consider adding intents.message_content if you plan to add command-based interactions later.

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
        print(f"{get_log_prefix()} Kicked member {member.name} (ID: {member.id}). Reason: {reason}")
    except discord.Forbidden:
        print(f"{get_log_prefix()} ERROR: Bot lacks permission to kick {member.name} (ID: {member.id}).")
    except discord.HTTPException as e:
        print(f"{get_log_prefix()} ERROR: Failed to kick {member.name} (ID: {member.id}): {e}")

# --- Core Logic Task ---
async def kick_if_not_verified(member: discord.Member):
    """
    Waits for VERIFICATION_TIMEOUT_SECONDS. If the member is still in the server
    and does not have the VERIFIED_ROLE_NAME, they are kicked.
    This task is cancelled if the member gets verified before the timeout.
    """
    await asyncio.sleep(VERIFICATION_TIMEOUT_SECONDS)

    # Ensure the task hasn't been cancelled (e.g., by member getting verified)
    # and that the member is still in our pending list.
    # The presence in pending_verification_tasks implies it wasn't cancelled.
    if member.id not in pending_verification_tasks:
        # Task was likely cancelled because the user was verified or left.
        # Or this is a stray task somehow.
        print(f"{get_log_prefix()} Verification task for {member.name} (ID: {member.id}) no longer relevant or already handled.")
        return

    try:
        # Re-fetch member to ensure their roles are up-to-date and they are still in the guild
        guild = member.guild
        fresh_member = await guild.fetch_member(member.id)

        if fresh_member: # Member is still in the guild
            verified_role = discord.utils.get(fresh_member.roles, name=VERIFIED_ROLE_NAME)
            if not verified_role:
                timeout_reason = f"Not verified with the '{VERIFIED_ROLE_NAME}' role within {VERIFICATION_TIMEOUT_SECONDS / 60:.1f} minutes."
                await kick_member(fresh_member, timeout_reason)
            else:
                # This case should ideally be caught by on_member_update,
                # but as a safeguard, if they got verified and on_member_update somehow missed it or was delayed.
                print(f"{get_log_prefix()} Member {fresh_member.name}#{fresh_member.discriminator} (ID: {fresh_member.id}) was already verified by timeout check. Welcome should have been sent.")
        else:
            # Member left the server before timeout
            print(f"{get_log_prefix()} Member {member.name} (ID: {member.id}) left before verification timeout.")

    except discord.NotFound:
        # Member left the server or was kicked by other means before timeout
        print(f"{get_log_prefix()} Member {member.name} (ID: {member.id}) not found. Likely left or was kicked before verification timeout.")
    except discord.Forbidden:
        print(f"{get_log_prefix()} ERROR: Bot lacks permission to fetch or kick member {member.name} (ID: {member.id}) during timeout check.")
    except Exception as e:
        print(f"{get_log_prefix()} ERROR: An unexpected error occurred in kick_if_not_verified for {member.name} (ID: {member.id}): {e}")
    finally:
        # Clean up the task from the pending dictionary
        if member.id in pending_verification_tasks:
            del pending_verification_tasks[member.id]
            print(f"{get_log_prefix()} Removed verification task for {member.name} (ID: {member.id}) after timeout check.")


# --- Event Handlers ---
@client.event
async def on_ready():
    print(f'{get_log_prefix()} Bot logged in as {client.user.name}')
    print(f'{get_log_prefix()} Watching for new members...')
    if WELCOME_CHANNEL_ID == 0:
        print(f"{get_log_prefix()} WARNING: WELCOME_CHANNEL_ID is not set. Welcome messages will not be sent.")
    if not VERIFIED_ROLE_NAME:
        print(f"{get_log_prefix()} WARNING: VERIFIED_ROLE_NAME is not set. Role verification might not work as expected.")


@client.event
async def on_member_join(member: discord.Member):
    print(f"{get_log_prefix()} Member joined: {member.name} (ID: {member.id}, Account Created: {member.created_at})")

    # 1. Check account age
    account_age = datetime.now(timezone.utc) - member.created_at
    if account_age.days < MIN_ACCOUNT_AGE_DAYS:
        age_kick_reason = f"Account is too new (created {account_age.days} days ago, minimum is {MIN_ACCOUNT_AGE_DAYS} days)."
        await kick_member(member, age_kick_reason)
        return # Stop further processing for this member

    # 2. If account age is okay, start monitoring for verification
    # Check if a task already exists (e.g., rapid rejoin) - though unlikely to be an issue with member object identity.
    if member.id in pending_verification_tasks:
        print(f"{get_log_prefix()} Warning: Verification task already exists for {member.name} (ID: {member.id}). This might indicate a rapid rejoin or an issue.")
        # Optionally, cancel the old task and start a new one, or just let it be.
        # For simplicity, we'll let the old one run its course or be cancelled by on_member_update.

    # Create a task that will kick the member if they are not verified in time
    task = asyncio.create_task(kick_if_not_verified(member))
    pending_verification_tasks[member.id] = task
    print(f"{get_log_prefix()} Scheduled verification timeout task for {member.name} (ID: {member.id}). Timeout: {VERIFICATION_TIMEOUT_SECONDS}s.")


@client.event
async def on_member_update(before: discord.Member, after: discord.Member):
    # Check if the member was pending verification
    if after.id not in pending_verification_tasks:
        return # Not a member we are currently monitoring for initial verification

    guild = after.guild
    verified_role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)

    if not verified_role:
        print(f"{get_log_prefix()} ERROR: Verified role '{VERIFIED_ROLE_NAME}' not found in guild '{guild.name}'. Cannot process verification.")
        # Potentially remove from pending_verification_tasks or let timeout handle it,
        # as verification is impossible without the role existing.
        return

    # Check if the 'verified' role was ADDED
    was_verified_before = verified_role in before.roles
    is_verified_now = verified_role in after.roles

    if not was_verified_before and is_verified_now:
        print(f"{get_log_prefix()} Member {after.name} (ID: {after.id}) received the '{VERIFIED_ROLE_NAME}' role.")

        # Cancel the pending kick task for this member
        task = pending_verification_tasks.pop(after.id, None)
        if task:
            task.cancel()
            try:
                await task # Wait for task to acknowledge cancellation
            except asyncio.CancelledError:
                print(f"{get_log_prefix()} Successfully cancelled verification timeout task for {after.name} (ID: {after.id}).")
        else:
            print(f"{get_log_prefix()} Warning: No pending verification task found to cancel for {after.name} (ID: {after.id}) upon role update. Welcome will still be sent.")


        # Send welcome message
        if WELCOME_CHANNEL_ID != 0:
            welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
            if welcome_channel and isinstance(welcome_channel, discord.TextChannel):
                try:
                    welcome_message_formatted = f"{WELCOME_MESSAGE}"
                    await welcome_channel.send(welcome_message_formatted)
                    print(f"{get_log_prefix()} Sent welcome message for {after.name} (ID: {after.id}) to channel ID {WELCOME_CHANNEL_ID}.")
                except discord.Forbidden:
                    print(f"{get_log_prefix()} ERROR: Bot lacks permission to send messages to welcome channel ID {WELCOME_CHANNEL_ID}.")
                except discord.HTTPException as e:
                    print(f"{get_log_prefix()} ERROR: Failed to send welcome message for {after.name} (ID: {after.id}): {e}")
            else:
                print(f"{get_log_prefix()} ERROR: Welcome channel ID {WELCOME_CHANNEL_ID} not found or is not a text channel.")
        else:
            print(f"{get_log_prefix()} Welcome channel ID not configured. Skipping welcome message for {after.name} (ID: {after.id}).")

@client.event
async def on_member_remove(member: discord.Member):
    if WELCOME_CHANNEL_ID != 0:
        welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
        if welcome_channel and isinstance(welcome_channel, discord.TextChannel):
            try:
                goodbye_message_formatted = f"{GOODBYE_MESSAGE}"
                await welcome_channel.send(goodbye_message_formatted)
                print(f"{get_log_prefix()} Sent goodbye message for {member.name} (ID: {member.id}) to channel ID {WELCOME_CHANNEL_ID}.")
            except discord.Forbidden:
                print(f"{get_log_prefix()} ERROR: Bot lacks permission to send messages to welcome channel ID {WELCOME_CHANNEL_ID}.")
            except discord.HTTPException as e:
                print(f"{get_log_prefix()} ERROR: Failed to send goodbye message for {member.name} (ID: {member.id}): {e}")
        else:
            print(f"{get_log_prefix()} ERROR: Welcome channel ID {WELCOME_CHANNEL_ID} not found or is not a text channel.")
    else:
        print(f"{get_log_prefix()} Welcome channel ID not configured. Skipping goodbye message for {member.name} (ID: {member.id}).")
    # If a member leaves or is kicked, and they had a pending verification task, cancel it.
    if member.id in pending_verification_tasks:
        task = pending_verification_tasks.pop(member.id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass # Expected
            print(f"{get_log_prefix()} Member {member.name} (ID: {member.id}) left/was kicked. Cancelled their pending verification task.")


# --- Main Execution ---
if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print(f"{get_log_prefix()} ERROR: DISCORD_BOT_TOKEN environment variable not set. Bot cannot start.")
    elif WELCOME_CHANNEL_ID == 0:
        print(f"{get_log_prefix()} WARNING: WELCOME_CHANNEL_ID environment variable is not set or is invalid. Welcome messages will not be sent to a specific channel.")
    elif not VERIFIED_ROLE_NAME:
        print(f"{get_log_prefix()} WARNING: VERIFIED_ROLE_NAME environment variable is not set. Role verification may not work as expected.")
    else:
        try:
            client.run(DISCORD_BOT_TOKEN)
        except discord.LoginFailure:
            print(f"{get_log_prefix()} ERROR: Login failed. Check if DISCORD_BOT_TOKEN is correct.")
        except Exception as e:
            print(f"{get_log_prefix()} ERROR: An unexpected error occurred while trying to run the bot: {e}")
