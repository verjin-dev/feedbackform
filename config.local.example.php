<?php
// Copy this file to config.local.php and fill in real values.
// config.local.php is git-ignored and must never be committed.
//
// Create a dedicated database user rather than reusing root:
//
//   CREATE USER 'evaluation_app'@'localhost' IDENTIFIED BY 'a-long-random-password';
//   GRANT SELECT, INSERT, UPDATE, DELETE ON evaluation_db.* TO 'evaluation_app'@'localhost';
//   FLUSH PRIVILEGES;
//
// The app needs no DDL rights in normal operation; schema changes are applied
// separately by an administrator.

return array(
	'host' => 'localhost',
	'user' => 'evaluation_app',
	'pass' => '',
	'name' => 'evaluation_db',
);
