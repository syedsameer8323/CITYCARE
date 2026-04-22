-- ================================================================
--  CityCare  –  DB ADDITIONS  (MySQL / InnoDB)
--  Run ONCE against your existing waste_management_system DB
-- ================================================================

USE `waste_management_system`;

-- ────────────────────────────────────────────────────────────────
-- 1. Patch existing `complaints` – add columns if missing
-- ────────────────────────────────────────────────────────────────
DROP PROCEDURE IF EXISTS add_col;
DELIMITER $$
CREATE PROCEDURE add_col(IN tbl VARCHAR(100), IN col VARCHAR(100), IN defn TEXT)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA='waste_management_system'
          AND TABLE_NAME=tbl AND COLUMN_NAME=col
    ) THEN
        SET @s = CONCAT('ALTER TABLE `',tbl,'` ADD COLUMN `',col,'` ',defn);
        PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
    END IF;
END$$
DELIMITER ;

CALL add_col('complaints','',
    'INT(10) DEFAULT NULL AFTER `assigned_staff`');
CALL add_col('complaints','resolved_at',
    'DATETIME DEFAULT NULL');

DROP PROCEDURE IF EXISTS add_col;

-- ────────────────────────────────────────────────────────────────
-- 2. STAFF ACCOUNTS  (portal logins for field staff)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `staff_accounts` (
  `id`                INT(10)       NOT NULL AUTO_INCREMENT,
  `name`              VARCHAR(100)  NOT NULL,
  `employee_id`       VARCHAR(50)   NOT NULL,
  `email`             VARCHAR(100)  NOT NULL,
  `phone`             VARCHAR(20)   NOT NULL,
  `password_hash`     VARCHAR(255)  NOT NULL,
  `department`        VARCHAR(100)  NOT NULL,
  `designation`       VARCHAR(100)  NOT NULL,
  `zone`              VARCHAR(150)  NOT NULL,
  `notify_pref`       ENUM('email','sms','both') DEFAULT 'both',
  `performance_score` INT(3)        DEFAULT 50,
  `avg_rating`        DECIMAL(3,2)  DEFAULT 0.00,
  `total_ratings`     INT(6)        DEFAULT 0,
  `is_active`         TINYINT(1)    DEFAULT 1,
  `is_approved`       TINYINT(1)    DEFAULT 0,
  `joined`            DATETIME      DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_email`       (`email`),
  UNIQUE KEY `uq_employee_id` (`employee_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ────────────────────────────────────────────────────────────────
-- 3. STAFF NOTIFICATIONS
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `staff_notifications` (
  `id`           INT(10)      NOT NULL AUTO_INCREMENT,
  `staff_id`     INT(10)      NOT NULL,
  `type`         VARCHAR(30)  DEFAULT 'system',
  `title`        VARCHAR(200) NOT NULL,
  `message`      TEXT         NOT NULL,
  `complaint_id` INT(10)      DEFAULT NULL,
  `is_read`      TINYINT(1)   DEFAULT 0,
  `created_at`   DATETIME     DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_notif_staff` (`staff_id`,`is_read`),
  CONSTRAINT `fk_notif_staff`
    FOREIGN KEY (`staff_id`) REFERENCES `staff_accounts`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ────────────────────────────────────────────────────────────────
-- 4. COMPLAINT PHOTOS  (before / after evidence)
-- ────────────────────────────────────────────────────────────────
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

-- ────────────────────────────────────────────────────────────────
-- 5. COMPLAINT ACTIVITY LOG
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `complaint_activity` (
  `id`           INT(10)      NOT NULL AUTO_INCREMENT,
  `complaint_id` INT(10)      NOT NULL,
  `staff_id`     INT(10)      NOT NULL,
  `action`       VARCHAR(255) NOT NULL,
  `notes`        TEXT,
  `created_at`   DATETIME     DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_activity_complaint` (`complaint_id`),
  CONSTRAINT `fk_activity_complaint`
    FOREIGN KEY (`complaint_id`) REFERENCES `complaints`(`complaint_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_activity_staff`
    FOREIGN KEY (`staff_id`) REFERENCES `staff_accounts`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ────────────────────────────────────────────────────────────────
-- 6. STAFF RATINGS  (citizen rates after complaint resolved)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `staff_ratings` (
  `id`           INT(10)      NOT NULL AUTO_INCREMENT,
  `complaint_id` INT(10)      NOT NULL,
  `staff_id`     INT(10)      NOT NULL,
  `userid`       VARCHAR(100) NOT NULL,
  `rating`       TINYINT(1)   NOT NULL,
  `comment`      TEXT,
  `created_at`   DATETIME     DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rating_complaint` (`complaint_id`),
  KEY `idx_ratings_staff` (`staff_id`),
  CONSTRAINT `fk_rating_complaint`
    FOREIGN KEY (`complaint_id`) REFERENCES `complaints`(`complaint_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_rating_staff`
    FOREIGN KEY (`staff_id`) REFERENCES `staff_accounts`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ────────────────────────────────────────────────────────────────
-- 7. Extra indexes on complaints
-- ────────────────────────────────────────────────────────────────
DROP PROCEDURE IF EXISTS add_idx;
DELIMITER $$
CREATE PROCEDURE add_idx(IN tbl VARCHAR(100), IN idx VARCHAR(100), IN defn TEXT)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA='waste_management_system'
          AND TABLE_NAME=tbl AND INDEX_NAME=idx
    ) THEN
        SET @s = CONCAT('ALTER TABLE `',tbl,'` ADD ',defn);
        PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
    END IF;
END$$
DELIMITER ;

CALL add_idx('complaints','idx_complaints_staff',
    'INDEX `idx_complaints_staff` (``)');
CALL add_idx('complaints','idx_complaints_loc',
    'INDEX `idx_complaints_loc` (`location`(50))');

DROP PROCEDURE IF EXISTS add_idx;