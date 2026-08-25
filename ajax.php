<?php
ob_start();
date_default_timezone_set("Asia/Manila");

// admin_class.php starts the session, so $_SESSION is populated by the include.
include 'admin_class.php';

$action = isset($_GET['action']) ? $_GET['action'] : '';

// Every callable action must be listed here with the roles permitted to call it.
// Role ids match $_SESSION['login_type']: 1 = admin, 2 = faculty, 3 = student.
// 'public' means no session is required. An action absent from this map is a 404,
// which is what makes the dynamic dispatch below safe.
$permissions = array(
	'login'                  => array('public'),
	'logout'                 => array(1, 2, 3),
	'update_user'            => array(1, 2, 3),

	'save_evaluation'        => array(3),
	'get_class'              => array(1, 2),
	'get_report'             => array(1, 2),

	'signup'                 => array(1),
	'save_user'              => array(1),
	'delete_user'            => array(1),
	'save_faculty'           => array(1),
	'delete_faculty'         => array(1),
	'save_student'           => array(1),
	'delete_student'         => array(1),
	'save_subject'           => array(1),
	'delete_subject'         => array(1),
	'save_class'             => array(1),
	'delete_class'           => array(1),
	'save_academic'          => array(1),
	'delete_academic'        => array(1),
	'make_default'           => array(1),
	'save_criteria'          => array(1),
	'delete_criteria'        => array(1),
	'save_criteria_order'    => array(1),
	'save_question'          => array(1),
	'delete_question'        => array(1),
	'save_question_order'    => array(1),
	'save_restriction'       => array(1),
);

if (!isset($permissions[$action])) {
	http_response_code(404);
	ob_end_flush();
	exit;
}

$allowed = $permissions[$action];
if (!in_array('public', $allowed, true)) {
	$role = isset($_SESSION['login_type']) ? (int) $_SESSION['login_type'] : 0;
	if (!in_array($role, $allowed, true)) {
		http_response_code(403);
		ob_end_flush();
		exit;
	}
}

// Constructed only after the check, so an unauthorized request never opens a
// database connection.
$crud = new Action();
$result = $crud->{$action}();
if ($result) {
	echo $result;
}

ob_end_flush();
