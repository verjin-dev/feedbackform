<?php
// Shared access check for every page under admin/, faculty/ and student/.
//
// These files are reachable directly by URL — several are loaded that way on
// purpose, through uni_modal() — so routing alone never protected them. Before
// this guard existed, GET /admin/manage_class.php?id=1 executed an
// unauthenticated query against the database.

if (session_status() === PHP_SESSION_NONE) {
	session_start();
}

// Role ids match $_SESSION['login_type']: 1 = admin, 2 = faculty, 3 = student.
function require_role($roles)
{
	$role = isset($_SESSION['login_type']) ? (int) $_SESSION['login_type'] : 0;

	if (!in_array($role, (array) $roles, true)) {
		if (!headers_sent()) {
			http_response_code($role === 0 ? 401 : 403);
		}
		exit('Forbidden.');
	}
}
