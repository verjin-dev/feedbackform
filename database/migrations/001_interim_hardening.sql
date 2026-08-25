-- ============================================================================
-- P1 interim hardening — apply to the LIVE database.
--
-- Run the CHECK sections first and read their output. Steps 2 and 3 will fail
-- if duplicate rows already exist; that failure is informative, not harmful,
-- and the cleanup queries below resolve it.
--
-- Take a backup before running any of this:
--   mysqldump -u root -p evaluation_db > evaluation_db_backup_$(date +%F).sql
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 1. CHECK: accounts still using the template's seeded default passwords.
--    0192023a7bbd73250516f069df18b500 is md5('admin123') — the shipped default.
--    Any row returned here is a live credential an attacker can guess.
-- ----------------------------------------------------------------------------
SELECT 'users' AS source, id, email FROM users
WHERE password IN (
  '0192023a7bbd73250516f069df18b500',
  'd40242fb23c45206fadee4e2418f274f',
  '1254737c076cf867dc53d60a0364f38e',
  '4744ddea876b11dcb1d169fadf494418',
  '3cc93e9a6741d8b40460457139cf8ced'
)
UNION ALL
SELECT 'faculty_list', id, email FROM faculty_list
WHERE password IN (
  '0192023a7bbd73250516f069df18b500',
  'd40242fb23c45206fadee4e2418f274f',
  '1254737c076cf867dc53d60a0364f38e',
  '4744ddea876b11dcb1d169fadf494418',
  '3cc93e9a6741d8b40460457139cf8ced'
)
UNION ALL
SELECT 'student_list', id, email FROM student_list
WHERE password IN (
  '0192023a7bbd73250516f069df18b500',
  'd40242fb23c45206fadee4e2418f274f',
  '1254737c076cf867dc53d60a0364f38e',
  '4744ddea876b11dcb1d169fadf494418',
  '3cc93e9a6741d8b40460457139cf8ced'
);

-- ACTION for every row returned above: set a new password. Replace the literal
-- below with a long random passphrase — do not reuse it across accounts, and do
-- not commit it anywhere.
--
--   UPDATE users SET password = MD5('<new-passphrase-here>') WHERE id = <id>;
--
-- MD5 is still what the running app compares against; that is not fixed here
-- because it needs the P2/P3 schema work. Rotating away from a publicly known
-- default is still the single highest-value change available today.
--
-- If any seeded sample account (George Wilson, John Smith, Claire Blake,
-- Mike Williams) is not a real person at the college, delete it instead:
--
--   DELETE FROM faculty_list WHERE id = <id>;
--   DELETE FROM student_list WHERE id = <id>;


-- ----------------------------------------------------------------------------
-- 2. CHECK then FIX: duplicate evaluations.
--    Nothing has ever stopped a student submitting twice for one assignment.
--    Any duplicates present are already skewing the report percentages.
-- ----------------------------------------------------------------------------
SELECT academic_id, student_id, restriction_id, COUNT(*) AS submissions
FROM evaluation_list
GROUP BY academic_id, student_id, restriction_id
HAVING COUNT(*) > 1;

-- If the query above returns rows, keep the earliest submission of each group
-- and remove the rest. Review the list before running this.
--
--   DELETE a FROM evaluation_answers a
--   INNER JOIN evaluation_list e ON e.evaluation_id = a.evaluation_id
--   INNER JOIN (
--     SELECT academic_id, student_id, restriction_id, MIN(evaluation_id) AS keep_id
--     FROM evaluation_list
--     GROUP BY academic_id, student_id, restriction_id
--     HAVING COUNT(*) > 1
--   ) d ON d.academic_id = e.academic_id
--      AND d.student_id = e.student_id
--      AND d.restriction_id = e.restriction_id
--   WHERE e.evaluation_id <> d.keep_id;
--
--   DELETE e FROM evaluation_list e
--   INNER JOIN (
--     SELECT academic_id, student_id, restriction_id, MIN(evaluation_id) AS keep_id
--     FROM evaluation_list
--     GROUP BY academic_id, student_id, restriction_id
--     HAVING COUNT(*) > 1
--   ) d ON d.academic_id = e.academic_id
--      AND d.student_id = e.student_id
--      AND d.restriction_id = e.restriction_id
--   WHERE e.evaluation_id <> d.keep_id;

-- Then enforce it in the database, where the UI cannot be bypassed.
ALTER TABLE `evaluation_list`
  ADD UNIQUE KEY `uq_evaluation_once` (`academic_id`, `student_id`, `restriction_id`);


-- ----------------------------------------------------------------------------
-- 3. CHECK then FIX: duplicate answers.
--    evaluation_answers has no primary key at all.
-- ----------------------------------------------------------------------------
SELECT evaluation_id, question_id, COUNT(*) AS rows_present
FROM evaluation_answers
GROUP BY evaluation_id, question_id
HAVING COUNT(*) > 1;

-- If that returns nothing, apply both:
ALTER TABLE `evaluation_answers`
  ADD UNIQUE KEY `uq_answer_once` (`evaluation_id`, `question_id`);

ALTER TABLE `evaluation_answers`
  ADD CONSTRAINT `ck_rate_range` CHECK (`rate` BETWEEN 1 AND 5);
-- The CHECK constraint requires MySQL 8.0.16+ or MariaDB 10.2+. On older
-- servers it parses and is ignored, which is harmless — the application-side
-- validation added in save_evaluation() covers it either way.


-- ----------------------------------------------------------------------------
-- 4. Indexes the app has always needed. Every report query filters on these
--    columns and none of them were indexed.
-- ----------------------------------------------------------------------------
ALTER TABLE `evaluation_list`
  ADD KEY `ix_eval_report` (`academic_id`, `faculty_id`, `subject_id`, `class_id`);

ALTER TABLE `evaluation_answers`
  ADD KEY `ix_answer_eval` (`evaluation_id`);

ALTER TABLE `restriction_list`
  ADD KEY `ix_restriction_lookup` (`academic_id`, `class_id`);

ALTER TABLE `question_list`
  ADD KEY `ix_question_criteria` (`academic_id`, `criteria_id`);


-- ----------------------------------------------------------------------------
-- 5. A dedicated application database user, so the app stops connecting as root.
--    Replace the passphrase, then put the same values in config.local.php.
-- ----------------------------------------------------------------------------
-- CREATE USER 'evaluation_app'@'localhost' IDENTIFIED BY '<long-random-passphrase>';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON evaluation_db.* TO 'evaluation_app'@'localhost';
-- FLUSH PRIVILEGES;
--
-- Deliberately no DDL rights: schema changes are applied by an administrator
-- running files like this one, never by the application at runtime.
