from PIL import Image

img = Image.new("CMYK", (480, 480))
img.save('test.pdf')
