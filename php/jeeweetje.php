<?php

if(!function_exists('jw')) {
    function jw() {
        ob_start();
        $expression = func_get_args();
        call_user_func_array('var_dump', $expression);
        echo '<pre><code class="language-php">' . htmlentities(ob_get_clean()) . '</code></pre>';
    }
}

// Test.
jw(true, 1337, 'hoi', ['een ding', 'nog een ding'], (object) ['oop' => '<de-shit>']);
