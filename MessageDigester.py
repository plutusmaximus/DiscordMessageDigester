import asyncio
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import re
import smtplib
import sys
from typing import Any, TypedDict, Optional

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger("MessageDigester")

def generate_log_filename(prefix: str = "log", extension: str = ".log") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}{extension}"

logging.basicConfig(
    level=logging.INFO,  # Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(levelname)s - %(message)s',  # Timestamp prefix format
    datefmt='%Y-%m-%d %H:%M:%S',  # Concise timestamp format
    handlers=[
        TimedRotatingFileHandler(
            filename=generate_log_filename(),
            when="midnight",  # Rotate at midnight daily
            interval=1,  # Every 1 day
            backupCount=10,  # Keep up to 10 backup files
            encoding="utf-8",
            delay=False
        ),
        logging.FileHandler(generate_log_filename()),  # Log to file with timestamped name
        logging.StreamHandler()  # Also log to console
    ]
)

logger.info("Started")

# Load bot config variables from environment
load_dotenv()

# The discord token is used to log the bot in to discord.
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
if not DISCORD_TOKEN:
    logger.error(f"DISCORD_TOKEN not present in .env - quitting")
    sys.exit()

# Interval at which to create a digest from all messages posted
# since the last digest.
DEFAULT_DIGEST_INTERVAL_MINUTES = int(os.getenv('DEFAULT_DIGEST_INTERVAL_MINUTES') or '1440')    # Default to 24 hours
# Interval between running the main loop to check if digests need to be generated.
MAIN_LOOP_INTERVAL_SEC = int(os.getenv('MAIN_LOOP_INTERVAL_SEC') or '60') # Default to 60 seconds
# File to store configurations for each server
CONFIG_FILE = os.getenv('CONFIG_FILE') or 'bot_config.json'

# If EMAIL_SENDER_EMAIL is not present don't send emails
EMAIL_SENDER_EMAIL = os.getenv('EMAIL_SENDER_EMAIL')
EMAIL_SENDER_PASSWORD = os.getenv('EMAIL_SENDER_PASSWORD')
EMAIL_SMTP_SERVER = os.getenv('EMAIL_SMTP_SERVER') or 'NO SMTP SERVER!!'
EMAIL_SMTP_PORT = int(os.getenv('EMAIL_SMTP_PORT') or '587')

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True  # Needed for reading message content
bot = commands.Bot(command_prefix='!', intents=intents)

# Represents the server config stored in the JSON config file
class ServerConfig(TypedDict):
    channels: list[int]
    digest_interval: int
    email_recipients: list[str]
    last_digest: Optional[datetime]

# Load digest configurations from file
def load_config() -> dict[int,ServerConfig]:
    logger.info(f"Loading config from: {os.path.abspath(CONFIG_FILE)}...")
    if not os.path.exists(CONFIG_FILE):
        logger.info(f"{os.path.abspath(CONFIG_FILE)} does not exist - creating...")
        with open(CONFIG_FILE, 'w') as f:
            data : Any = {}
            json.dump(data, f)
            return data
    else:
        with open(CONFIG_FILE, 'r') as f:
            tmp = json.load(f)
            # Convert keys from string to int
            data = {int(key): value for key, value in tmp.items()}
            # Convert last_digest back to datetime for each server
            for server_id in data:
                if 'last_digest' in data[server_id] and data[server_id]['last_digest']:
                    data[server_id]['last_digest'] = datetime.fromisoformat(data[server_id]['last_digest'])

            return data
    return {}

# Save configurations to file
def save_config(configs : dict[int, Any]):
    data = {}
    for server_id, conf in configs.items():
        data[server_id] = conf.copy()
        if 'last_digest' in conf and conf['last_digest']:
            data[server_id]['last_digest'] = conf['last_digest'].isoformat()
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f)

