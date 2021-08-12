from PIL import Image

print('Hello, World!')

img = Image.open('177525_10150987745223956_1777701739_o.jpg')
img.rotate(90).show()
