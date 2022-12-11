# Import the necessary libraries
import random
from PIL import Image

# Create a new image with the appropriate dimensions
width = 4096  # The image should be 4096 by 4096 pixels
height = 4096
image = Image.new("RGB", (width, height))

# Create a list of all possible colors
colors = [(red, green, blue) for red in range(0, 256) for green in range(0, 256) for blue in range(0, 256)]

# Shuffle the colors using a random number generator
random.shuffle(colors)

# Iterate over all pixels in the image and assign each pixel a randomly shuffled color
for x in range(0, width):
  for y in range(0, height):
    image.putpixel((x, y), colors[x * width + y])

# Save the image to a file
image.save("shuffled_colors.png")
