"""
Image processing utilities for Discord attachments.

Handles downloading, resizing, and encoding images for Claude API.
"""
import io
import base64
import aiohttp
from PIL import Image
from bot.logger import logger
from bot.config import Config
import discord


SUPPORTED_IMAGE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/webp": "webp",
    "image/gif": "gif"
}


def is_image_attachment(attachment: discord.Attachment) -> bool:
    """
    Check if a Discord attachment is a supported image type.

    Args:
        attachment: Discord attachment object

    Returns:
        True if the attachment is a supported image format
    """
    return attachment.content_type and attachment.content_type.lower() in SUPPORTED_IMAGE_TYPES


async def download_attachment(attachment: discord.Attachment) -> bytes:
    """
    Download an image attachment from Discord CDN.

    Args:
        attachment: Discord attachment object

    Returns:
        Image bytes

    Raises:
        aiohttp.ClientError: If download fails
        ValueError: If file size exceeds limit
    """
    # Check file size
    max_bytes = Config.IMAGE_MAX_FILE_SIZE_MB * 1024 * 1024
    if attachment.size > max_bytes:
        raise ValueError(f"Image file size ({attachment.size / 1024 / 1024:.2f}MB) exceeds limit ({Config.IMAGE_MAX_FILE_SIZE_MB}MB)")

    # Download the image
    async with aiohttp.ClientSession() as session:
        async with session.get(attachment.url) as response:
            response.raise_for_status()
            return await response.read()


def resize_image(image_bytes: bytes, max_dimensions: int) -> bytes:
    """
    Resize an image maintaining aspect ratio and convert to JPEG.

    Args:
        image_bytes: Original image bytes
        max_dimensions: Maximum width or height in pixels

    Returns:
        Resized image bytes in JPEG format
    """
    # Open image
    image = Image.open(io.BytesIO(image_bytes))

    # Convert RGBA to RGB (handle transparency)
    if image.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode == "P":
            image = image.convert("RGBA")
        background.paste(image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None)
        image = background

    # Calculate new dimensions
    width, height = image.size
    if width <= max_dimensions and height <= max_dimensions:
        # No resize needed
        pass
    elif width > height:
        new_width = max_dimensions
        new_height = int((max_dimensions / width) * height)
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    else:
        new_height = max_dimensions
        new_width = int((max_dimensions / height) * width)
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Convert to JPEG bytes
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=85, optimize=True)
    return output.getvalue()


def encode_image_to_base64(image_bytes: bytes) -> str:
    """
    Encode image bytes to base64 string.

    Args:
        image_bytes: Image bytes

    Returns:
        Base64 encoded string
    """
    return base64.b64encode(image_bytes).decode("utf-8")


async def process_discord_attachment(attachment: discord.Attachment, max_dimensions: int) -> dict | None:
    """
    Process a Discord image attachment into a Claude-compatible content block.

    Downloads, resizes, and encodes the image as base64 for the Claude API.

    Args:
        attachment: Discord attachment object
        max_dimensions: Maximum width/height for resizing

    Returns:
        Claude image content block dict, or None if processing fails
    """
    try:
        # Validate file type
        if not is_image_attachment(attachment):
            logger.debug(f"Skipping non-image attachment: {attachment.filename} ({attachment.content_type})")
            return None

        logger.debug(f"Processing image: {attachment.filename} ({attachment.size / 1024:.2f}KB)")

        # Download image
        image_bytes = await download_attachment(attachment)

        # Resize and convert to JPEG
        resized_bytes = resize_image(image_bytes, max_dimensions)

        # Encode to base64
        base64_data = encode_image_to_base64(resized_bytes)

        logger.debug(f"Successfully processed image: {attachment.filename} ({len(resized_bytes) / 1024:.2f}KB after resize)")

        # Return Claude-compatible content block
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64_data
            }
        }

    except ValueError as e:
        logger.warning(f"Image validation failed for {attachment.filename}: {e}")
        return None

    except aiohttp.ClientError as e:
        logger.error(f"Failed to download image {attachment.filename}: {e}")
        return None

    except Exception as e:
        logger.error(f"Failed to process image {attachment.filename}: {e}", exc_info=True)
        return None
