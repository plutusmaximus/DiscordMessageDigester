Message Digester
================
Message Digester is a Discord bot that creates digests of messages on a discord server.

Periodically, based on a configurable interval, the bot will collect all messages that have been posted since the last digest, format them as HTML, and send them to a list of email addresses.

# Commands
All commands are prefixed with `!`

**!add_channel** - Adds the current channel to be monitored for new messages.

**!remove_channel** - Removes the current channel from the !list of monitored channels.

**!add_emails** - Adds email recipients of the message digest.

**!remove_emails** - Removes email recipients from the message digest.

**!set_interval** - Sets the interval at which to check for new messages.

**!show_config** - Prints the configuration for the server.

**!help** - Shows help text.

Type !help command for more info on a command.

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