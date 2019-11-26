<?php

$im = new Imagick;
$im->newImage(300, 300, new ImagickPixel('#ff0000'));
$im->setImageFormat('gif');
$im->setImageIterations(0);

$frame = new Imagick;
$frame->newImage(300, 300, new ImagickPixel('#00ff00'));
$frame->setImageFormat('gif');
$frame->setImageDelay(10);

$im->addImage($frame);

header('Content-Type: ' . $im->getImageMimeType());

echo $im->getImagesBlob();
