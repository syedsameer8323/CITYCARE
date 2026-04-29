-- -- ================================================================
-- --  CityCare  –  DB ADDITIONS  (MySQL / InnoDB)
-- --  Run ONCE against your existing waste_management_system DB
-- -- ================================================================

-- USE `waste_management_system`;

-- -- ────────────────────────────────────────────────────────────────
-- -- 1. Patch existing `complaints` – add columns if missing
-- -- ────────────────────────────────────────────────────────────────
-- DROP PROCEDURE IF EXISTS add_col;
-- DELIMITER $$
-- CREATE PROCEDURE add_col(IN tbl VARCHAR(100), IN col VARCHAR(100), IN defn TEXT)
-- BEGIN
--     IF NOT EXISTS (
--         SELECT 1 FROM information_schema.COLUMNS
--         WHERE TABLE_SCHEMA='waste_management_system'
--           AND TABLE_NAME=tbl AND COLUMN_NAME=col
--     ) THEN
--         SET @s = CONCAT('ALTER TABLE `',tbl,'` ADD COLUMN `',col,'` ',defn);
--         PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
--     END IF;
-- END$$
-- DELIMITER ;

-- CALL add_col('complaints','',
--     'INT(10) DEFAULT NULL AFTER `assigned_staff`');
-- CALL add_col('complaints','resolved_at',
--     'DATETIME DEFAULT NULL');

-- DROP PROCEDURE IF EXISTS add_col;

