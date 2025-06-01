import discord
import os
import asyncio
import sqlite3 # For persistent storage
from datetime import datetime, timedelta, timezone

# --- Configuration ---
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
WELCOME_CHANNEL_ID = int(os.getenv('WELCOME_CHANNEL_ID', '0'))
VERIFIED_ROLE_NAME = os.getenv('VERIFIED_ROLE_NAME', 'verified')
VERIFICATION_TIMEOUT_SECONDS = int(os.getenv('VERIFICATION_TIMEOUT_SECONDS', '600')) # 10 minutes
MIN_ACCOUNT_AGE_DAYS = int(os.getenv('MIN_ACCOUNT_AGE_DAYS', '90'))
# OFFLINE_CATCHUP_WINDOW_SECONDS will now act as a fallback/maximum if last_online_time is very old or not found
OFFLINE_CATCHUP_WINDOW_SECONDS = int(os.getenv('OFFLINE_CATCHUP_WINDOW_SECONDS', VERIFICATION_TIMEOUT_SECONDS * 2))
MENTION_CHANNEL_NAME = os.getenv('MENTION_CHANNEL_NAME', None)
BOT_STATUS_MESSAGE = os.getenv('BOT_STATUS_MESSAGE', 'Monitoring new members')
WELCOME_MESSAGE = os.getenv('WELCOME_MESSAGE', 'Welcome {member_mention} to **{guild_name}**!')
BATCH_WELCOME_MESSAGE = os.getenv('BATCH_WELCOME_MESSAGE', 'While the bot was offline, the following members joined: **{member_mentions_list}**, welcome to **{guild_name}**!')
GOODBYE_MESSAGE = os.getenv('GOODBYE_MESSAGE', '**{member_name}** just left **{guild_name}**.')
BATCH_GOODBYE_MESSAGE = os.getenv('BATCH_GOODBYE_MESSAGE', 'While the bot was offline, the following members left: **{member_names_list}**.')

# --- Database Setup ---
DB_NAME = 'verification_state.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verified_members (
            guild_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            verified_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, member_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_status (
            id INTEGER PRIMARY KEY,
            last_online_time TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    print(f"{get_log_prefix()} Database '{DB_NAME}' initialized.")

def mark_member_verified_in_db(guild_id: int, member_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO verified_members (guild_id, member_id, verified_at)
            VALUES (?, ?, ?)
        ''', (guild_id, member_id, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        print(f"{get_log_prefix()} Marked member {member_id} in guild {guild_id} as verified in DB.")
    except sqlite3.Error as e:
        print(f"{get_log_prefix()} DB_ERROR marking member {member_id} verified: {e}")
    finally:
        conn.close()

def remove_member_from_db(guild_id: int, member_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            DELETE FROM verified_members
            WHERE guild_id = ? AND member_id = ?
        ''', (guild_id, member_id))
        conn.commit()
        # Only log if a row was actually deleted
        if cursor.rowcount > 0:
            print(f"{get_log_prefix()} Removed member {member_id} in guild {guild_id} from DB.")
    except sqlite3.Error as e:
        print(f"{get_log_prefix()} DB_ERROR removing member {member_id}: {e}")
    finally:
        conn.close()

def was_member_verified_in_db(guild_id: int, member_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT 1 FROM verified_members
            WHERE guild_id = ? AND member_id = ?
        ''', (guild_id, member_id))
        return cursor.fetchone() is not None
    except sqlite3.Error as e:
        print(f"{get_log_prefix()} DB_ERROR checking member {member_id} verification: {e}")
        return False
    finally:
        conn.close()

def get_all_verified_member_ids_from_db(guild_id: int) -> list[int]:
    """Retrieves all member IDs marked as verified in the DB for a specific guild."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    member_ids = []
    try:
        cursor.execute('''
            SELECT member_id FROM verified_members
            WHERE guild_id = ?
        ''', (guild_id,))
        rows = cursor.fetchall()
        member_ids = [row[0] for row in rows]
    except sqlite3.Error as e:
        print(f"{get_log_prefix()} DB_ERROR getting all verified members for guild {guild_id}: {e}")
    finally:
        conn.close()
    return member_ids

def get_last_online_time() -> datetime | None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    last_online_time = None
    try:
        cursor.execute('SELECT last_online_time FROM bot_status WHERE id = 1')
        row = cursor.fetchone()
        if row:
            last_online_time = datetime.fromisoformat(row[0])
            print(f"{get_log_prefix()} Retrieved last online time from DB: {last_online_time}")
    except sqlite3.Error as e:
        print(f"{get_log_prefix()} DB_ERROR retrieving last online time: {e}")
    finally:
        conn.close()
    return last_online_time

def update_last_online_time():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    current_time = datetime.now(timezone.utc).isoformat()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO bot_status (id, last_online_time)
            VALUES (1, ?)
        ''', (current_time,))
        conn.commit()
        print(f"{get_log_prefix()} Updated last online time in DB to: {current_time}")
    except sqlite3.Error as e:
        print(f"{get_log_prefix()} DB_ERROR updating last online time: {e}")
    finally:
        conn.close()

# --- Bot Setup ---
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
client = discord.Client(intents=intents)
pending_verification_tasks = {}

# --- Helper Functions ---
def get_log_prefix():
    return f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}]"

