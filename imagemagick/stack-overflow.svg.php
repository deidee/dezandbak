<?php

$im = new Imagick;
$im->newImage(300, 300, new ImagickPixel('#ffffff'));
$im->setImageFormat('svg');

$im1 = new Imagick();
$im1->newImage(300, 300, new ImagickPixel('#ffffff'));
$im1->setImageFormat('png');
$fillColor = new ImagickPixel('#ff0000');
$draw = new ImagickDraw();
$draw->setFillColor($fillColor);
$draw->setStrokeWidth(0);
$draw->setFillOpacity(.5);
$draw->rectangle(50, 50, 249, 249);
$im1->drawImage($draw);

$im->compositeImage($im1->getimage(), Imagick::COMPOSITE_COPY, 0, 0);

header('Content-Type: image/svg+xml');

echo $im->getImageBlob();