# Get a discord server's name from its ID.
def get_server_name_from_id(server_id: int) -> str:
    try:
        guild = bot.get_guild(server_id)
        if guild is None:
            # If guild not in cache, try fetching it
            guild = asyncio.run(bot.fetch_guild(server_id))
        if guild.name:
            return guild.name
    except discord.errors.Forbidden:
        logger.exception(f"Bot lacks permission to access server with ID {server_id}")
    except discord.errors.HTTPException as e:
        logger.exception(f"Error fetching server with ID {server_id}: {e}")
    
    return "NO SERVER NAME"

# Generate a server identifier (name/ID) to use in logging
def server_log_name(server_id : int) -> str:
    return f'"{get_server_name_from_id(server_id)}"/{server_id}'

# Load the config
# Global configs dictionary:
#  {
#       server_id: ServerConfig
#  }
# Note: 'server_id' refers to Discord's guild ID, which identifies a server, not premium guild features
try:
    configs = load_config()
except Exception as e:
    logger.exception(f"An error occurred: {str(e)}")

# Main loop that periodically checks to see if a new
# digest needs to be generated.
@tasks.loop(seconds=MAIN_LOOP_INTERVAL_SEC)
async def digest_check():
    if not configs:
        logger.info("No servers have been configured")
        return
        
    try:
        now = datetime.now(timezone.utc)
        for server_id, conf in list(configs.items()):  # Copy to avoid runtime changes
            if 'last_digest' not in conf or not conf['last_digest']:
                conf['last_digest'] = now
                continue
            elapsed_minutes = (now - conf['last_digest']).total_seconds() / 60
            if elapsed_minutes >= conf.get('digest_interval', DEFAULT_DIGEST_INTERVAL_MINUTES):
                await generate_digest(server_id)
                conf['last_digest'] = now
                save_config(configs)

    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")

# Group messages according to the window of time in which they occurred.
# Grouped messages will be rendered to the digest under their timestamp.
# This avoids polluting the digest with lots of timestamps.
def group_messages_by_timestamp(messages : list[discord.Message]) -> dict[str, list[discord.Message]]:
    msgGroups : dict[str, list[discord.Message]] = {}

    for msg in messages:
        # Timestamp granularity is minute, so messages
        # will be grouped under the minute in which they occurred.
        timestamp = msg.created_at.astimezone().strftime('%a %b %d %I:%M %p')
        if timestamp not in msgGroups:
            msgGroups[timestamp] = []
            
        msgGroups[timestamp].append(msg)

    return msgGroups

def send_email(sender_email: str, sender_password: str, recipient_list: list[str], 
               subject: str, body: str, content_type: str = 'html', 
               smtp_server: str = "smtp.gmail.com", smtp_port: int = 587) -> bool:
    """
    Send an email to a list of recipients via SMTP with undisclosed recipients.
    Supports both standard password and Gmail's app-specific password authentication.

    Args:
        sender_email (str): Sender's email address
        sender_password (str): Sender's email password or app-specific password for Gmail
        recipient_list (List[str]): List of recipient email addresses
        subject (str): Email subject
        body (str): Email body content (HTML or plain text)
        content_type (str): MIME type of the body ('html' or 'plain', default: 'html')
        smtp_server (str): SMTP server address (default: Gmail)
        smtp_port (int): SMTP server port (default: 587 for TLS)

    Returns:
        bool: True if email sent successfully, False otherwise

    Note:
        - For Gmail with 2FA enabled, generate an app-specific password at:
          https://myaccount.google.com/security (under "Signing in to Google" > "App passwords").
    """
    try:
        # Validate content_type
        if content_type not in ['html', 'plain']:
            raise ValueError("content_type must be 'html' or 'plain'")

        # Create the email message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = "Undisclosed Recipients <undisclosed-recipients@no-reply.com>"
        msg['Subject'] = subject
        
        # Add body to email with specified content type
        msg.attach(MIMEText(body, content_type))

        # Set up the SMTP server
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Enable TLS

        # Authenticate using the provided credentials
        # For Gmail, app-specific password is used the same way as a regular password
        server.login(sender_email, sender_password)

        # Send email to all recipients as BCC
        server.sendmail(sender_email, recipient_list, msg.as_string())
        
        # Close the connection
        server.quit()
        return True
    
    except Exception as e:
        print(f"Failed to send email: {str(e)}")
        return False

