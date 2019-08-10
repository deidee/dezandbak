<?php

require_once '../../vendor/autoload.php';

use ScssPhp\ScssPhp\Compiler;

$scss = new Compiler();

$code = file_get_contents('../kleurmanipulatie.scss');

echo $scss->compile($code);
