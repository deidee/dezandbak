from PIL import Image
from PIL import ImageDraw

img = Image.new("CMYK", (480, 480))
draw = ImageDraw.Draw(img)
draw.text((0, 0),"Hello, World!",(255,0,255))
img.save('test.pdf')