def render_digest_to_html(serverName: str, digest: dict[str, dict[str, list[discord.Message]]]) -> str:
    html = '<html><body style="font-family: Arial, sans-serif;">\n'
    # Add page title with server name
    html += f'<h1>Digest for {serverName}</h1>\n'
    
    for channel_name, message_groups in digest.items():
        # Add channel header
        html += f'<h2>#{channel_name}</h2>\n'
        
        for timestamp, messages in message_groups.items():
            # Convert timestamp string to datetime and format
            try:
                dt = datetime.fromisoformat(timestamp)
                formatted_time = dt.strftime("%a %b %d %I:%M %p")
            except ValueError:
                formatted_time = timestamp  # Fallback if timestamp isn't valid ISO format
            
            # Add timestamp header
            html += f'<h3>{formatted_time}</h3>\n'
            
            # Check if message group is empty
            if not messages:
                html += '<p>No new messages</p>\n'
            else:
                html += '<ul>\n'
                # Add each message in the group
                for message in messages:
                    author = message.author.name
                    content = message.content.replace('<', '&lt;').replace('>', '&gt;')  # Escape HTML characters
                    
                    # Initialize thumbnail and embed HTML
                    thumbnail_html = ''
                    embed_html = ''
                    
                    # Check for attachments and add thumbnails
                    for attachment in message.attachments:
                        if attachment.url:
                            thumbnail_html += f'<br><img src="{attachment.url}" alt="Attachment Thumbnail" style="max-width: 200px; max-height: 200px; object-fit: cover;" onerror="this.style.display=\'none\'">'
                    
                    # Check for stickers and add thumbnails or name based on format
                    for sticker_item in message.stickers:
                        if sticker_item.id:
                            # Render Lottie stickers as their name, others as images
                            if sticker_item.format == discord.StickerFormatType.lottie:
                                thumbnail_html += f'<br><p>Sticker: {sticker_item.name.replace("<", "&lt;").replace(">", "&gt;")}</p>'
                            else:
                                sticker_url = f"https://cdn.discordapp.com/stickers/{sticker_item.id}.png?size=320"
                                thumbnail_html += f'<br><img src="{sticker_url}" alt="Sticker" style="max-width: 200px; max-height: 200px; object-fit: cover;" onerror="this.style.display=\'none\'">'
                        else:
                            # Fallback in case sticker ID is unavailable
                            thumbnail_html += f'<br><p>Unable to load sticker: {sticker_item.name.replace("<", "&lt;").replace(">", "&gt;")}</p>'
                    
                    # Check for embeds and add formatted content
                    for embed in message.embeds:
                        embed_content = ''
                        if embed.title:
                            # Make title a clickable link if embed.url exists, otherwise just strong text
                            title_text = embed.title.replace('<', '&lt;').replace('>', '&gt;')
                            if embed.url:
                                embed_content += f'<a href="{embed.url}" style="text-decoration: none; color: #0066cc; display: block;"><strong>{title_text}</strong></a>'
                            else:
                                embed_content += f'<strong style="display: block; word-wrap: break-word;">{title_text}</strong>'
                        if embed.description:
                            embed_content += f'<p style="margin: 0; word-wrap: break-word;">{embed.description.replace("<", "&lt;").replace(">", "&gt;")}</p>'
                        if embed.thumbnail and embed.thumbnail.url:
                            embed_content += f'<img src="{embed.thumbnail.url}" alt="Embed Thumbnail" style="max-width: 200px; max-height: 200px; object-fit: cover; display: block; margin-top: 10px;" onerror="this.style.display=\'none\'">'
                        if embed_content:
                            embed_html += f'<div style="width: 200px; padding: 10px; border-left: 2px solid #ccc; box-sizing: border-box;">{embed_content}</div>'
                    
                    html += f'    <li><strong>{author}:</strong> {content}{thumbnail_html}{embed_html}</li>\n'
                html += '</ul>\n'
    
    html += '</body></html>'
    return html