async def kick_member(member: discord.Member, reason: str):
    guild_id = member.guild.id
    member_id = member.id
    try:
        await member.kick(reason=reason)
        print(f"{get_log_prefix()} Kicked member {member.name}#{member.discriminator} (ID: {member_id}). Reason: {reason}")
        remove_member_from_db(guild_id, member_id)
    except discord.Forbidden:
        print(f"{get_log_prefix()} ERROR: Bot lacks permission to kick {member.name}#{member.discriminator} (ID: {member_id}).")
    except discord.HTTPException as e:
        print(f"{get_log_prefix()} ERROR: Failed to kick {member.name}#{member.discriminator} (ID: {member_id}): {e}")

# --- Core Logic Task ---
async def kick_if_not_verified(member: discord.Member, initial_delay_seconds: float = None):
    actual_delay = VERIFICATION_TIMEOUT_SECONDS if initial_delay_seconds is None else initial_delay_seconds

    if actual_delay <= 0:
        print(f"{get_log_prefix()} Immediate verification check for {member.name}#{member.discriminator} (ID: {member.id}).")
    else:
        print(f"{get_log_prefix()} Scheduled verification task for {member.name}#{member.discriminator} (ID: {member.id}). Timeout: {actual_delay:.1f}s.")
        await asyncio.sleep(actual_delay)

    if member.id not in pending_verification_tasks or pending_verification_tasks[member.id].done():
        if member.id not in pending_verification_tasks:
             print(f"{get_log_prefix()} Verification task for {member.name}#{member.discriminator} (ID: {member.id}) already handled or cancelled.")
        return

    try:
        guild = member.guild
        if not guild:
            print(f"{get_log_prefix()} ERROR: Could not get guild for member {member.name} (ID: {member.id}) during kick check.")
            if member.id in pending_verification_tasks: del pending_verification_tasks[member.id]
            return

        current_member_info = await guild.fetch_member(member.id)
        if not current_member_info:
            print(f"{get_log_prefix()} Member {member.name} (ID: {member.id}) left before verification timeout completion.")
            remove_member_from_db(guild.id, member.id)
            if member.id in pending_verification_tasks: del pending_verification_tasks[member.id]
            return

        verified_role = discord.utils.get(current_member_info.roles, name=VERIFIED_ROLE_NAME)
        if not verified_role:
            timeout_reason = f"Not verified with the '{VERIFIED_ROLE_NAME}' role within the allocated time."
            await kick_member(current_member_info, timeout_reason)
        else:
            print(f"{get_log_prefix()} Member {current_member_info.name} (ID: {current_member_info.id}) was found verified by kick task.")
            mark_member_verified_in_db(guild.id, current_member_info.id)

    except discord.NotFound:
        print(f"{get_log_prefix()} Member {member.name} (ID: {member.id}) not found during kick check. Likely left.")
        if member.guild: remove_member_from_db(member.guild.id, member.id)
    except discord.Forbidden:
        print(f"{get_log_prefix()} ERROR: Bot lacks permission to fetch or kick member {member.name} (ID: {member.id}).")
    except Exception as e:
        print(f"{get_log_prefix()} ERROR: Unexpected error in kick_if_not_verified for {member.name} (ID: {member.id}): {e}")
    finally:
        if member.id in pending_verification_tasks:
            del pending_verification_tasks[member.id]

