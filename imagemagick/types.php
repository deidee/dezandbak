<?php

$format = 'svg';

$im = new Imagick;
$im->newImage(300, 300, new ImagickPixel('#ffffff'));
$im->setImageFormat($format);

$draw = new ImagickDraw();
$draw->setStrokeWidth(0);
$draw->setFillColor(new ImagickPixel('#ff0000'));
$draw->setFillOpacity(.5);
$draw->rectangle(50, 50, 249, 249);

$im->drawImage($draw);

header('Content-Type: ' . $im->getImageMimeType());

echo $im;