async def generate_digest(server_id : int):
    try:
        logger.info(f"Generating digest for server {server_log_name(server_id)}...")

        conf = configs.get(server_id)
        if not conf or 'channels' not in conf or not conf['channels']:
            logger.info(f"No channels configured for server {server_log_name(server_id)}")
            return
        
        serverName = get_server_name_from_id(server_id)

        haveNewMessages = False

        # For each channel collect messages and group them
        # by timestamp

        digest : dict[str, dict[str,list[discord.Message]]] = {}
        
        for channel_id in conf['channels']:
            channel = bot.get_channel(channel_id)
            if not channel:
                continue

            # Tell type checker that channel is a TextChannel
            assert isinstance(channel, discord.TextChannel), "Expected a TextChannel"

            digest[get_channel_name(channel_id)] = {}

            # Fetch messages since last digest, oldest first to maintain time ordering
            messages = [msg async for msg in channel.history(after=conf['last_digest'], oldest_first=True, limit = None)]

            if not messages:
                continue

            digest[get_channel_name(channel_id)] = msgGroups = group_messages_by_timestamp(messages)

            # If no messages don't add to the digest
            if not msgGroups:
                continue
            
            haveNewMessages = True

        if(not haveNewMessages):
            logger.info(f"No new messages on server {server_log_name(server_id)}.")
            return
        
        logger.info(f"Writing messages from server {server_log_name(server_id)} to digest...")
        
        baseFilename = f"digest_{server_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        # Save to HTML file
        html = render_digest_to_html(serverName, digest)
        htmlFilename = f"{baseFilename}.html"
        with open(htmlFilename, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"Generated HTML digest {htmlFilename} for server {server_log_name(server_id)}")

        # Send HTML-formatted email to recipient list

        if not EMAIL_SENDER_EMAIL or not EMAIL_SENDER_PASSWORD:
            logger.info(f"Email disabled for {server_log_name(server_id)} - no email will be sent")
            return

        if 'email_recipients' not in conf or not conf['email_recipients']:
            logger.info(f"No email recipients for {server_log_name(server_id)}")
            return

        logger.info(f"Sending digest email for server {server_log_name(server_id)}...")

        recipientList = conf['email_recipients']
    
        subject = f"Discord Message Digest for {serverName}"
        send_email(EMAIL_SENDER_EMAIL, EMAIL_SENDER_PASSWORD, recipientList, subject, html)

    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")

# Return the server ID in string format.  Used by bot commands.
def get_server_id(ctx : commands.Context[commands.Bot]) -> int:
    assert ctx.guild is not None  # Tell type checker ctx.guild is not None
    return ctx.guild.id  # Guild ID is the server ID

# Return the name of the channel associated with the channel ID.
def get_channel_name(channelId : int) -> str:
    channel = bot.get_channel(channelId)

    # Tell type checker that channel is a TextChannel
    assert isinstance(channel, discord.TextChannel), "Expected a TextChannel"

    return channel.name

SERVER_CONFIG_TEMPLATE: ServerConfig = {
    'channels': [],
    'digest_interval': DEFAULT_DIGEST_INTERVAL_MINUTES,
    'email_recipients': [],
    'last_digest': None
}

# If a server config doesn't exist populate it with a default config
def populate_server_config(server_id : int):
    if not server_id in configs or not configs[server_id]:
        configs[server_id] = SERVER_CONFIG_TEMPLATE.copy()

    config = configs[server_id]
    
    # If the config exists it might not have all the fields if new fields have
    # been added since the config was created.
    for key, value in SERVER_CONFIG_TEMPLATE.items():
        if key not in config:
            config[key] = value
    
################################
# Bot Commands
################################

# add_channel
# Adds a channel to be monitored for new messages.
# Usage
#   !add_channel
#
# Called from the channel to add.
#
@bot.command(name='add_channel',brief='Adds the current channel to be monitored for new messages')
@commands.has_permissions(administrator=True)
@commands.guild_only()  # Restrict command to guilds only
async def add_channel(ctx : commands.Context[commands.Bot]):
    try:
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send(f'Only text channels can be monitored.')
            return

        channelName = get_channel_name(ctx.channel.id)

        server_id = get_server_id(ctx)

        populate_server_config(server_id)

        if ctx.channel.id not in configs[server_id]['channels']:
            configs[server_id]['channels'].append(ctx.channel.id)
            save_config(configs)
            await ctx.send(f'Added channel #{channelName} to monitored channels.')
            logger.info(f'Added channel #{channelName} to monitored channels on server {server_log_name(server_id)}.')
        else:
            await ctx.send(f'Channel #{channelName} is already monitored.')
    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")

