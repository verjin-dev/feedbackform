<?php
// Credentials are read from config.local.php (git-ignored) or the environment.
// Never commit real credentials to this repository. See config.local.example.php.

$conf = array();
if (file_exists(__DIR__ . '/config.local.php')) {
	$conf = include __DIR__ . '/config.local.php';
	if (!is_array($conf)) {
		$conf = array();
	}
}

$db_host = isset($conf['host']) ? $conf['host'] : (getenv('DB_HOST') ?: 'localhost');
$db_user = isset($conf['user']) ? $conf['user'] : (getenv('DB_USER') ?: '');
$db_pass = isset($conf['pass']) ? $conf['pass'] : (getenv('DB_PASS') ?: '');
$db_name = isset($conf['name']) ? $conf['name'] : (getenv('DB_NAME') ?: 'evaluation_db');

$conn = @new mysqli($db_host, $db_user, $db_pass, $db_name);

if ($conn->connect_errno) {
	// Log the detail; never render connection internals to the browser.
	error_log('DB connection failed: ' . $conn->connect_error);
	http_response_code(500);
	exit('Database unavailable. Please try again later.');
}

$conn->set_charset('utf8mb4');