# --- Event Handlers ---
@client.event
async def on_ready():
    init_db()
    print(f'{get_log_prefix()} Bot logged in as {client.user.name}')
    await client.change_presence(activity=discord.Game(name=BOT_STATUS_MESSAGE), status=discord.Status.online)
    print(f"{get_log_prefix()} Bot status set to '{BOT_STATUS_MESSAGE}'.")

    if WELCOME_CHANNEL_ID == 0: print(f"{get_log_prefix()} WARNING: WELCOME_CHANNEL_ID is not set.")
    if not VERIFIED_ROLE_NAME: print(f"{get_log_prefix()} WARNING: VERIFIED_ROLE_NAME is not set.")

    # Get last online time from DB
    last_online_db_time = get_last_online_time()
    current_time = datetime.now(timezone.utc)
    
    # Determine the start of the catch-up window
    # If last_online_db_time is available, use it. Otherwise, use current time minus OFFLINE_CATCHUP_WINDOW_SECONDS
    catchup_start_time = current_time - timedelta(seconds=OFFLINE_CATCHUP_WINDOW_SECONDS)
    if last_online_db_time:
        # Use the later of (last_online_db_time) or (current_time - OFFLINE_CATCHUP_WINDOW_SECONDS)
        # This ensures we don't try to catch up on an excessively long period if the bot was offline for a very long time
        catchup_start_time = max(last_online_db_time, catchup_start_time)
        print(f"{get_log_prefix()} Using last online time from DB ({last_online_db_time}) for catch-up.")
    else:
        print(f"{get_log_prefix()} No last online time found in DB. Using fallback catch-up window of {OFFLINE_CATCHUP_WINDOW_SECONDS} seconds.")

    print(f"{get_log_prefix()} Starting offline member catch-up process for events since: {catchup_start_time} UTC")

    for guild in client.guilds:
        print(f"{get_log_prefix()} Processing guild: {guild.name} (ID: {guild.id})")
        verified_role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)
        if not verified_role:
            print(f"{get_log_prefix()} WARNING: Verified role '{VERIFIED_ROLE_NAME}' not found in guild '{guild.name}'.")
            continue

        current_guild_member_ids = set()
        verified_during_downtime_members_to_welcome = [] # For batch welcome

        # --- NEW LOGIC: Check for initial DB population for verified members ---
        # Check if there are any verified members already recorded for this guild
        existing_verified_members_in_db = get_all_verified_member_ids_from_db(guild.id)
        if not existing_verified_members_in_db: # If DB is empty for this guild
            print(f"{get_log_prefix()} DB for guild {guild.name} (ID: {guild.id}) appears empty. Populating with existing verified members.")
            if verified_role:
                async for member in guild.fetch_members(limit=None):
                    if not member.bot and verified_role in member.roles:
                        mark_member_verified_in_db(guild.id, member.id)
                        print(f"{get_log_prefix()} Added existing verified member {member.name} (ID: {member.id}) to DB.")
            else:
                print(f"{get_log_prefix()} WARNING: Verified role '{VERIFIED_ROLE_NAME}' not found in guild '{guild.name}', cannot initially populate verified members.")
        else:
            print(f"{get_log_prefix()} DB for guild {guild.name} (ID: {guild.id}) already contains verified members. Skipping initial population.")
        # --- END NEW LOGIC ---

        # --- Pass 1: Process current members ---
        async for member in guild.fetch_members(limit=None):
            current_guild_member_ids.add(member.id)
            if member.bot: continue

            # Check if the member is already verified by their roles.
            # If they are, skip the age check and any potential kick for age,
            # and ensure they are marked in DB and welcomed if they joined offline.
            has_verified_role_now = verified_role in member.roles
            if has_verified_role_now:
                # If they have the role, ensure they are in the DB and consider for batch welcome
                print(f"{get_log_prefix()} Member {member.name} (ID: {member.id}) has verified role. Ensuring DB record and checking for offline welcome.")
                mark_member_verified_in_db(guild.id, member.id)
                # Only add to welcome list if they joined *after* the bot was last online
                if member.joined_at and member.joined_at.astimezone(timezone.utc) >= catchup_start_time:
                    verified_during_downtime_members_to_welcome.append(member)
                continue # Skip all other checks for this member as they are already verified.

            # If they don't have the verified role, proceed with age check and timeout
            account_age = current_time - member.created_at
            
            # Check if member joined while bot was offline AND if their account age is too new
            if member.joined_at and member.joined_at.astimezone(timezone.utc) >= catchup_start_time:
                if account_age.days < MIN_ACCOUNT_AGE_DAYS:
                    try:
                        # Re-fetch to ensure member is still present before kicking
                        await guild.fetch_member(member.id) 
                        age_kick_reason = f"Account too new (created {account_age.days} days ago, min {MIN_ACCOUNT_AGE_DAYS} days). Found during catch-up."
                        print(f"{get_log_prefix()} Kicking member {member.name} (ID: {member.id}) for age during catch-up.")
                        await kick_member(member, age_kick_reason)
                    except discord.NotFound:
                        print(f"{get_log_prefix()} Member {member.name} (ID: {member.id}) for age check already left.")
                    except Exception as e:
                         print(f"{get_log_prefix()} Error during age kick for {member.name} (ID: {member.id}): {e}")
                    continue # Move to next member if kicked or already left

                # If they are not verified, but also not too young, and joined while offline, schedule a check
                if member.id not in pending_verification_tasks:
                    time_since_joined = current_time - member.joined_at.astimezone(timezone.utc)
                    remaining_time = VERIFICATION_TIMEOUT_SECONDS - time_since_joined.total_seconds()
                    
                    if remaining_time > 0:
                        print(f"{get_log_prefix()} Member {member.name} (ID: {member.id}) joined offline, not verified. Scheduling check. Remaining time: {remaining_time:.1f}s.")
                        task = asyncio.create_task(kick_if_not_verified(member, initial_delay_seconds=remaining_time))
                        pending_verification_tasks[member.id] = task
                    else:
                        # If remaining_time is 0 or negative, kick immediately if not verified
                        print(f"{get_log_prefix()} Member {member.name} (ID: {member.id}) joined offline, not verified, and verification timeout already passed.")
                        await kick_if_not_verified(member, initial_delay_seconds=0) # Perform immediate check
            else:
                # Member joined while bot was online, or before catch-up window, and is not verified, so no action needed here.
                pass 
        
        # --- Send Batch Welcome for current members verified during downtime ---
        if WELCOME_CHANNEL_ID != 0 and verified_during_downtime_members_to_welcome:
            target_welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
            if target_welcome_channel and isinstance(target_welcome_channel, discord.TextChannel):
                if len(verified_during_downtime_members_to_welcome) > 1:
                    mentions = ", ".join([m.mention for m in verified_during_downtime_members_to_welcome])
                    try:
                        batch_message = BATCH_WELCOME_MESSAGE.format(member_mentions_list=mentions, guild_name=guild.name)
                        await target_welcome_channel.send(batch_message)
                        print(f"{get_log_prefix()} Sent batch welcome for {len(verified_during_downtime_members_to_welcome)} members in {guild.name}.")
                    except Exception as e: print(f"{get_log_prefix()} ERROR sending batch welcome: {e}")
                elif len(verified_during_downtime_members_to_welcome) == 1:
                    member_to_welcome = verified_during_downtime_members_to_welcome[0]
                    specific_channel_mention_str = ""
                    if MENTION_CHANNEL_NAME:
                        tmc_obj = discord.utils.get(guild.text_channels, name=MENTION_CHANNEL_NAME)
                        specific_channel_mention_str = tmc_obj.mention if tmc_obj else f"#{MENTION_CHANNEL_NAME}"
                    try:
                        single_message = WELCOME_MESSAGE.format(
                            member_mention=member_to_welcome.mention, guild_name=guild.name, specific_channel_mention=specific_channel_mention_str)
                        await target_welcome_channel.send(single_message)
                        print(f"{get_log_prefix()} Sent individual welcome (batch logic) for {member_to_welcome.name} (ID: {member_to_welcome.id}).")
                    except Exception as e: print(f"{get_log_prefix()} ERROR sending single welcome (batch logic) for {member_to_welcome.name}: {e}")
            else: print(f"{get_log_prefix()} WARNING: Welcome channel {WELCOME_CHANNEL_ID} not found in {guild.name} for batch welcome.")

        # --- Pass 2: Process verified members who left while bot was offline ---
        db_verified_ids = get_all_verified_member_ids_from_db(guild.id)
        left_verified_user_objects = []

        for member_id_in_db in db_verified_ids:
            if member_id_in_db not in current_guild_member_ids:
                # This member was verified but is no longer in the guild
                try:
                    user = await client.fetch_user(member_id_in_db) # Fetch user object for name
                    left_verified_user_objects.append(user)
                    print(f"{get_log_prefix()} Verified member {user.name} (ID: {user.id}) left guild {guild.name} while bot was offline.")
                except discord.NotFound:
                    print(f"{get_log_prefix()} Could not fetch user info for ID {member_id_in_db} (left offline, user deleted?).")
                    # Still remove from DB as they are not in guild
                except Exception as e:
                    print(f"{get_log_prefix()} Error fetching user {member_id_in_db} who left offline: {e}")
                
                # Remove from DB regardless of whether user object could be fetched, as they are not in guild
                remove_member_from_db(guild.id, member_id_in_db)

        # --- Send Batch Goodbye for verified members who left during downtime ---
        if WELCOME_CHANNEL_ID != 0 and left_verified_user_objects: # Using WELCOME_CHANNEL_ID for goodbyes too
            target_goodbye_channel = guild.get_channel(WELCOME_CHANNEL_ID)
            if target_goodbye_channel and isinstance(target_goodbye_channel, discord.TextChannel):
                if len(left_verified_user_objects) > 1:
                    names_list = ", ".join([u.display_name for u in left_verified_user_objects])
                    try:
                        batch_goodbye_msg = BATCH_GOODBYE_MESSAGE.format(member_names_list=names_list, guild_name=guild.name)
                        await target_goodbye_channel.send(batch_goodbye_msg)
                        print(f"{get_log_prefix()} Sent batch goodbye for {len(left_verified_user_objects)} members who left {guild.name} offline.")
                    except Exception as e: print(f"{get_log_prefix()} ERROR sending batch goodbye: {e}")
                elif len(left_verified_user_objects) == 1:
                    user_who_left = left_verified_user_objects[0]
                    try:
                        single_goodbye_msg = GOODBYE_MESSAGE.format(member_name=user_who_left.display_name, guild_name=guild.name)
                        await target_goodbye_channel.send(single_goodbye_msg)
                        print(f"{get_log_prefix()} Sent individual goodbye (offline logic) for {user_who_left.display_name} (ID: {user_who_left.id}).")
                    except Exception as e: print(f"{get_log_prefix()} ERROR sending single goodbye (offline logic) for {user_who_left.display_name}: {e}")
            else: print(f"{get_log_prefix()} WARNING: Goodbye channel {WELCOME_CHANNEL_ID} not found in {guild.name} for offline leavers.")

    print(f"{get_log_prefix()} Offline member catch-up finished.")
    update_last_online_time() # Update last online time after catch-up

