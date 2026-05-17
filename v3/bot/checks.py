import discord
from bot.config import Config
from bot.logger import logger
from datetime import datetime, timedelta, timezone

# user_id -> (request_count, window_start: datetime)
_rate_limit_state: dict[int, tuple[int, datetime]] = {}


def is_rate_limited(user_id: int) -> tuple[bool, datetime | None, bool]:
    """Returns (is_limited, reset_time, is_last_request).
    is_last_request is True when this request exhausts the user's quota."""
    if user_id in Config.OVERRIDE_USERS:
        logger.debug("Rate limit bypassed for override user %s", user_id)
        return False, None, False

    now = datetime.now(timezone.utc)
    limit = Config.RATE_LIMIT_REQUESTS
    window = timedelta(hours=Config.RATE_LIMIT_WINDOW_HOURS)

    if user_id not in _rate_limit_state:
        _rate_limit_state[user_id] = (1, now)
        logger.debug("Rate limit: new window for user %s (1/%d)", user_id, limit)
        return False, None, (1 == limit)

    count, window_start = _rate_limit_state[user_id]

    if now - window_start > window:
        _rate_limit_state[user_id] = (1, now)
        logger.debug("Rate limit: window expired, reset for user %s (1/%d)", user_id, limit)
        return False, None, (1 == limit)

    if count < limit:
        _rate_limit_state[user_id] = (count + 1, window_start)
        logger.debug("Rate limit: user %s request %d/%d", user_id, count + 1, limit)
        return False, None, (count + 1 == limit)

    reset_time = window_start + window
    logger.warning("Rate limit exceeded for user %s (%d/%d), resets at %s", user_id, count, limit, reset_time.isoformat())
    return True, reset_time, False

async def channel_check(interaction: discord.Interaction) -> bool:
    logger.info("channel_check called: user=%s, channel_id=%s, guild=%s",
                interaction.user.name, interaction.channel_id, interaction.guild.name if interaction.guild else None)
    if interaction.channel_id in Config.ALLOWED_CHANNELS:
        logger.info("Access granted for user %s in allowed channel %s", interaction.user.name, interaction.channel_id)
        return True
    if interaction.user.id in Config.OVERRIDE_USERS:
        logger.info("Access granted for override user %s", interaction.user.name)
        return True

    # Check if user is in an authorized server
    if interaction.guild and interaction.guild.id in Config.AUTHORIZED_SERVERS:
        logger.info("Access granted for user %s in authorized server %s", interaction.user.name, interaction.guild.name)
        return True

    # Get member roles if in a guild
    if interaction.guild:
        member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            logger.info("Member not in cache, fetching from API for user %s (id=%s)", interaction.user.name, interaction.user.id)
            try:
                member = await interaction.guild.fetch_member(interaction.user.id)
            except discord.NotFound:
                logger.warning("Member %s (id=%s) not found in guild %s",
                               interaction.user.name, interaction.user.id, interaction.guild.name)
            except discord.HTTPException as e:
                logger.warning("Failed to fetch member %s: %s", interaction.user.name, e)
        if member:
            member_role_ids = [role.id for role in member.roles]
            logger.info("Role check for user %s: member_role_ids=%s, allowed_roles=%s",
                        interaction.user.name, member_role_ids, Config.ALLOWED_ROLES)
            if any(role.id in Config.ALLOWED_ROLES for role in member.roles):
                logger.info("Access granted for user %s via allowed role", interaction.user.name)
                return True
            else:
                logger.info("No matching roles for user %s", interaction.user.name)
        else:
            logger.warning("Could not get member object for user %s (id=%s) in guild %s",
                           interaction.user.name, interaction.user.id, interaction.guild.name)
    else:
        logger.warning("No guild context for interaction from user %s", interaction.user.name)

    logger.info("Access denied for user %s in channel %s", interaction.user.name, interaction.channel_id)
    return False
