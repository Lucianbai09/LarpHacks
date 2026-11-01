from io import BytesIO

from PIL import Image, ImageOps

MAX_PHOTO_MB = 10
MAX_PHOTO_SIDE = 1280

# Refuses images that would fill the server's memory once decoded. Pillow raises an error at twice this.
Image.MAX_IMAGE_PIXELS = 25_000_000


def to_jpeg(image):
    output = BytesIO()
    image.save(output, "JPEG", quality=80)
    return output.getvalue()


def clean_photo(upload):
    """Redraws an upload as a small JPEG, which drops any hidden script and the GPS location phones add.

    Returns None if it isn't a picture we can read.
    """
    try:
        with Image.open(upload, formats=["JPEG", "PNG", "WEBP", "GIF"]) as image:
            image.draft("RGB", (MAX_PHOTO_SIDE, MAX_PHOTO_SIDE))
            upright = ImageOps.exif_transpose(image).convert("RGB")
            upright.thumbnail((MAX_PHOTO_SIDE, MAX_PHOTO_SIDE))
            return to_jpeg(upright)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None
