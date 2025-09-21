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


# Terms of Use

As an administrator inviting this bot to a server, you agree to only grant the
bot access to text channels with minimal posting activity to limit email spam.
You also agree to add prominent warnings to these channels that posts to them
will be forwarded by the bot to club students and/or their parents via email.

You must seek and record the consent of monitored announcement channels'
individual posters to share their Discord API data with this bot to fulfill its
functions as described in the [Privacy Policy]( #privacy-policy ); Forward
copies of recorded consent to the bot's owner through the club's official email
address.  These restrictions are meant to comply with the [Discord Developer
Terms of Service](
https://support-dev.discord.com/hc/en-us/articles/8562894815383-Discord-Developer-Terms-of-Service
).


# Privacy Policy

This bot does not persist any user data.  However, it does share message
contents and authors' server nicknames that it sees in announcement channels (as
assigned by server owners).  These messages get forwarded to limited mailing
lists of the students and parents in Sage Creek High School's robotics club that
cannot or refuse to join Discord.  The student and parent members of these
mailing lists are the only third parties that receive shared data; it is not
sold to them.  Because this bot is not operated by a for-profit company, it is
exempt from the California Consumer Privacy Act (CCPA).