# remove_channel
# Removes a channel from the list of channels to be monitored.
# Usage
#   !remove_channel
#
# Called from the channel to remove.
#
@bot.command(name='remove_channel',brief='Removes the current channel from the list of monitored channels')
@commands.has_permissions(administrator=True)
@commands.guild_only()  # Restrict command to guilds only
async def remove_channel(ctx : commands.Context[commands.Bot]):
    try:
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send(f'Only text channels can be monitored.')
            return
        
        channelName = get_channel_name(ctx.channel.id)
        
        server_id = get_server_id(ctx)
        if server_id in configs and ctx.channel.id in configs[server_id]['channels']:
            configs[server_id]['channels'].remove(ctx.channel.id)
            save_config(configs)
            await ctx.send(f'Removed channel #{channelName} from monitored channels.')
            logger.info(f'Removed channel #{channelName} from monitored channels {server_log_name(server_id)}.')
        else:
            await ctx.send(f'Channel #{channelName} is not being monitored.')
    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")

# set_interval
# Sets the interval at which to check for new messages.
# Usage
#   !set_interval <minutes>
#
# Called from any channel.
#
@bot.command(name='set_interval',brief='Sets the interval at which to check for new messages')
@commands.has_permissions(administrator=True)
@commands.guild_only()  # Restrict command to guilds only
async def set_interval(ctx : commands.Context[commands.Bot], minutes: int):
    try:
        if minutes < 1:
            await ctx.send('Interval must be at least 1 minute.')
            return
        server_id = get_server_id(ctx)

        populate_server_config(server_id)

        configs[server_id]['digest_interval'] = minutes
        save_config(configs)
        await ctx.send(f'Digest interval set to {minutes} minutes.')
        logger.info(f'Digest interval set to {minutes} minutes on server {server_log_name(server_id)}.')
    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")

# Regular expression for basic email validation
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

def email_list_from_csv(csv : str) -> list[str]:
    # Split string on either commas or whitespace
    return [r.strip().lower() for x in csv.split(',') for r in x.split()]

# add_emails
# Adds email recipients of the message digest.
# Usage
#   !add_emails <recipient_list>
#
# <recipient_list> is a comma-separated list of email addresses.
#
# Called from any channel.
#
@bot.command(name='add_emails',brief='Adds email recipients of the message digest')
@commands.has_permissions(administrator=True)
@commands.guild_only()  # Restrict command to guilds only
async def add_emails(ctx : commands.Context[commands.Bot], *, recipientCSV : str):
    try:
        
        recipientsToAdd = email_list_from_csv(recipientCSV)

        if not recipientsToAdd:
            await ctx.send(f'Email recipient list not updated')
            return
        
        emails : list[str] = []

        for recipient in recipientsToAdd:
            # Validate email format
            if EMAIL_PATTERN.match(recipient):
                emails.append(recipient)
            else:
                await ctx.send(f'"{recipient}" is an invalid email')

        if not emails:
            await ctx.send(f'Email recipient list not updated')
            return
                
        server_id = get_server_id(ctx)

        populate_server_config(server_id)

        # Merge lists and remove duplicates
        oldEmails = configs[server_id]['email_recipients']
        emails = list(dict.fromkeys(emails + oldEmails))

        configs[server_id]['email_recipients'] = emails
        save_config(configs)

        await ctx.send(f'Email recipient list updated')
        logger.info(f'Email recipient list updated on server {server_log_name(server_id)}.')
    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")