@client.event
async def on_member_join(member: discord.Member):
    print(f"{get_log_prefix()} Member joined (bot online): {member.name} (ID: {member.id})")
    account_age = datetime.now(timezone.utc) - member.created_at
    if account_age.days < MIN_ACCOUNT_AGE_DAYS:
        age_kick_reason = f"Account too new (created {account_age.days} days ago, min {MIN_ACCOUNT_AGE_DAYS} days)."
        await kick_member(member, age_kick_reason)
        return

    if member.id not in pending_verification_tasks:
        task = asyncio.create_task(kick_if_not_verified(member))
        pending_verification_tasks[member.id] = task
        print(f"{get_log_prefix()} Scheduled verification task for {member.name} (ID: {member.id}). Timeout: {VERIFICATION_TIMEOUT_SECONDS}s.")
    else:
        print(f"{get_log_prefix()} Warning: Task already exists for {member.name} (ID: {member.id}) in on_member_join.")

@client.event
async def on_member_update(before: discord.Member, after: discord.Member):
    guild = after.guild
    verified_role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)

    if not verified_role:
        if after.id in pending_verification_tasks:
             print(f"{get_log_prefix()} ERROR: Verified role '{VERIFIED_ROLE_NAME}' not found in {guild.name} for {after.name} (ID: {after.id}).")
        return

    was_verified_before = verified_role in before.roles
    is_verified_now = verified_role in after.roles

    if not was_verified_before and is_verified_now:
        print(f"{get_log_prefix()} Member {after.name} (ID: {after.id}) received '{VERIFIED_ROLE_NAME}' role.")
        mark_member_verified_in_db(guild.id, after.id)

        task = pending_verification_tasks.pop(after.id, None)
        welcome_sent_by_this_event = False
        if task:
            if not task.done():
                task.cancel()
                try: await task
                except asyncio.CancelledError: print(f"{get_log_prefix()} Cancelled verification task for {after.name} (ID: {after.id}).")
                except Exception as e: print(f"{get_log_prefix()} Exception awaiting cancelled task for {after.name}: {e}")
            else: print(f"{get_log_prefix()} Verification task for {after.name} already done.")
            
            if WELCOME_CHANNEL_ID != 0:
                target_welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
                if target_welcome_channel and isinstance(target_welcome_channel, discord.TextChannel):
                    try:
                        specific_channel_mention_str = ""
                        if MENTION_CHANNEL_NAME:
                            tmc_obj = discord.utils.get(guild.text_channels, name=MENTION_CHANNEL_NAME)
                            specific_channel_mention_str = tmc_obj.mention if tmc_obj else f"#{MENTION_CHANNEL_NAME}"
                        
                        formatted_welcome_message = WELCOME_MESSAGE.format(
                            member_mention=after.mention, guild_name=guild.name, specific_channel_mention=specific_channel_mention_str)
                        await target_welcome_channel.send(formatted_welcome_message)
                        print(f"{get_log_prefix()} Sent welcome for {after.name} (ID: {after.id}) (on_member_update).")
                        welcome_sent_by_this_event = True
                    except Exception as e: print(f"{get_log_prefix()} ERROR sending welcome (on_member_update) for {after.name}: {e}")
                else: print(f"{get_log_prefix()} ERROR: Welcome channel {WELCOME_CHANNEL_ID} not found for {after.name}.")
            else: print(f"{get_log_prefix()} Welcome channel ID not configured, skipping welcome for {after.name}.")
        
        if not welcome_sent_by_this_event and not task :
             print(f"{get_log_prefix()} Member {after.name} verified, no active kick task. Welcome likely handled by on_ready or not applicable.")

