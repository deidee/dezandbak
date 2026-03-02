<?php
declare(strict_types=1);

/*
 * facebook-page-avatar.php
 *
 * Very basic demo:
 * - Upload an image from your browser
 * - POST it to /{page-id}/photos
 * - POST the returned photo ID to /{page-id}/picture
 *
 * Before using:
 * 1. Create a Meta app
 * 2. Obtain a PAGE access token for the page you manage
 * 3. Fill in PAGE_ID and PAGE_ACCESS_TOKEN below
 *
 * SECURITY NOTE:
 * - Do not leave this file publicly exposed without authentication.
 * - Move secrets into environment variables for production use.
 */

const GRAPH_VERSION = 'v25.0';
const PAGE_ID = 'YOUR_PAGE_ID';
const PAGE_ACCESS_TOKEN = 'YOUR_PAGE_ACCESS_TOKEN';

function h(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES, 'UTF-8');
}

function graphPost(string $endpoint, array $fields): array
{
    $url = 'https://graph.facebook.com/' . GRAPH_VERSION . '/' . ltrim($endpoint, '/');

    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => $fields,
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

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    try {
        if (PAGE_ID === 'YOUR_PAGE_ID' || PAGE_ACCESS_TOKEN === 'YOUR_PAGE_ACCESS_TOKEN') {
            throw new RuntimeException('Please set PAGE_ID and PAGE_ACCESS_TOKEN in the PHP file first.');
        }

        if (!isset($_FILES['avatar']) || $_FILES['avatar']['error'] !== UPLOAD_ERR_OK) {
            throw new RuntimeException('Please choose an image file first.');
        }

        $tmpPath = $_FILES['avatar']['tmp_name'];
        $originalName = $_FILES['avatar']['name'] ?? 'upload.jpg';
        $fileSize = (int) ($_FILES['avatar']['size'] ?? 0);

        if ($fileSize <= 0) {
            throw new RuntimeException('The uploaded file appears to be empty.');
        }

        // Basic MIME validation
        $finfo = new finfo(FILEINFO_MIME_TYPE);
        $mime = $finfo->file($tmpPath) ?: 'application/octet-stream';

        $allowed = [
            'image/jpeg',
            'image/png',
            'image/gif',
            'image/webp',
        ];

        if (!in_array($mime, $allowed, true)) {
            throw new RuntimeException('Unsupported file type: ' . $mime);
        }

        // Step 1: upload the image to the Page
        $photoUpload = graphPost(
            PAGE_ID . '/photos',
            [
                'access_token' => PAGE_ACCESS_TOKEN,
                // Keep it out of the public feed if possible
                'published' => 'false',
                'source' => new CURLFile($tmpPath, $mime, $originalName),
            ]
        );

        $photoId = $photoUpload['body']['id'] ?? null;
        if (!$photoId) {
            throw new RuntimeException('Upload succeeded, but no photo ID was returned.');
        }

        $debug['upload_response'] = $photoUpload['body'];

        // Step 2: set that uploaded photo as the Page profile picture
        $pictureUpdate = graphPost(
            PAGE_ID . '/picture',
            [
                'access_token' => PAGE_ACCESS_TOKEN,
                'photo' => (string) $photoId,
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
        body {
            font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
            margin: 2rem;
            line-height: 1.45;
            background: #f7f7f8;
            color: #111;
        }
        .box {
            max-width: 42rem;
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 10px;
            padding: 1.25rem;
            box-shadow: 0 8px 24px rgba(0,0,0,.05);
        }
        h1 {
            margin-top: 0;
            font-size: 1.4rem;
        }
        .row {
            margin: 1rem 0;
        }
        input[type="file"] {
            display: block;
            margin-top: .5rem;
        }
        button {
            padding: .8rem 1rem;
            border: 0;
            border-radius: 8px;
            background: #1877f2;
            color: #fff;
            font-weight: 600;
            cursor: pointer;
        }
        button:hover {
            opacity: .95;
        }
        .ok, .err {
            margin: 1rem 0;
            padding: .85rem 1rem;
            border-radius: 8px;
        }
        .ok {
            background: #eaf8ee;
            color: #185c2b;
            border: 1px solid #b9e2c5;
        }
        .err {
            background: #fff0f0;
            color: #8a1f1f;
            border: 1px solid #efc2c2;
        }
        pre {
            overflow: auto;
            background: #111;
            color: #f3f3f3;
            padding: 1rem;
            border-radius: 8px;
            font-size: .9rem;
        }
        .note {
            color: #555;
            font-size: .95rem;
        }
        code {
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
        This uploads a local image and then tells the Facebook Graph API to use it as the Page avatar.
    </p>

    <?php if ($status !== null): ?>
        <div class="ok"><?= h($status) ?></div>
    <?php endif; ?>

    <?php if ($error !== null): ?>
        <div class="err"><?= h($error) ?></div>
    <?php endif; ?>

    <form method="post" enctype="multipart/form-data">
        <div class="row">
            <label for="avatar"><strong>Select image</strong></label>
            <input type="file" name="avatar" id="avatar" accept="image/*" required>
        </div>

        <div class="row">
            <button type="submit">Replace profile picture</button>
        </div>
    </form>

    <?php if (!empty($debug)): ?>
        <h2>API responses</h2>
        <pre><?= h(json_encode($debug, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)) ?></pre>
    <?php endif; ?>

    <p class="note">
        Recommended next step: move <code>PAGE_ID</code> and <code>PAGE_ACCESS_TOKEN</code> into environment variables and protect this page behind your own login.
    </p>
</div>
</body>
</html>