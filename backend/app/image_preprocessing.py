"""Shared training-export and deployment image preprocessing contract."""
from PIL import Image


def prepare_image(image, image_size):
    import numpy as np
    image = image.convert("RGB")
    width, height = image.size
    resized = (image_size, int(image_size * height / width)) if width <= height else (
        int(image_size * width / height), image_size)
    image = image.resize(resized, Image.Resampling.BILINEAR)
    left = int(round((image.width - image_size) / 2))
    top = int(round((image.height - image_size) / 2))
    image = image.crop((left, top, left + image_size, top + image_size))
    return np.ascontiguousarray(np.asarray(image, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0)