@client.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    member_id = member.id
    guild_id = guild.id
    
    print(f"{get_log_prefix()} Member {member.display_name} (ID: {member_id}) left guild {guild.name} (ID: {guild_id}).")

    task = pending_verification_tasks.pop(member_id, None)
    if task: # Member left while a kick task was pending
        if not task.done():
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        print(f"{get_log_prefix()} Cancelled/removed pending task for leaving member {member.display_name} (ID: {member_id}).")
        remove_member_from_db(guild_id, member_id) 
        return # No goodbye if they were pending verification and left

    # If no task was pending, check DB if they were previously verified (for members leaving while bot is ONLINE)
    member_was_verified_in_db_check = was_member_verified_in_db(guild_id, member_id)
    
    if member_was_verified_in_db_check:
        if WELCOME_CHANNEL_ID != 0:
            target_goodbye_channel = guild.get_channel(WELCOME_CHANNEL_ID)
            if target_goodbye_channel and isinstance(target_goodbye_channel, discord.TextChannel):
                try:
                    formatted_goodbye_message = GOODBYE_MESSAGE.format(member_name=member.display_name, guild_name=guild.name)
                    await target_goodbye_channel.send(formatted_goodbye_message)
                    print(f"{get_log_prefix()} Sent goodbye for verified member {member.display_name} (ID: {member_id}) (on_member_remove).")
                except Exception as e: print(f"{get_log_prefix()} ERROR sending goodbye (on_member_remove) for {member.display_name}: {e}")
            else: print(f"{get_log_prefix()} ERROR: Goodbye channel {WELCOME_CHANNEL_ID} not found for {member.display_name}.")
        else: print(f"{get_log_prefix()} Welcome channel ID not configured, skipping goodbye for {member.display_name}.")
    else:
        print(f"{get_log_prefix()} Member {member.display_name} (ID: {member_id}) left and was not recorded as verified in DB. No on_member_remove goodbye sent.")

    # Final cleanup from DB, as they have left the server.
    # This is important because on_ready handles leavers found during startup.
    # on_member_remove handles leavers while bot is online.
    remove_member_from_db(guild_id, member_id)

# --- Main Execution ---
if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print(f"{get_log_prefix()} ERROR: DISCORD_BOT_TOKEN missing.")
        exit(1)
    if WELCOME_CHANNEL_ID == 0:
        print(f"{get_log_prefix()} WARNING: WELCOME_CHANNEL_ID environment variable is not set or is invalid.")
    if not VERIFIED_ROLE_NAME:
        print(f"{get_log_prefix()} WARNING: VERIFIED_ROLE_NAME environment variable is not set.")
    
    try:
        client.run(DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        print(f"{get_log_prefix()} ERROR: Login failed. Check DISCORD_BOT_TOKEN.")
    except Exception as e:
        print(f"{get_log_prefix()} ERROR running bot: {e}")