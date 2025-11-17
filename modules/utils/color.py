"""Image color analysis for game cover art.

This module provides utilities for analyzing dominant colors in game cover
images using k-means clustering. The primary use case is extracting theme
colors from game artwork to enhance visualization in Home Assistant dashboards.

The module can process images from both local file paths and remote URLs,
making it suitable for analyzing game covers fetched from IGDB or other
game databases.

Algorithm:
    Uses k-means clustering on RGB pixel values to identify the most
    common color in an image. Images are downsampled to 100x100 pixels
    for performance, which is sufficient for dominant color detection.

Example:
    >>> from modules.utils.color import get_dominant_color
    >>>
    >>> # From local file
    >>> color = get_dominant_color("/path/to/game_cover.jpg")
    >>> print(f"RGB: {color}")
    (45, 123, 200)
    >>>
    >>> # From URL
    >>> color = get_dominant_color("https://example.com/cover.jpg")
    >>> print(f"RGB: {color}")
    (180, 50, 90)
    >>>
    >>> # Use for Home Assistant theme color
    >>> r, g, b = color
    >>> hex_color = f"#{r:02x}{g:02x}{b:02x}"
    >>> print(f"Hex color: {hex_color}")
    'Hex color: #2d7bc8'
"""

# Standard library imports
from io import BytesIO

# Third-party imports
import imageio.v3 as iio
import numpy as np
import requests
from scipy.ndimage import zoom
from sklearn.cluster import KMeans


def load_image(image_source):
    """Load and preprocess an image from file path or URL.

    Loads an image from either a local file path or remote URL, converts
    it to RGB format, and resizes to 100x100 pixels for efficient processing.

    Uses imageio for image decoding - a lighter alternative to Pillow that
    supports all common formats (JPEG, PNG, GIF, etc.) without system dependencies.

    Args:
        image_source: Path to local image file or HTTP/HTTPS URL.

    Returns:
        numpy array of shape (100, 100, 3) with RGB values (0-255).

    Raises:
        requests.RequestException: If URL fetch fails.
        ValueError: If image format is unsupported.
        FileNotFoundError: If local file doesn't exist.

    Example:
        >>> # Load from local file
        >>> img = load_image("/path/to/cover.jpg")
        >>> print(img.shape)
        (100, 100, 3)

        >>> # Load from URL
        >>> img = load_image("https://example.com/cover.png")
        >>> print(img.dtype)
        uint8
    """
    # Load image from URL or file
    if image_source.startswith("http://") or image_source.startswith("https://"):
        response = requests.get(image_source, timeout=10)
        response.raise_for_status()
        img_array = iio.imread(BytesIO(response.content))
    else:
        img_array = iio.imread(image_source)

    # Ensure RGB format
    if img_array.ndim == 2:  # Grayscale
        img_array = np.stack([img_array] * 3, axis=-1)
    elif img_array.shape[2] == 4:  # RGBA
        img_array = img_array[..., :3]

    # Resize to 100x100 using bilinear interpolation
    h, w = img_array.shape[:2]
    zoom_h, zoom_w = 100 / h, 100 / w
    img_resized = zoom(img_array, (zoom_h, zoom_w, 1), order=1)

    return img_resized.astype(np.uint8)


def get_dominant_color(image_source, k=3):
    """Extract the dominant color from an image using k-means clustering.

    Analyzes an image to find its most prominent color by clustering all
    pixels into k groups and returning the center of the largest cluster.
    This provides a representative color for the image that can be used
    for theming or visualization.

    The algorithm:
    1. Load and resize image to 100x100 pixels
    2. Flatten pixel array to list of RGB values
    3. Cluster pixels into k groups using k-means
    4. Return the centroid of the largest cluster

    Args:
        image_source: Path to local image file or HTTP/HTTPS URL.
        k: Number of color clusters (default: 3). Higher values may capture
           more color nuances but can be slower. 3-5 is typically sufficient.

    Returns:
        Tuple of (R, G, B) integers representing the dominant color.
        Each value is in range 0-255.

    Example:
        >>> # Basic usage
        >>> color = get_dominant_color("game_cover.jpg")
        >>> print(f"RGB: {color}")
        RGB: (45, 123, 200)

        >>> # Use more clusters for complex images
        >>> color = get_dominant_color("colorful_cover.jpg", k=5)
        >>> print(color)
        (89, 156, 78)

        >>> # Convert to hex for CSS/HTML
        >>> r, g, b = get_dominant_color("cover.jpg")
        >>> hex_color = f"#{r:02x}{g:02x}{b:02x}"
        >>> print(hex_color)
        '#2d7bc8'
    """
    image_np = load_image(image_source)
    image_np = image_np.reshape((-1, 3))

    # Find the most common color
    kmeans = KMeans(n_clusters=k, n_init=10, random_state=42)
    kmeans.fit(image_np)

    # Get the color with the largest cluster
    unique, counts = np.unique(kmeans.labels_, return_counts=True)
    dominant_color = kmeans.cluster_centers_[unique[np.argmax(counts)]]

    # Return the dominant color as a tuple
    return tuple(map(int, dominant_color))