-- -- ────────────────────────────────────────────────────────────────
-- -- 2. STAFF ACCOUNTS  (portal logins for field staff)
-- -- ────────────────────────────────────────────────────────────────
-- CREATE TABLE IF NOT EXISTS `staff_accounts` (
--   `id`                INT(10)       NOT NULL AUTO_INCREMENT,
--   `name`              VARCHAR(100)  NOT NULL,
--   `employee_id`       VARCHAR(50)   NOT NULL,
--   `email`             VARCHAR(100)  NOT NULL,
--   `phone`             VARCHAR(20)   NOT NULL,
--   `password_hash`     VARCHAR(255)  NOT NULL,
--   `department`        VARCHAR(100)  NOT NULL,
--   `designation`       VARCHAR(100)  NOT NULL,
--   `zone`              VARCHAR(150)  NOT NULL,
--   `notify_pref`       ENUM('email','sms','both') DEFAULT 'both',
--   `performance_score` INT(3)        DEFAULT 50,
--   `avg_rating`        DECIMAL(3,2)  DEFAULT 0.00,
--   `total_ratings`     INT(6)        DEFAULT 0,
--   `is_active`         TINYINT(1)    DEFAULT 1,
--   `is_approved`       TINYINT(1)    DEFAULT 0,
--   `joined`            DATETIME      DEFAULT CURRENT_TIMESTAMP,
--   PRIMARY KEY (`id`),
--   UNIQUE KEY `uq_email`       (`email`),
--   UNIQUE KEY `uq_employee_id` (`employee_id`)
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -- ────────────────────────────────────────────────────────────────
-- -- 3. STAFF NOTIFICATIONS
-- -- ────────────────────────────────────────────────────────────────
-- CREATE TABLE IF NOT EXISTS `staff_notifications` (
--   `id`           INT(10)      NOT NULL AUTO_INCREMENT,
--   `staff_id`     INT(10)      NOT NULL,
--   `type`         VARCHAR(30)  DEFAULT 'system',
--   `title`        VARCHAR(200) NOT NULL,
--   `message`      TEXT         NOT NULL,
--   `complaint_id` INT(10)      DEFAULT NULL,
--   `is_read`      TINYINT(1)   DEFAULT 0,
--   `created_at`   DATETIME     DEFAULT CURRENT_TIMESTAMP,
--   PRIMARY KEY (`id`),
--   KEY `idx_notif_staff` (`staff_id`,`is_read`),
--   CONSTRAINT `fk_notif_staff`
--     FOREIGN KEY (`staff_id`) REFERENCES `staff_accounts`(`id`) ON DELETE CASCADE
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -- ────────────────────────────────────────────────────────────────
-- -- 4. COMPLAINT PHOTOS  (before / after evidence)
-- -- ────────────────────────────────────────────────────────────────
-- CREATE TABLE IF NOT EXISTS `complaint_photos` (
--   `id`           INT(10)      NOT NULL AUTO_INCREMENT,
--   `complaint_id` INT(10)      NOT NULL,
--   `staff_id`     INT(10)      NOT NULL,
--   `filename`     VARCHAR(255) NOT NULL,
--   `photo_type`   ENUM('before','after') NOT NULL,
--   `uploaded_at`  DATETIME     DEFAULT CURRENT_TIMESTAMP,
--   PRIMARY KEY (`id`),
--   KEY `idx_photos_complaint` (`complaint_id`),
--   CONSTRAINT `fk_photos_complaint`
--     FOREIGN KEY (`complaint_id`) REFERENCES `complaints`(`complaint_id`) ON DELETE CASCADE,
--   CONSTRAINT `fk_photos_staff`
--     FOREIGN KEY (`staff_id`) REFERENCES `staff_accounts`(`id`) ON DELETE CASCADE
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -- ────────────────────────────────────────────────────────────────
-- -- 5. COMPLAINT ACTIVITY LOG
-- -- ────────────────────────────────────────────────────────────────
-- CREATE TABLE IF NOT EXISTS `complaint_activity` (
--   `id`           INT(10)      NOT NULL AUTO_INCREMENT,
--   `complaint_id` INT(10)      NOT NULL,
--   `staff_id`     INT(10)      NOT NULL,
--   `action`       VARCHAR(255) NOT NULL,
--   `notes`        TEXT,
--   `created_at`   DATETIME     DEFAULT CURRENT_TIMESTAMP,
--   PRIMARY KEY (`id`),
--   KEY `idx_activity_complaint` (`complaint_id`),
--   CONSTRAINT `fk_activity_complaint`
--     FOREIGN KEY (`complaint_id`) REFERENCES `complaints`(`complaint_id`) ON DELETE CASCADE,
--   CONSTRAINT `fk_activity_staff`
--     FOREIGN KEY (`staff_id`) REFERENCES `staff_accounts`(`id`) ON DELETE CASCADE
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -- ────────────────────────────────────────────────────────────────
-- -- 6. STAFF RATINGS  (citizen rates after complaint resolved)
-- -- ────────────────────────────────────────────────────────────────
-- CREATE TABLE IF NOT EXISTS `staff_ratings` (
--   `id`           INT(10)      NOT NULL AUTO_INCREMENT,
--   `complaint_id` INT(10)      NOT NULL,
--   `staff_id`     INT(10)      NOT NULL,
--   `userid`       VARCHAR(100) NOT NULL,
--   `rating`       TINYINT(1)   NOT NULL,
--   `comment`      TEXT,
--   `created_at`   DATETIME     DEFAULT CURRENT_TIMESTAMP,
--   PRIMARY KEY (`id`),
--   UNIQUE KEY `uq_rating_complaint` (`complaint_id`),
--   KEY `idx_ratings_staff` (`staff_id`),
--   CONSTRAINT `fk_rating_complaint`
--     FOREIGN KEY (`complaint_id`) REFERENCES `complaints`(`complaint_id`) ON DELETE CASCADE,
--   CONSTRAINT `fk_rating_staff`
--     FOREIGN KEY (`staff_id`) REFERENCES `staff_accounts`(`id`) ON DELETE CASCADE
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -- ────────────────────────────────────────────────────────────────
-- -- 7. Extra indexes on complaints
-- -- ────────────────────────────────────────────────────────────────
-- DROP PROCEDURE IF EXISTS add_idx;
-- DELIMITER $$
-- CREATE PROCEDURE add_idx(IN tbl VARCHAR(100), IN idx VARCHAR(100), IN defn TEXT)
-- BEGIN
--     IF NOT EXISTS (
--         SELECT 1 FROM information_schema.STATISTICS
--         WHERE TABLE_SCHEMA='waste_management_system'
--           AND TABLE_NAME=tbl AND INDEX_NAME=idx
--     ) THEN
--         SET @s = CONCAT('ALTER TABLE `',tbl,'` ADD ',defn);
--         PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
--     END IF;
-- END$$
-- DELIMITER ;

-- CALL add_idx('complaints','idx_complaints_staff',
--     'INDEX `idx_complaints_staff` (``)');
-- CALL add_idx('complaints','idx_complaints_loc',
--     'INDEX `idx_complaints_loc` (`location`(50))');

-- DROP PROCEDURE IF EXISTS add_idx;










-- ═══════════════════════════════════════════════════════════════
--  CityCare – Upgraded Database Schema
--  Run this on your existing `waste_management_system` database.
--  All operations are safe to re-run (IF NOT EXISTS / procedures).
-- ═══════════════════════════════════════════════════════════════

USE `waste_management_system`;

-- ───────────────────────────────────────────────────────────────
-- HELPER: safe ADD COLUMN procedure
-- ───────────────────────────────────────────────────────────────
DROP PROCEDURE IF EXISTS add_col;
DELIMITER $$
CREATE PROCEDURE add_col(IN tbl VARCHAR(100), IN col VARCHAR(100), IN defn TEXT)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = 'waste_management_system'
          AND TABLE_NAME   = tbl
          AND COLUMN_NAME  = col
    ) THEN
        SET @s = CONCAT('ALTER TABLE `', tbl, '` ADD COLUMN `', col, '` ', defn);
        PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
    END IF;
END$$
DELIMITER ;

-- ───────────────────────────────────────────────────────────────
-- HELPER: safe ADD INDEX procedure
-- ───────────────────────────────────────────────────────────────
DROP PROCEDURE IF EXISTS add_idx;
DELIMITER $$
CREATE PROCEDURE add_idx(IN tbl VARCHAR(100), IN idx VARCHAR(100), IN defn TEXT)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = 'waste_management_system'
          AND TABLE_NAME   = tbl
          AND INDEX_NAME   = idx
    ) THEN
        SET @s = CONCAT('ALTER TABLE `', tbl, '` ADD ', defn);
        PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
    END IF;
END$$
DELIMITER ;

-- ═══════════════════════════════════════════════════════════════
--  1. PATCH: complaints table – add missing columns
-- ═══════════════════════════════════════════════════════════════

-- Staff foreign key
CALL add_col('complaints', 'staff_id',
    'INT(10) DEFAULT NULL AFTER `assigned_staff`');

-- Resolution timestamp
CALL add_col('complaints', 'resolved_at',
    'DATETIME DEFAULT NULL');

-- Admin-set deadline
CALL add_col('complaints', 'deadline',
    'DATETIME DEFAULT NULL');

-- Reminder trigger timestamp
CALL add_col('complaints', 'reminder_at',
    'DATETIME DEFAULT NULL');

-- Internal admin notes (not shown to user/staff)
CALL add_col('complaints', 'admin_notes',
    'TEXT DEFAULT NULL');

-- Escalation flag
CALL add_col('complaints', 'escalated',
    'TINYINT(1) DEFAULT 0');

-- When the complaint was escalated
CALL add_col('complaints', 'escalated_at',
    'DATETIME DEFAULT NULL');

-- Reason recorded at escalation time
CALL add_col('complaints', 'escalation_reason',
    'VARCHAR(255) DEFAULT NULL');

-- Which staff member it was escalated FROM
CALL add_col('complaints', 'escalated_from_staff',
    'VARCHAR(100) DEFAULT NULL');

-- ═══════════════════════════════════════════════════════════════
--  2. STAFF ACCOUNTS
--     Stores portal login accounts for all field staff.
--     Each row represents one staff member with dept + zone +
--     designation so the smart-assign and escalation engines can
--     route complaints correctly.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS `staff_accounts` (
  `id`                INT(10)       NOT NULL AUTO_INCREMENT,
  `name`              VARCHAR(100)  NOT NULL,
  `employee_id`       VARCHAR(50)   NOT NULL,
  `email`             VARCHAR(100)  NOT NULL,
  `phone`             VARCHAR(20)   NOT NULL DEFAULT '',
  `password_hash`     VARCHAR(255)  NOT NULL,

  -- Hierarchy fields used for smart-assignment & escalation
  `department`        VARCHAR(100)  NOT NULL
      COMMENT 'One of: Sanitation | Waste Management | Public Works | Health & Hygiene | Environment',
  `designation`       VARCHAR(100)  NOT NULL
      COMMENT 'Hierarchy: Worker → Senior Worker → Supervisor → Senior Supervisor → Officer → Senior Officer → Chief Officer',
  `zone`              VARCHAR(255)  NOT NULL
      COMMENT 'Comma-separated area keywords, e.g. "Charminar, Old City"',

  `notify_pref`       ENUM('email','sms','both') DEFAULT 'both',
  `performance_score` INT(3)        DEFAULT 50
      COMMENT '0–100 calculated score: resolved count, severity bonus, overdue penalty, avg rating',
  `avg_rating`        DECIMAL(3,2)  DEFAULT 0.00,
  `total_ratings`     INT(6)        DEFAULT 0,
  `current_load`      INT(4)        DEFAULT 0
      COMMENT 'Live count of active (non-resolved) complaints assigned',
  `available`         TINYINT(1)    DEFAULT 1,
  `is_active`         TINYINT(1)    DEFAULT 1,
  `is_approved`       TINYINT(1)    DEFAULT 0
      COMMENT 'Admin must approve before staff can log in',
  `joined`            DATETIME      DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sa_email`       (`email`),
  UNIQUE KEY `uq_sa_employee_id` (`employee_id`),
  KEY        `idx_sa_dept_zone`  (`department`, `zone`(50)),
  KEY        `idx_sa_designation`(`designation`),
  KEY        `idx_sa_approved`   (`is_approved`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Staff portal accounts with department/zone/designation for hierarchy routing';

-- ═══════════════════════════════════════════════════════════════
--  3. NOTIFICATIONS
--     Central notification log used by all four event types:
--     assignment | reminder | escalation | admin_message
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS `notifications` (
  `id`           INT(10)      NOT NULL AUTO_INCREMENT,
  `complaint_id` INT(10)      DEFAULT NULL,
  `staff_id`     INT(10)      NOT NULL,
  `message`      TEXT         NOT NULL,
  `type`         ENUM('assignment','reminder','escalation','admin_message','system')
                              DEFAULT 'assignment'
      COMMENT 'assignment=new task, reminder=follow-up, escalation=passed up, admin_message=manual msg',
  `title`        VARCHAR(200) DEFAULT NULL,
  `is_read`      TINYINT(1)   DEFAULT 0,
  `timestamp`    DATETIME     DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  KEY `idx_notif_staff`     (`staff_id`, `is_read`),
  KEY `idx_notif_complaint` (`complaint_id`),
  CONSTRAINT `fk_notif_staff`
    FOREIGN KEY (`staff_id`)
    REFERENCES  `staff_accounts`(`id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='All in-app notifications for staff: assignment, reminder, escalation, admin messages';

-- ═══════════════════════════════════════════════════════════════
--  4. COMPLAINT PHOTOS
--     Before / after evidence photos uploaded by staff
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS `complaint_photos` (
  `id`           INT(10)      NOT NULL AUTO_INCREMENT,
  `complaint_id` INT(10)      NOT NULL,
  `staff_id`     INT(10)      NOT NULL,
  `filename`     VARCHAR(255) NOT NULL,
  `photo_type`   ENUM('before','after') NOT NULL,
  `uploaded_at`  DATETIME     DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  KEY `idx_photos_complaint` (`complaint_id`),
  CONSTRAINT `fk_photos_complaint`
    FOREIGN KEY (`complaint_id`) REFERENCES `complaints`(`complaint_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_photos_staff`
    FOREIGN KEY (`staff_id`) REFERENCES `staff_accounts`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ═══════════════════════════════════════════════════════════════
--  5. COMPLAINT ACTIVITY LOG
--     Immutable audit trail: every status change, assignment,
--     note, or escalation is recorded here.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS `complaint_activity` (
  `id`           INT(10)      NOT NULL AUTO_INCREMENT,
  `complaint_id` INT(10)      NOT NULL,
  `staff_id`     INT(10)      DEFAULT NULL
      COMMENT 'NULL when action is by system or admin (no staff login)',
  `action`       VARCHAR(255) NOT NULL,
  `notes`        TEXT         DEFAULT NULL,
  `created_at`   DATETIME     DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  KEY `idx_activity_complaint` (`complaint_id`),
  CONSTRAINT `fk_activity_complaint`
    FOREIGN KEY (`complaint_id`) REFERENCES `complaints`(`complaint_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Append-only audit log for every action taken on a complaint';

-- ═══════════════════════════════════════════════════════════════
--  6. STAFF RATINGS
--     Citizens rate staff after a complaint is resolved (1-5).
--     One rating per complaint enforced by UNIQUE key.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS `staff_ratings` (
  `id`           INT(10)      NOT NULL AUTO_INCREMENT,
  `complaint_id` INT(10)      NOT NULL,
  `staff_id`     INT(10)      NOT NULL,
  `userid`       VARCHAR(100) NOT NULL,
  `rating`       TINYINT(1)   NOT NULL COMMENT '1-5 stars',
  `comment`      TEXT         DEFAULT NULL,
  `created_at`   DATETIME     DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rating_complaint` (`complaint_id`)
      COMMENT 'One rating per complaint',
  KEY `idx_ratings_staff` (`staff_id`),
  CONSTRAINT `fk_rating_complaint`
    FOREIGN KEY (`complaint_id`) REFERENCES `complaints`(`complaint_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_rating_staff`
    FOREIGN KEY (`staff_id`) REFERENCES `staff_accounts`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ═══════════════════════════════════════════════════════════════
--  7. EXTRA INDEXES on complaints
-- ═══════════════════════════════════════════════════════════════
CALL add_idx('complaints', 'idx_complaints_staff',
    'INDEX `idx_complaints_staff` (`staff_id`)');
CALL add_idx('complaints', 'idx_complaints_loc',
    'INDEX `idx_complaints_loc` (`location`(50))');
CALL add_idx('complaints', 'idx_complaints_status',
    'INDEX `idx_complaints_status` (`status`)');
CALL add_idx('complaints', 'idx_complaints_severity',
    'INDEX `idx_complaints_severity` (`severity`)');
CALL add_idx('complaints', 'idx_complaints_escalated',
    'INDEX `idx_complaints_escalated` (`escalated`)');
CALL add_idx('complaints', 'idx_complaints_created',
    'INDEX `idx_complaints_created` (`created_at`)');
CALL add_idx('complaints', 'idx_complaints_deadline',
    'INDEX `idx_complaints_deadline` (`deadline`)');

-- ═══════════════════════════════════════════════════════════════
--  8. CLEANUP helpers
-- ═══════════════════════════════════════════════════════════════
DROP PROCEDURE IF EXISTS add_col;
DROP PROCEDURE IF EXISTS add_idx;

-- ═══════════════════════════════════════════════════════════════
--  9. REFERENCE DATA – Seed staff designations & sample staff
--     (comment out if you already have staff data)
-- ═══════════════════════════════════════════════════════════════

/*
-- Designation reference (informational – stored inline in staff_accounts.designation)
-- Hierarchy order (lowest → highest):
--   Worker → Senior Worker → Supervisor → Senior Supervisor
--   → Officer → Senior Officer → Chief Officer

-- Department → Category mapping reference:
--   Sanitation        : Domestic, Uncollected Waste
--   Waste Management  : Organic, Mixed, Garbage Overflow
--   Public Works      : Liquid, Streetlight Issue, Water Leakage, Road Damage, Drainage Issue
--   Health & Hygiene  : Public Toilet Issue, Dead Animal
--   Environment       : Hazardous, Illegal Dumping

-- Sample staff inserts (password = 'password123' hashed):
INSERT IGNORE INTO staff_accounts
    (name, employee_id, email, phone, password_hash,
     department, designation, zone, is_approved, is_active)
VALUES
  ('Ravi Kumar',   'EMP001', 'ravi@citycare.in',   '9000000001',
   '$2b$12$examplehashhere', 'Sanitation',     'Worker',         'Charminar, Old City',      1, 1),
  ('Suresh Babu',  'EMP002', 'suresh@citycare.in', '9000000002',
   '$2b$12$examplehashhere', 'Sanitation',     'Supervisor',     'Charminar, Old City',      1, 1),
  ('Priya Devi',   'EMP003', 'priya@citycare.in',  '9000000003',
   '$2b$12$examplehashhere', 'Waste Management','Worker',        'Nampally, Abids',          1, 1),
  ('Anil Reddy',   'EMP004', 'anil@citycare.in',   '9000000004',
   '$2b$12$examplehashhere', 'Public Works',   'Officer',        'Secunderabad, Trimulgherry',1, 1),
  ('Fatima Begum', 'EMP005', 'fatima@citycare.in', '9000000005',
   '$2b$12$examplehashhere', 'Environment',    'Senior Officer', 'All Zones',                1, 1);
*/

-- ═══════════════════════════════════════════════════════════════
--  10. VIEWS for admin dashboard convenience
-- ═══════════════════════════════════════════════════════════════

-- View: overdue complaints (pending > 5 days, not yet escalated)
CREATE OR REPLACE VIEW `v_overdue_complaints` AS
SELECT
    c.complaint_id,
    c.category,
    c.location,
    c.severity,
    c.status,
    c.assigned_staff,
    c.staff_id,
    c.created_at,
    DATEDIFF(NOW(), c.created_at) AS days_pending,
    sa.designation  AS staff_designation,
    sa.department   AS staff_department,
    sa.zone         AS staff_zone
FROM complaints c
LEFT JOIN staff_accounts sa ON c.staff_id = sa.id
WHERE c.status NOT IN ('resolved', 'Resolved', 'escalated')
  AND DATEDIFF(NOW(), c.created_at) > 5
  AND (c.escalated IS NULL OR c.escalated = 0)
ORDER BY days_pending DESC;

-- View: escalated complaints summary
CREATE OR REPLACE VIEW `v_escalated_complaints` AS
SELECT
    c.complaint_id,
    c.category,
    c.location,
    c.severity,
    c.status,
    c.assigned_staff,
    c.escalated_at,
    c.escalation_reason,
    c.escalated_from_staff,
    sa.designation AS current_designation,
    sa.department  AS department
FROM complaints c
LEFT JOIN staff_accounts sa ON c.staff_id = sa.id
WHERE c.escalated = 1 OR c.status = 'escalated'
ORDER BY c.escalated_at DESC;

-- View: staff workload summary
CREATE OR REPLACE VIEW `v_staff_workload` AS
SELECT
    sa.id,
    sa.name,
    sa.designation,
    sa.department,
    sa.zone,
    sa.performance_score,
    sa.avg_rating,
    COUNT(c.complaint_id)                                           AS total_assigned,
    SUM(CASE WHEN c.status = 'pending'   THEN 1 ELSE 0 END)        AS pending_count,
    SUM(CASE WHEN c.status IN ('In Progress','processing') THEN 1 ELSE 0 END) AS inprogress_count,
    SUM(CASE WHEN c.status IN ('resolved','Resolved') THEN 1 ELSE 0 END)  AS resolved_count,
    SUM(CASE WHEN c.status NOT IN ('resolved','Resolved') AND DATEDIFF(NOW(), c.created_at) > 5 THEN 1 ELSE 0 END) AS overdue_count
FROM staff_accounts sa
LEFT JOIN complaints c ON c.staff_id = sa.id
WHERE sa.is_approved = 1 AND sa.is_active = 1
GROUP BY sa.id, sa.name, sa.designation, sa.department,
         sa.zone, sa.performance_score, sa.avg_rating
ORDER BY pending_count DESC, sa.performance_score DESC;

-- ═══════════════════════════════════════════════════════════════
--  SCHEMA SUMMARY
-- ═══════════════════════════════════════════════════════════════
/*
  Tables:
  ┌──────────────────────┬──────────────────────────────────────────────┐
  │ Table                │ Purpose                                      │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ complaints           │ Core complaint records (patched with new cols)│
  │ staff_accounts       │ Staff logins + dept/zone/designation         │
  │ notifications        │ All 4 notification types in one table        │
  │ complaint_photos     │ Before/after evidence photos                 │
  │ complaint_activity   │ Immutable audit log                          │
  │ staff_ratings        │ Citizen star ratings after resolution        │
  └──────────────────────┴──────────────────────────────────────────────┘

  New columns on complaints:
  ┌──────────────────────┬──────────────────────────────────────────────┐
  │ Column               │ Purpose                                      │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ staff_id             │ FK → staff_accounts.id                       │
  │ resolved_at          │ Timestamp when set to resolved               │
  │ deadline             │ Admin-set deadline datetime                  │
  │ reminder_at          │ When to trigger reminder notification        │
  │ admin_notes          │ Internal notes (not shown to public)         │
  │ escalated            │ 0/1 flag                                     │
  │ escalated_at         │ Timestamp of escalation                      │
  │ escalation_reason    │ Reason string                                │
  │ escalated_from_staff │ Previous staff name before escalation        │
  └──────────────────────┴──────────────────────────────────────────────┘

  Views:
    v_overdue_complaints   – pending > 5 days, not escalated
    v_escalated_complaints – all escalated complaint details
    v_staff_workload       – per-staff task breakdown
*/