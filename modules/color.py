# Standard library imports
from io import BytesIO

# Third-party imports
import numpy as np
import requests
from PIL import Image
from sklearn.cluster import KMeans

def load_image(image_source):
    # Handle bot local and remote images
    if image_source.startswith('http://') or image_source.startswith('https://'):
        response = requests.get(image_source)
        img = Image.open(BytesIO(response.content))
    else:
        img = Image.open(image_source)
    
    # Convert image to a manageable size (for performance)
    img = img.convert("RGB").resize((100, 100))
    return img

def get_dominant_color(image_source, k=3):
    image = load_image(image_source)
    image_np = np.array(image)
    image_np = image_np.reshape((-1, 3))

    # Find the most common color
    kmeans = KMeans(n_clusters=k)
    kmeans.fit(image_np)
    
    # Get the color with the largest cluster
    unique, counts = np.unique(kmeans.labels_, return_counts=True)
    dominant_color = kmeans.cluster_centers_[unique[np.argmax(counts)]]
    
    # Return the dominant color as a tuple
    return tuple(map(int, dominant_color))
