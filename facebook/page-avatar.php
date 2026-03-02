<?php
declare(strict_types=1);

/*
 * facebook-page-avatar-url.php
 *
 * Very basic demo:
 * - Enter a publicly reachable image URL
 * - POST it to /{page-id}/picture
 *
 * Config:
 * - Reads config from ../config.ini
 *
 * Example config.ini:
 *
 * [facebook]
 * page_id = "123456789012345"
 * page_access_token = "EAAB..."
 * graph_version = "v25.0"
 *
 * SECURITY NOTE:
 * - Keep config.ini outside the public web root if possible.
 * - Do not expose this script publicly without authentication.
 */

function h(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES, 'UTF-8');
}

function loadConfig(): array
{
    $configPath = dirname(__DIR__) . DIRECTORY_SEPARATOR . 'config.ini';

    if (!is_file($configPath)) {
        throw new RuntimeException('Config file not found: ' . $configPath);
    }

    $config = parse_ini_file($configPath, true, INI_SCANNER_TYPED);

    if ($config === false) {
        throw new RuntimeException('Could not parse config file: ' . $configPath);
    }

    $fb = $config['facebook'] ?? null;
    if (!is_array($fb)) {
        throw new RuntimeException('Missing [facebook] section in config.ini');
    }

    $pageId = trim((string)($fb['page_id'] ?? ''));
    $pageAccessToken = trim((string)($fb['page_access_token'] ?? ''));
    $graphVersion = trim((string)($fb['graph_version'] ?? 'v25.0'));

    if ($pageId === '') {
        throw new RuntimeException('Missing facebook.page_id in config.ini');
    }

    if ($pageAccessToken === '') {
        throw new RuntimeException('Missing facebook.page_access_token in config.ini');
    }

    if ($graphVersion === '') {
        $graphVersion = 'v25.0';
    }

    return [
            'page_id' => $pageId,
            'page_access_token' => $pageAccessToken,
            'graph_version' => $graphVersion,
            'config_path' => $configPath,
    ];
}

function graphPost(string $graphVersion, string $endpoint, array $fields): array
{
    $url = 'https://graph.facebook.com/' . $graphVersion . '/' . ltrim($endpoint, '/');

    $ch = curl_init($url);
    curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => http_build_query($fields),
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 60,
    ]);

    $raw = curl_exec($ch);
    $curlErr = curl_error($ch);
    $httpCode = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($raw === false) {
        throw new RuntimeException('cURL error: ' . $curlErr);
    }

    $json = json_decode($raw, true);

    if (!is_array($json)) {
        throw new RuntimeException("Unexpected response (HTTP {$httpCode}): " . $raw);
    }

    if (isset($json['error'])) {
        $message = $json['error']['message'] ?? 'Unknown Graph API error';
        $type = $json['error']['type'] ?? 'GraphMethodException';
        $code = $json['error']['code'] ?? 'n/a';
        throw new RuntimeException("Facebook API error: {$message} [{$type}, code {$code}]");
    }

    return [
            'http_code' => $httpCode,
            'body' => $json,
            'raw' => $raw,
    ];
}

$status = null;
$error = null;
$debug = [];
$pictureUrl = '';

try {
    $cfg = loadConfig();
} catch (Throwable $e) {
    $cfg = null;
    $error = $e->getMessage();
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $cfg !== null) {
    try {
        $pictureUrl = trim((string)($_POST['picture_url'] ?? ''));

        if ($pictureUrl === '') {
            throw new RuntimeException('Please enter an image URL.');
        }

        if (!filter_var($pictureUrl, FILTER_VALIDATE_URL)) {
            throw new RuntimeException('Please enter a valid absolute URL.');
        }

        $parts = parse_url($pictureUrl);
        $scheme = strtolower((string)($parts['scheme'] ?? ''));
        if (!in_array($scheme, ['http', 'https'], true)) {
            throw new RuntimeException('Only http:// and https:// URLs are supported.');
        }

        $pictureUpdate = graphPost(
                $cfg['graph_version'],
                $cfg['page_id'] . '/picture',
                [
                        'access_token' => $cfg['page_access_token'],
                        'picture' => $pictureUrl,
                        'profile_pic_method' => 'custom',
                ]
        );

        $debug['picture_response'] = $pictureUpdate['body'];
        $status = 'Profile picture updated successfully.';
    } catch (Throwable $e) {
        $error = $e->getMessage();
    }
}
?>
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Update Facebook Page Profile Picture</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body{
            font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
            margin: 2rem;
            line-height: 1.45;
            background: #f7f7f8;
            color: #111;
        }
        .box{
            max-width: 46rem;
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 10px;
            padding: 1.25rem;
            box-shadow: 0 8px 24px rgba(0,0,0,.05);
        }
        h1{
            margin-top: 0;
            font-size: 1.4rem;
        }
        .row{
            margin: 1rem 0;
        }
        input[type="url"]{
            display: block;
            width: 100%;
            box-sizing: border-box;
            margin-top: .5rem;
            padding: .8rem .9rem;
            border: 1px solid #ccc;
            border-radius: 8px;
            font: inherit;
        }
        button{
            padding: .8rem 1rem;
            border: 0;
            border-radius: 8px;
            background: #1877f2;
            color: #fff;
            font-weight: 600;
            cursor: pointer;
        }
        button:hover{
            opacity: .95;
        }
        .ok, .err{
            margin: 1rem 0;
            padding: .85rem 1rem;
            border-radius: 8px;
        }
        .ok{
            background: #eaf8ee;
            color: #185c2b;
            border: 1px solid #b9e2c5;
        }
        .err{
            background: #fff0f0;
            color: #8a1f1f;
            border: 1px solid #efc2c2;
        }
        pre{
            overflow: auto;
            background: #111;
            color: #f3f3f3;
            padding: 1rem;
            border-radius: 8px;
            font-size: .9rem;
        }
        .note{
            color: #555;
            font-size: .95rem;
        }
        code{
            background: #f1f1f1;
            padding: .15rem .35rem;
            border-radius: 4px;
        }
    </style>
</head>
<body>
<div class="box">
    <h1>Update Facebook Page profile picture</h1>

    <p class="note">
        Paste a direct image URL that Facebook/Meta can fetch, then press the button.
    </p>

    <?php if ($status !== null): ?>
        <div class="ok"><?= h($status) ?></div>
    <?php endif; ?>

    <?php if ($error !== null): ?>
        <div class="err"><?= h($error) ?></div>
    <?php endif; ?>

    <form method="post">
        <div class="row">
            <label for="picture_url"><strong>Image URL</strong></label>
            <input
                    type="url"
                    name="picture_url"
                    id="picture_url"
                    placeholder="https://example.com/path/to/avatar.jpg"
                    value="<?= h($pictureUrl) ?>"
                    required
            >
        </div>

        <div class="row">
            <button type="submit">Replace profile picture</button>
        </div>
    </form>

    <?php if ($cfg !== null): ?>
        <p class="note">
            Loaded config from <code><?= h($cfg['config_path']) ?></code>
        </p>
    <?php endif; ?>

    <?php if (!empty($debug)): ?>
        <h2>API response</h2>
        <pre><?= h(json_encode($debug, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)) ?></pre>
    <?php endif; ?>
</div>
</body>
</html>