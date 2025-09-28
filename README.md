Message Digester
================
Message Digester is a Discord bot that creates digests of messages on a discord server.

Periodically, based on a configurable interval, the bot will collect all messages that have been posted since the last digest, format them as HTML, and send them to a list of email addresses.

# Commands
All commands are prefixed with `!`

### add_channel
Adds a channel to be monitored for new messages.
```
!add_channel <channel name>
```

### remove_channel
Removes a channel from the !list of monitored channels.
```
!remove_channel <channel name>
```

### upload_emails
Uploads email recipients from an attached file. The attached file must contain a list of valid email addresses, with one email address per line.
```
!upload_emails
```

### set_interval
Sets the interval in minutes at which to check for new messages.
```
!set_interval <minutes>
```

### show_config
Prints the configuration for the server.
```
!show_config
```

### help
Shows help text.
```
!help
```

Type ```!help <command>``` for more info on a command.

# Inviting the bot to a server
To get an invite link for a Discord bot, follow these steps:

1. Go to the Discord Developer Portal at https://discord.com/developers/applications.
2. Select the bot application you want to invite from the list of your applications.
3. Navigate to the "OAuth2" tab and then click on "URL Generator".
4. Under "Scopes," tick the "bot" checkbox.
5. Under "Bot Permissions," select the specific permissions your bot needs to function in the server.
The invite link will automatically generate in the text box at the bottom of the page.
 Copy this link.
6. Paste the copied link into a web browser, select the server you want to add the bot to, and click "Authorize" to complete the invitation.

# Configuration

Confiugration can be set as environment variables or added to the .env file.  Environment variables take precendence over those in the .env file.

**DISCORD_TOKEN** - The discord authorization token token used by the bot. See [Discord Developer Portal](https://discord.com/developers/applications)

**DEFAULT_DIGEST_INTERVAL_MINUTES** - Interval over which to collect messages for a digest.  A new digest will be created each time this interval elapses for a specific server.  The digest will include messages posted to all monitored channels within that interval.

**MAIN_LOOP_INTERVAL_SEC** - Interval at which all servers are checked to see if a new digest should be created.  If during this check it's discovered that the digest interval has elapsed for a specific server then a new digest will be generated for that server.

**CONFIG_FILE** - File to store configurations, one configuration per server.

**EMAIL_SENDER_EMAIL** - Email from which digest email will be sent.
**MAIL_SENDER_PASSWORD** - Password for email account from which digest email will be sent. For gmail accounts which use multifactor authentication and app-specific password will be required for the EMAIL_SENDER_PASSWORD variable.  See [App Passwords](https://support.google.com/accounts/answer/185833).

**EMAIL_SMTP_SERVER** - Domain name of SMTP server from which to send emails
**EMAIL_SMTP_PORT** - IP port on which SMTP server is listening.

Python Dependencies
===================

```sh
pip install discord dotenv
```