# remove_emails
# Removes email recipients from the message digest.
# Usage
#   !remove_emails <recipient_list>
#
# <recipient_list> is a comma-separated list of email addresses.
#
# Called from any channel.
#
@bot.command(name='remove_emails',brief='Removes email recipients from the message digest')
@commands.has_permissions(administrator=True)
@commands.guild_only()  # Restrict command to guilds only
async def remove_emails(ctx : commands.Context[commands.Bot], *, recipientCSV : str):
    try:
        
        # Split string on either commas or whitespace
        recipientsToRemove = email_list_from_csv(recipientCSV)

        if not recipientsToRemove:
            await ctx.send(f'Email recipient list not updated')
            return
                
        server_id = get_server_id(ctx)

        populate_server_config(server_id)

        # Merge lists and remove duplicates
        oldEmails = configs[server_id]['email_recipients']
        emails = [recip for recip in oldEmails if recip not in recipientsToRemove]

        configs[server_id]['email_recipients'] = emails
        save_config(configs)

        await ctx.send(f'Email recipient list updated')
        logger.info(f'Email recipient list updated on server {server_log_name(server_id)}.')
    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")

# show_config
# Prints the configuration for the server.
# Usage
#   !show_config
#
# Called from any channel.
#
@bot.command(name='show_config',brief='Prints the configuration for the server')
@commands.has_permissions(administrator=True)
@commands.guild_only()  # Restrict command to guilds only
async def show_config(ctx : commands.Context[commands.Bot]):
    try:
        server_id = get_server_id(ctx)
        if server_id not in configs:
            await ctx.send('No configuration set yet.')
            return
        
        conf = configs[server_id]

        # KV pairs excluding 'channels'
        configStr = '\n'.join(f"{key}: {value}" for key, value in conf.items() if key != 'channels')
        # Special treatment for 'channels' to convert channel IDs to strings
        channels = ', '.join([get_channel_name(ch_id) for ch_id in conf.get('channels', []) if bot.get_channel(ch_id)]) or 'None'
        
        await ctx.send(f'channels: {channels}\n{configStr}')
    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")

# Run the bot

# Maximum reconnection attempts
MAX_RECONNECT_ATTEMPTS = 100
# Initial delay for reconnection (in seconds)
INITIAL_RECONNECT_DELAY = 5
# Maximum time to wait between connect attempts
MAX_RECONNECT_DELAY = 60

# Attempt to reconnect the bot with exponential backoff.
async def try_reconnect(attempt : int = 1):
    if attempt > MAX_RECONNECT_ATTEMPTS:
        logger.error("Maximum reconnection attempts reached. Shutting down.")
        await bot.close()
        return
    
    if digest_check.is_running():
        digest_check.cancel()

    delay = INITIAL_RECONNECT_DELAY
    
    while True:        
        logger.warning(f"Connection lost. Attempting to reconnect (Attempt {attempt}) in {delay} seconds...")

        await asyncio.sleep(delay)
        
        try:
            await bot.start(DISCORD_TOKEN or '')
            return  # Exit if connection succeeds
        except Exception as e:
            logger.error(f"Reconnection attempt {attempt} failed: {e}")
            attempt += 1
            delay = min(delay * 2, MAX_RECONNECT_DELAY)  # Exponential backoff with max delay

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')
    digest_check.start()  # Start the periodic check for digests

@bot.event
async def on_disconnect():
    logger.warning(f"B{bot.user}ot disconnected from Discord.")

@bot.event
async def on_command_error(ctx: commands.Context[commands.Bot], error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        commandNames = [command.name for command in bot.commands]
        availableCommands = "\n".join(f"!{name}" for name in commandNames)
        await ctx.send(f"Command not found.\nAvailable commands:\n{availableCommands}")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    else:
        logger.error(f"Command error: {error}")
        await ctx.send("An error occurred while processing the command.")

async def main():
    try:
        await bot.start(DISCORD_TOKEN or '')
    except discord.errors.LoginFailure:
        logger.error("Invalid Discord token. Please check your token.")
    except Exception as e:
        logger.error(f"Failed to connect: {e}")
        await try_reconnect()

if __name__ == "__main__":
    # Run the bot in an asyncio event loop
    asyncio.run(main())