<?php
// The session and the access check run before any output is emitted.
//
// This file previously opened with the doctype and called session_start() on
// line 3, which only worked because output_buffering happened to be on: with
// it off the session never started, $_SESSION was empty on every request, and
// the redirect below failed silently with "headers already sent". The access
// check was relying on a php.ini setting rather than on being correct.
session_start();

if (!isset($_SESSION['login_id'])) {
	header('location:login.php');
	// header() does not stop execution. Without this exit, the rest of the page
	// still ran and issued every one of its queries for a visitor who was never
	// signed in; the browser followed the redirect, so nobody saw it happen.
	exit;
}

include 'db_connect.php';

if (!isset($_SESSION['system'])) {
	$system = $conn->query("SELECT * FROM system_settings")->fetch_array();
	if ($system) {
		foreach ($system as $k => $v) {
			if (!is_numeric($k)) {
				$_SESSION['system'][$k] = $v;
			}
		}
	}
}
?>
<!DOCTYPE html>
<html lang="en">
<?php include 'header.php' ?>
<body class="hold-transition sidebar-mini layout-fixed layout-navbar-fixed layout-footer-fixed">
<div class="wrapper">
  <?php include 'topbar.php' ?>
  <?php include $_SESSION['login_view_folder'].'sidebar.php' ?>

  <!-- Content Wrapper. Contains page content -->
  <div class="content-wrapper">
  	 <div class="toast" id="alert_toast" role="alert" aria-live="assertive" aria-atomic="true">
	    <div class="toast-body text-white">
	    </div>
	  </div>
    <div id="toastsContainerTopRight" class="toasts-top-right fixed"></div>
    <!-- Content Header (Page header) -->
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0"><?php echo $title ?></h1>
          </div><!-- /.col -->

        </div><!-- /.row -->
            <hr class="border-primary">
      </div><!-- /.container-fluid -->
    </div>
    <!-- /.content-header -->

    <!-- Main content -->
    <section class="content">
      <div class="container-fluid">
         <?php
            // The page name is matched against a per-role allowlist before it is
            // used to build an include path. Without this, $_GET['page'] reaches
            // include() directly and file_exists() is not a traversal guard.
            $allowed_pages = array(
              'admin/' => array(
                'home','academic_list','class_list','criteria_list','faculty_list',
                'student_list','subject_list','user_list','questionnaire','report',
                'new_faculty','new_student','new_user',
                'manage_academic','manage_class','manage_subject',
                'manage_questionnaire','manage_restriction',
                'view_faculty','view_student','view_user',
                'edit_faculty','edit_student','edit_user',
              ),
              'faculty/' => array('home','result','not_started','done','closed'),
              'student/' => array('home','evaluate','not_started','done','closed'),
            );

            $folder = isset($_SESSION['login_view_folder']) ? $_SESSION['login_view_folder'] : '';
            $page   = isset($_GET['page']) ? $_GET['page'] : 'home';

            if(!isset($allowed_pages[$folder]) || !in_array($page, $allowed_pages[$folder], true)){
                include '404.html';
            }else{
                include $folder.$page.'.php';
            }
          ?>
      </div><!--/. container-fluid -->
    </section>
    <!-- /.content -->
    <div class="modal fade" id="confirm_modal" role='dialog'>
    <div class="modal-dialog modal-md" role="document">
      <div class="modal-content">
        <div class="modal-header">
        <h5 class="modal-title">Confirmation</h5>
      </div>
      <div class="modal-body">
        <div id="delete_content"></div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-primary" id='confirm' onclick="">Continue</button>
        <button type="button" class="btn btn-secondary" data-dismiss="modal">Close</button>
      </div>
      </div>
    </div>
  </div>
  <div class="modal fade" id="uni_modal" role='dialog'>
    <div class="modal-dialog modal-md" role="document">
      <div class="modal-content">
        <div class="modal-header">
        <h5 class="modal-title"></h5>
      </div>
      <div class="modal-body">
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-primary" id='submit' onclick="$('#uni_modal form').submit()">Save</button>
        <button type="button" class="btn btn-secondary" data-dismiss="modal">Cancel</button>
      </div>
      </div>
    </div>
  </div>
  <div class="modal fade" id="uni_modal_right" role='dialog'>
    <div class="modal-dialog modal-full-height  modal-md" role="document">
      <div class="modal-content">
        <div class="modal-header">
        <h5 class="modal-title"></h5>
        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
          <span class="fa fa-arrow-right"></span>
        </button>
      </div>
      <div class="modal-body">
      </div>
      </div>
    </div>
  </div>
  <div class="modal fade" id="viewer_modal" role='dialog'>
    <div class="modal-dialog modal-md" role="document">
      <div class="modal-content">
              <button type="button" class="btn-close" data-dismiss="modal"><span class="fa fa-times"></span></button>
              <img src="" alt="">
      </div>
    </div>
  </div>
  </div>
  <!-- /.content-wrapper -->

  <!-- Control Sidebar -->
  <aside class="control-sidebar control-sidebar-dark">
    <!-- Control sidebar content goes here -->
  </aside>
  <!-- /.control-sidebar -->

  <!-- Main Footer -->
  <footer class="main-footer">
    <strong>Copyright &copy; 2021 <a href="https://www.erode-sengunthar.ac.in/">esec-ac.com</a>.</strong>
    All rights reserved.
    <div class="float-right d-none d-sm-inline-block">
      <b>Student Feedback</b>
    </div>
  </footer>
</div>
<!-- ./wrapper -->

<!-- REQUIRED SCRIPTS -->
<!-- jQuery -->
<!-- Bootstrap -->
<?php include 'footer.php' ?>
</body>
</html>
