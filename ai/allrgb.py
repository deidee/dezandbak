# Import the necessary libraries
from PIL import Image

# Create a new image with the appropriate dimensions
width = 4096
height = 4096
image = Image.new("RGB", (width, height))

# Iterate over all possible values of red, green, and blue
for red in range(0, 256):
  for green in range(0, 256):
    for blue in range(0, 256):
      # Calculate the x and y coordinates of the current pixel
      x = red * 16 + green // 16
      y = green % 16 * 256 + blue
      # Set the corresponding pixel in the image to the current color
      image.putpixel((x, y), (red, green, blue))

# Save the image to a file
image.save("all_colors.png")
