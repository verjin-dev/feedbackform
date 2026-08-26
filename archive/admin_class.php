<?php
session_start();
ini_set('display_errors', 1);
Class Action {
	private $db;

	public function __construct() {
		ob_start();
   	include 'db_connect.php';
    
    $this->db = $conn;
	}
	function __destruct() {
	    $this->db->close();
	    ob_end_flush();
	}

	// Uploads land in assets/uploads/, which is web-served. Without an extension
	// allowlist an "avatar" can be a .php file, which lets any authenticated
	// account -- including a student, via update_user -- place a webshell.
	// The stored name is generated here and never taken from the client.
	private function store_upload($field, $dir = 'assets/uploads/'){
		if(!isset($_FILES[$field]) || !is_uploaded_file($_FILES[$field]['tmp_name']))
			return false;
		if($_FILES[$field]['error'] !== UPLOAD_ERR_OK)
			return false;
		if($_FILES[$field]['size'] > 2 * 1024 * 1024)
			return false;

		$allowed = array(
			IMAGETYPE_JPEG => 'jpg',
			IMAGETYPE_PNG  => 'png',
			IMAGETYPE_GIF  => 'gif',
			IMAGETYPE_WEBP => 'webp',
		);
		$info = @getimagesize($_FILES[$field]['tmp_name']);
		if($info === false || !isset($allowed[$info[2]]))
			return false;

		$fname = date('Ymd_His').'_'.bin2hex(random_bytes(8)).'.'.$allowed[$info[2]];
		if(!move_uploaded_file($_FILES[$field]['tmp_name'], $dir.$fname))
			return false;
		@chmod($dir.$fname, 0644);
		return $fname;
	}

	function login(){
		// Hardened: the role selector is validated against a fixed table list and is
		// never used as client-supplied SQL; credentials are bound, not interpolated.
		$email    = isset($_POST['email']) ? trim($_POST['email']) : '';
		$password = isset($_POST['password']) ? $_POST['password'] : '';
		$login    = isset($_POST['login']) ? $_POST['login'] : '';

		$type  = array("","users","faculty_list","student_list");
		$type2 = array("","admin","faculty","student");

		if(!ctype_digit((string)$login) || (int)$login < 1 || (int)$login > 3)
			return 2;
		$login = (int)$login;
		$table = $type[$login];

		if($email === '' || $password === '')
			return 2;

		$stmt = $this->db->prepare("SELECT *,concat(firstname,' ',lastname) as name FROM {$table} where email = ? and password = ? limit 1");
		if(!$stmt)
			return 2;
		$hash = md5($password);
		$stmt->bind_param('ss', $email, $hash);
		$stmt->execute();
		$qry = $stmt->get_result();

		if($qry && $qry->num_rows > 0){
			foreach ($qry->fetch_array() as $key => $value) {
				if($key != 'password' && !is_numeric($key))
					$_SESSION['login_'.$key] = $value;
			}
			$_SESSION['login_type'] = $login;
			$_SESSION['login_view_folder'] = $type2[$login].'/';
			$stmt->close();

			$academic = $this->db->query("SELECT * FROM academic_list where is_default = 1 ");
			if($academic->num_rows > 0){
				foreach($academic->fetch_array() as $k => $v){
					if(!is_numeric($k))
						$_SESSION['academic'][$k] = $v;
				}
			}
			return 1;
		}
		$stmt->close();
		return 2;
	}
	function logout(){
		session_destroy();
		foreach ($_SESSION as $key => $value) {
			unset($_SESSION[$key]);
		}
		header("location:login.php");
	}
	function save_user(){
		extract($_POST);
		$data = "";
		foreach($_POST as $k => $v){
			if(!in_array($k, array('id','cpass','password')) && !is_numeric($k)){
				if(empty($data)){
					$data .= " $k='$v' ";
				}else{
					$data .= ", $k='$v' ";
				}
			}
		}
		if(!empty($password)){
					$data .= ", password=md5('$password') ";

		}
		$check = $this->db->query("SELECT * FROM users where email ='$email' ".(!empty($id) ? " and id != {$id} " : ''))->num_rows;
		if($check > 0){
			return 2;
			exit;
		}
		if(isset($_FILES['img']) && $_FILES['img']['tmp_name'] != ''){
			$fname = $this->store_upload('img');
			if($fname !== false)
				$data .= ", avatar = '$fname' ";
			else
				error_log('rejected avatar upload in '.__FUNCTION__);
		}
		if(empty($id)){
			$save = $this->db->query("INSERT INTO users set $data");
		}else{
			$save = $this->db->query("UPDATE users set $data where id = $id");
		}

		if($save){
			return 1;
		}
	}
	function signup(){
		extract($_POST);
		$data = "";
		foreach($_POST as $k => $v){
			if(!in_array($k, array('id','cpass')) && !is_numeric($k)){
				if($k =='password'){
					if(empty($v))
						continue;
					$v = md5($v);

				}
				if(empty($data)){
					$data .= " $k='$v' ";
				}else{
					$data .= ", $k='$v' ";
				}
			}
		}

		$check = $this->db->query("SELECT * FROM users where email ='$email' ".(!empty($id) ? " and id != {$id} " : ''))->num_rows;
		if($check > 0){
			return 2;
			exit;
		}
		if(isset($_FILES['img']) && $_FILES['img']['tmp_name'] != ''){
			$fname = $this->store_upload('img');
			if($fname !== false)
				$data .= ", avatar = '$fname' ";
			else
				error_log('rejected avatar upload in '.__FUNCTION__);
		}
		if(empty($id)){
			$save = $this->db->query("INSERT INTO users set $data");

		}else{
			$save = $this->db->query("UPDATE users set $data where id = $id");
		}

		if($save){
			if(empty($id))
				$id = $this->db->insert_id;
			foreach ($_POST as $key => $value) {
				if(!in_array($key, array('id','cpass','password')) && !is_numeric($key))
					$_SESSION['login_'.$key] = $value;
			}
					$_SESSION['login_id'] = $id;
				if(isset($_FILES['img']) && !empty($_FILES['img']['tmp_name']))
					$_SESSION['login_avatar'] = $fname;
			return 1;
		}
	}

	function update_user(){
		// Updates the signed-in account's own profile, and nothing else.
		//
		// This function previously took the row id from the request, looped
		// every POST key into `SET $k='$v'`, and then copied every POST key
		// into $_SESSION['login_'.$key]. Posting id=2 therefore edited another
		// account -- including its password -- and simultaneously moved the
		// caller's session onto that account. A signed-in student could take
		// over any other student, and a faculty member any other faculty.
		//
		// The id now comes from the session, the writable columns are listed
		// explicitly, and the values are bound.
		$type = array("", "users", "faculty_list", "student_list");

		$role = isset($_SESSION['login_type']) ? (int)$_SESSION['login_type'] : 0;
		$id   = isset($_SESSION['login_id']) ? (int)$_SESSION['login_id'] : 0;
		if($role < 1 || $role > 3 || $id < 1)
			return 2;
		$table = $type[$role];

		$firstname = isset($_POST['firstname']) ? trim($_POST['firstname']) : '';
		$lastname  = isset($_POST['lastname']) ? trim($_POST['lastname']) : '';
		$email     = isset($_POST['email']) ? trim($_POST['email']) : '';
		$password  = isset($_POST['password']) ? $_POST['password'] : '';

		if($firstname === '' || $lastname === '' || $email === '')
			return 2;
		if(!filter_var($email, FILTER_VALIDATE_EMAIL))
			return 2;

		$check = $this->db->prepare("SELECT id FROM {$table} where email = ? and id != ? limit 1");
		if(!$check)
			return 2;
		$check->bind_param('si', $email, $id);
		$check->execute();
		$taken = $check->get_result();
		$clash = $taken && $taken->num_rows > 0;
		$check->close();
		if($clash)
			return 2;

		$columns = array('firstname = ?', 'lastname = ?', 'email = ?');
		$types   = 'sss';
		$values  = array($firstname, $lastname, $email);

		$avatar = false;
		if(isset($_FILES['img']) && $_FILES['img']['tmp_name'] != ''){
			$avatar = $this->store_upload('img');
			if($avatar === false){
				error_log('rejected avatar upload in '.__FUNCTION__);
			}else{
				$columns[] = 'avatar = ?';
				$types    .= 's';
				$values[]  = $avatar;
			}
		}

		if($password !== ''){
			// Still MD5, because that is what login() compares against until
			// the rebuild replaces it. Bound rather than interpolated.
			$columns[] = 'password = ?';
			$types    .= 's';
			$values[]  = md5($password);
		}

		$sql  = "UPDATE {$table} set ".implode(', ', $columns)." where id = ?";
		$types .= 'i';
		$values[] = $id;

		$stmt = $this->db->prepare($sql);
		if(!$stmt)
			return 2;
		$stmt->bind_param($types, ...$values);
		$ok = $stmt->execute();
		$stmt->close();

		if(!$ok)
			return 2;

		// Only the fields actually written are mirrored into the session, and
		// never login_id or login_type: those identify the account and must not
		// be movable by a request.
		$_SESSION['login_firstname'] = $firstname;
		$_SESSION['login_lastname']  = $lastname;
		$_SESSION['login_email']     = $email;
		$_SESSION['login_name']      = $firstname.' '.$lastname;
		if($avatar !== false)
			$_SESSION['login_avatar'] = $avatar;

		return 1;
	}
	function delete_user(){
		extract($_POST);
		$delete = $this->db->query("DELETE FROM users where id = ".$id);
		if($delete)
			return 1;
	}
	function save_system_settings(){
		extract($_POST);
		$data = '';
		foreach($_POST as $k => $v){
			if(!is_numeric($k)){
				if(empty($data)){
					$data .= " $k='$v' ";
				}else{
					$data .= ", $k='$v' ";
				}
			}
		}
		if(isset($_FILES['cover']) && $_FILES['cover']['tmp_name'] != ''){
			$fname = $this->store_upload('cover', '../assets/uploads/');
			if($fname !== false)
				$data .= ", cover_img = '$fname' ";
		}
		$chk = $this->db->query("SELECT * FROM system_settings");
		if($chk->num_rows > 0){
			$save = $this->db->query("UPDATE system_settings set $data where id =".$chk->fetch_array()['id']);
		}else{
			$save = $this->db->query("INSERT INTO system_settings set $data");
		}
		if($save){
			foreach($_POST as $k => $v){
				if(!is_numeric($k)){
					$_SESSION['system'][$k] = $v;
				}
			}
			if($_FILES['cover']['tmp_name'] != ''){
				$_SESSION['system']['cover_img'] = $fname;
			}
			return 1;
		}
	}
	function save_subject(){
		extract($_POST);
		$data = "";
		foreach($_POST as $k => $v){
			if(!in_array($k, array('id','user_ids')) && !is_numeric($k)){
				if(empty($data)){
					$data .= " $k='$v' ";
				}else{
					$data .= ", $k='$v' ";
				}
			}
		}
		$chk = $this->db->query("SELECT * FROM subject_list where code = '$code' and id != '{$id}' ")->num_rows;
		if($chk > 0){
			return 2;
		}
		if(empty($id)){
			$save = $this->db->query("INSERT INTO subject_list set $data");
		}else{
			$save = $this->db->query("UPDATE subject_list set $data where id = $id");
		}
		if($save){
			return 1;
		}
	}
	function delete_subject(){
		extract($_POST);
		$delete = $this->db->query("DELETE FROM subject_list where id = $id");
		if($delete){
			return 1;
		}
	}
	function save_class(){
		extract($_POST);
		$data = "";
		foreach($_POST as $k => $v){
			if(!in_array($k, array('id','user_ids')) && !is_numeric($k)){
				if(empty($data)){
					$data .= " $k='$v' ";
				}else{
					$data .= ", $k='$v' ";
				}
			}
		}
		$chk = $this->db->query("SELECT * FROM class_list where (".str_replace(",",'and',$data).") and id != '{$id}' ")->num_rows;
		if($chk > 0){
			return 2;
		}
		if(isset($user_ids)){
			$data .= ", user_ids='".implode(',',$user_ids)."' ";
		}
		if(empty($id)){
			$save = $this->db->query("INSERT INTO class_list set $data");
		}else{
			$save = $this->db->query("UPDATE class_list set $data where id = $id");
		}
		if($save){
			return 1;
		}
	}
	function delete_class(){
		extract($_POST);
		$delete = $this->db->query("DELETE FROM class_list where id = $id");
		if($delete){
			return 1;
		}
	}
	function save_academic(){
		extract($_POST);
		$data = "";
		foreach($_POST as $k => $v){
			if(!in_array($k, array('id','user_ids')) && !is_numeric($k)){
				if(empty($data)){
					$data .= " $k='$v' ";
				}else{
					$data .= ", $k='$v' ";
				}
			}
		}
		$chk = $this->db->query("SELECT * FROM academic_list where (".str_replace(",",'and',$data).") and id != '{$id}' ")->num_rows;
		if($chk > 0){
			return 2;
		}
		$hasDefault = $this->db->query("SELECT * FROM academic_list where is_default = 1")->num_rows;
		if($hasDefault == 0){
			$data .= " , is_default = 1 ";
		}
		if(empty($id)){
			$save = $this->db->query("INSERT INTO academic_list set $data");
		}else{
			$save = $this->db->query("UPDATE academic_list set $data where id = $id");
		}
		if($save){
			return 1;
		}
	}
	function delete_academic(){
		extract($_POST);
		$delete = $this->db->query("DELETE FROM academic_list where id = $id");
		if($delete){
			return 1;
		}
	}
	function make_default(){
		extract($_POST);
		$update= $this->db->query("UPDATE academic_list set is_default = 0");
		$update1= $this->db->query("UPDATE academic_list set is_default = 1 where id = $id");
		$qry = $this->db->query("SELECT * FROM academic_list where id = $id")->fetch_array();
		if($update && $update1){
			foreach($qry as $k =>$v){
				if(!is_numeric($k))
					$_SESSION['academic'][$k] = $v;
			}

			return 1;
		}
	}
	function save_criteria(){
		extract($_POST);
		$data = "";
		foreach($_POST as $k => $v){
			if(!in_array($k, array('id','user_ids')) && !is_numeric($k)){
				if(empty($data)){
					$data .= " $k='$v' ";
				}else{
					$data .= ", $k='$v' ";
				}
			}
		}
		$chk = $this->db->query("SELECT * FROM criteria_list where (".str_replace(",",'and',$data).") and id != '{$id}' ")->num_rows;
		if($chk > 0){
			return 2;
		}
		
		if(empty($id)){
			$lastOrder= $this->db->query("SELECT * FROM criteria_list order by abs(order_by) desc limit 1");
		$lastOrder = $lastOrder->num_rows > 0 ? $lastOrder->fetch_array()['order_by'] + 1 : 0;
		$data .= ", order_by='$lastOrder' ";
			$save = $this->db->query("INSERT INTO criteria_list set $data");
		}else{
			$save = $this->db->query("UPDATE criteria_list set $data where id = $id");
		}
		if($save){
			return 1;
		}
	}
	function delete_criteria(){
		extract($_POST);
		$delete = $this->db->query("DELETE FROM criteria_list where id = $id");
		if($delete){
			return 1;
		}
	}
	function save_criteria_order(){
		extract($_POST);
		$data = "";
		foreach($criteria_id as $k => $v){
			$update[] = $this->db->query("UPDATE criteria_list set order_by = $k where id = $v");
		}
		if(isset($update) && count($update)){
			return 1;
		}
	}

	function save_question(){
		extract($_POST);
		$data = "";
		foreach($_POST as $k => $v){
			if(!in_array($k, array('id','user_ids')) && !is_numeric($k)){
				if(empty($data)){
					$data .= " $k='$v' ";
				}else{
					$data .= ", $k='$v' ";
				}
			}
		}
		
		if(empty($id)){
			$lastOrder= $this->db->query("SELECT * FROM question_list where academic_id = $academic_id order by abs(order_by) desc limit 1");
			$lastOrder = $lastOrder->num_rows > 0 ? $lastOrder->fetch_array()['order_by'] + 1 : 0;
			$data .= ", order_by='$lastOrder' ";
			$save = $this->db->query("INSERT INTO question_list set $data");
		}else{
			$save = $this->db->query("UPDATE question_list set $data where id = $id");
		}
		if($save){
			return 1;
		}
	}
	function delete_question(){
		extract($_POST);
		$delete = $this->db->query("DELETE FROM question_list where id = $id");
		if($delete){
			return 1;
		}
	}
	function save_question_order(){
		extract($_POST);
		$data = "";
		foreach($qid as $k => $v){
			$update[] = $this->db->query("UPDATE question_list set order_by = $k where id = $v");
		}
		if(isset($update) && count($update)){
			return 1;
		}
	}
	function save_faculty(){
		extract($_POST);
		$data = "";
		foreach($_POST as $k => $v){
			if(!in_array($k, array('id','cpass','password')) && !is_numeric($k)){
				if(empty($data)){
					$data .= " $k='$v' ";
				}else{
					$data .= ", $k='$v' ";
				}
			}
		}
		if(!empty($password)){
					$data .= ", password=md5('$password') ";

		}
		$check = $this->db->query("SELECT * FROM faculty_list where email ='$email' ".(!empty($id) ? " and id != {$id} " : ''))->num_rows;
		if($check > 0){
			return 2;
			exit;
		}
		$check = $this->db->query("SELECT * FROM faculty_list where school_id ='$school_id' ".(!empty($id) ? " and id != {$id} " : ''))->num_rows;
		if($check > 0){
			return 3;
			exit;
		}
		if(isset($_FILES['img']) && $_FILES['img']['tmp_name'] != ''){
			$fname = $this->store_upload('img');
			if($fname !== false)
				$data .= ", avatar = '$fname' ";
			else
				error_log('rejected avatar upload in '.__FUNCTION__);
		}
		if(empty($id)){
			$save = $this->db->query("INSERT INTO faculty_list set $data");
		}else{
			$save = $this->db->query("UPDATE faculty_list set $data where id = $id");
		}

		if($save){
			return 1;
		}
	}
	function delete_faculty(){
		extract($_POST);
		$delete = $this->db->query("DELETE FROM faculty_list where id = ".$id);
		if($delete)
			return 1;
	}
	function save_student(){
		extract($_POST);
		$data = "";
		foreach($_POST as $k => $v){
			if(!in_array($k, array('id','cpass','password')) && !is_numeric($k)){
				if(empty($data)){
					$data .= " $k='$v' ";
				}else{
					$data .= ", $k='$v' ";
				}
			}
		}
		if(!empty($password)){
					$data .= ", password=md5('$password') ";

		}
		$check = $this->db->query("SELECT * FROM student_list where email ='$email' ".(!empty($id) ? " and id != {$id} " : ''))->num_rows;
		if($check > 0){
			return 2;
			exit;
		}
		if(isset($_FILES['img']) && $_FILES['img']['tmp_name'] != ''){
			$fname = $this->store_upload('img');
			if($fname !== false)
				$data .= ", avatar = '$fname' ";
			else
				error_log('rejected avatar upload in '.__FUNCTION__);
		}
		if(empty($id)){
			$save = $this->db->query("INSERT INTO student_list set $data");
		}else{
			$save = $this->db->query("UPDATE student_list set $data where id = $id");
		}

		if($save){
			return 1;
		}
	}
	function delete_student(){
		extract($_POST);
		$delete = $this->db->query("DELETE FROM student_list where id = ".$id);
		if($delete)
			return 1;
	}
	function save_task(){
		extract($_POST);
		$data = "";
		foreach($_POST as $k => $v){
			if(!in_array($k, array('id')) && !is_numeric($k)){
				if($k == 'description')
					$v = htmlentities(str_replace("'","&#x2019;",$v));
				if(empty($data)){
					$data .= " $k='$v' ";
				}else{
					$data .= ", $k='$v' ";
				}
			}
		}
		if(empty($id)){
			$save = $this->db->query("INSERT INTO task_list set $data");
		}else{
			$save = $this->db->query("UPDATE task_list set $data where id = $id");
		}
		if($save){
			return 1;
		}
	}
	function delete_task(){
		extract($_POST);
		$delete = $this->db->query("DELETE FROM task_list where id = $id");
		if($delete){
			return 1;
		}
	}
	function save_progress(){
		extract($_POST);
		$data = "";
		foreach($_POST as $k => $v){
			if(!in_array($k, array('id')) && !is_numeric($k)){
				if($k == 'progress')
					$v = htmlentities(str_replace("'","&#x2019;",$v));
				if(empty($data)){
					$data .= " $k='$v' ";
				}else{
					$data .= ", $k='$v' ";
				}
			}
		}
		if(!isset($is_complete))
			$data .= ", is_complete=0 ";
		if(empty($id)){
			$save = $this->db->query("INSERT INTO task_progress set $data");
		}else{
			$save = $this->db->query("UPDATE task_progress set $data where id = $id");
		}
		if($save){
		if(!isset($is_complete))
			$this->db->query("UPDATE task_list set status = 1 where id = $task_id ");
		else
			$this->db->query("UPDATE task_list set status = 2 where id = $task_id ");
			return 1;
		}
	}
	function delete_progress(){
		extract($_POST);
		$delete = $this->db->query("DELETE FROM task_progress where id = $id");
		if($delete){
			return 1;
		}
	}
	function save_restriction(){
		extract($_POST);
		$filtered = implode(",",array_filter($rid));
		if(!empty($filtered))
			$this->db->query("DELETE FROM restriction_list where id not in ($filtered) and academic_id = $academic_id");
		else
			$this->db->query("DELETE FROM restriction_list where  academic_id = $academic_id");
		foreach($rid as $k => $v){
			$data = " academic_id = $academic_id ";
			$data .= ", faculty_id = {$faculty_id[$k]} ";
			$data .= ", class_id = {$class_id[$k]} ";
			$data .= ", subject_id = {$subject_id[$k]} ";
			if(empty($v)){
				$save[] = $this->db->query("INSERT INTO restriction_list set $data ");
			}else{
				$save[] = $this->db->query("UPDATE restriction_list set $data where id = $v ");
			}
		}
			return 1;
	}
	function save_evaluation(){
		// Hardened: ids are bound as integers, the submission is written in one
		// transaction, and the unique index on
		// (academic_id, student_id, restriction_id) is what actually prevents a
		// duplicate — the UI filter alone never did.
		// Return codes: 1 = saved, 2 = already submitted, 0 = rejected or failed.
		$student_id = isset($_SESSION['login_id']) ? (int)$_SESSION['login_id'] : 0;
		if($student_id < 1)
			return 0;

		$v = array();
		foreach(array('academic_id','subject_id','class_id','restriction_id','faculty_id') as $k){
			if(!isset($_POST[$k]) || !ctype_digit((string)$_POST[$k]) || (int)$_POST[$k] < 1)
				return 0;
			$v[$k] = (int)$_POST[$k];
		}

		$qid  = isset($_POST['qid']) && is_array($_POST['qid']) ? $_POST['qid'] : array();
		$rate = isset($_POST['rate']) && is_array($_POST['rate']) ? $_POST['rate'] : array();
		if(empty($qid))
			return 0;

		// Reject outright if any answer is missing or out of range, rather than
		// storing a partial evaluation.
		$answers = array();
		foreach($qid as $q){
			if(!ctype_digit((string)$q) || (int)$q < 1)
				return 0;
			$q = (int)$q;
			if(!isset($rate[$q]) || !ctype_digit((string)$rate[$q]))
				return 0;
			$r = (int)$rate[$q];
			if($r < 1 || $r > 5)
				return 0;
			$answers[$q] = $r;
		}

		// The evaluation window must be open (1 = Start).
		$status = isset($_SESSION['academic']['status']) ? (int)$_SESSION['academic']['status'] : 0;
		if($status !== 1)
			return 0;

		// The assignment must genuinely exist for this term, class, subject and faculty.
		$chk = $this->db->prepare("SELECT id FROM restriction_list where id = ? and academic_id = ? and class_id = ? and subject_id = ? and faculty_id = ? limit 1");
		if(!$chk)
			return 0;
		$chk->bind_param('iiiii', $v['restriction_id'], $v['academic_id'], $v['class_id'], $v['subject_id'], $v['faculty_id']);
		$chk->execute();
		$owns  = $chk->get_result();
		$valid = $owns && $owns->num_rows > 0;
		$chk->close();
		if(!$valid)
			return 0;

		// Return values are checked explicitly so this behaves the same on PHP
		// versions before 8.1, where mysqli does not throw on error.
		$errno = 0;
		$this->db->begin_transaction();
		try{
			$stmt = $this->db->prepare("INSERT INTO evaluation_list (student_id, academic_id, subject_id, class_id, restriction_id, faculty_id) VALUES (?,?,?,?,?,?)");
			if(!$stmt)
				throw new Exception('prepare evaluation_list failed');
			$stmt->bind_param('iiiiii', $student_id, $v['academic_id'], $v['subject_id'], $v['class_id'], $v['restriction_id'], $v['faculty_id']);
			if(!$stmt->execute()){
				$errno = $stmt->errno;
				$stmt->close();
				throw new Exception('insert evaluation_list failed');
			}
			$eid = $this->db->insert_id;
			$stmt->close();

			$ans = $this->db->prepare("INSERT INTO evaluation_answers (evaluation_id, question_id, rate) VALUES (?,?,?)");
			if(!$ans)
				throw new Exception('prepare evaluation_answers failed');
			foreach($answers as $q => $r){
				$ans->bind_param('iii', $eid, $q, $r);
				if(!$ans->execute()){
					$errno = $ans->errno;
					$ans->close();
					throw new Exception('insert evaluation_answers failed');
				}
			}
			$ans->close();

			$this->db->commit();
			return 1;
		}catch(Exception $e){
			if($errno === 0)
				$errno = $this->db->errno ? $this->db->errno : (int)$e->getCode();
			$this->db->rollback();
			if($errno == 1062)
				return 2;
			error_log('save_evaluation failed: '.$e->getMessage().' (errno '.$errno.')');
			return 0;
		}
	}
	function get_class(){
		extract($_POST);
		$data = array();
		$get = $this->db->query("SELECT c.id,concat(c.curriculum,' ',c.level,' - ',c.section) as class,s.id as sid,concat(s.code,' - ',s.subject) as subj FROM restriction_list r inner join class_list c on c.id = r.class_id inner join subject_list s on s.id = r.subject_id where r.faculty_id = {$fid} and academic_id = {$_SESSION['academic']['id']} ");
		while($row= $get->fetch_assoc()){
			$data[]=$row;
		}
		return json_encode($data);

	}
	function get_report(){
		extract($_POST);
		$data = array();
		$get = $this->db->query("SELECT * FROM evaluation_answers where evaluation_id in (SELECT evaluation_id FROM evaluation_list where academic_id = {$_SESSION['academic']['id']} and faculty_id = $faculty_id and subject_id = $subject_id and class_id = $class_id ) ");
		$answered = $this->db->query("SELECT * FROM evaluation_list where academic_id = {$_SESSION['academic']['id']} and faculty_id = $faculty_id and subject_id = $subject_id and class_id = $class_id");
			$rate = array();
		while($row = $get->fetch_assoc()){
			if(!isset($rate[$row['question_id']][$row['rate']]))
			$rate[$row['question_id']][$row['rate']] = 0;
			$rate[$row['question_id']][$row['rate']] += 1;

		}
		// $data[]= $row;
		$ta = $answered->num_rows;
		$r = array();
		foreach($rate as $qk => $qv){
			foreach($qv as $rk => $rv){
			$r[$qk][$rk] =($rate[$qk][$rk] / $ta) *100;
		}
	}
	$data['tse'] = $ta;
	$data['data'] = $r;
		
		return json_encode($data);

	}
}