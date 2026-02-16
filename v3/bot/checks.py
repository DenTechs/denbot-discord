import discord
from bot.config import Config
import logging
from bot.logger import logger

async def channel_check(interaction: discord.Interaction) -> bool:
    logger.info("channel_check called: user=%s, channel_id=%s, guild=%s",
                interaction.user.name, interaction.channel_id, interaction.guild.name if interaction.guild else None)
    if interaction.channel_id in Config.ALLOWED_CHANNELS:
        logger.info("Access granted for user %s in allowed channel %s", interaction.user.name, interaction.channel_id)
        return True
    if interaction.user.id in Config.OVERRIDE_USERS:
        logger.info("Access granted for override user %s", interaction.user.name)
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
