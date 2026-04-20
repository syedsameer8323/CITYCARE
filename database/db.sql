/*!40101 SET NAMES utf8 */;
/*!40101 SET SQL_MODE=''*/;

create database if not exists `waste_management_system`;
USE `waste_management_system`;

/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;

-- ─────────────────────────────────────────
--  USERS
-- ─────────────────────────────────────────
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `user_name` varchar(100) DEFAULT NULL,
  `userid`    varchar(100) DEFAULT NULL,
  `email`     varchar(100) DEFAULT NULL,
  `passwrd`   varchar(100) DEFAULT NULL,
  `phno`      varchar(100) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

INSERT INTO `users` VALUES
('CLOUDTECHNOLOGIES','ct123','ct@gmail.com','12345','8121583911');

-- ─────────────────────────────────────────
--  STAFF  (new)
-- ─────────────────────────────────────────
DROP TABLE IF EXISTS `staff`;
CREATE TABLE `staff` (
  `staff_id`     int(10)      NOT NULL AUTO_INCREMENT,
  `staff_name`   varchar(100) NOT NULL,
  `designation`  varchar(100) DEFAULT 'Field Officer',
  `phone`        varchar(20)  DEFAULT NULL,
  `available`    tinyint(1)   DEFAULT 1,   -- 1 = free, 0 = busy
  `current_load` int(5)       DEFAULT 0,   -- # active complaints assigned
  PRIMARY KEY (`staff_id`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

INSERT INTO `staff` (`staff_name`,`designation`,`phone`,`available`,`current_load`) VALUES
('Ravi Kumar',   'Field Officer',  '9000000001', 1, 0),
('Sunita Rao',   'Field Officer',  '9000000002', 1, 0),
('Anil Sharma',  'Supervisor',     '9000000003', 1, 0),
('Meena Das',    'Field Officer',  '9000000004', 1, 0),
('Kiran Babu',   'Supervisor',     '9000000005', 1, 0);

-- ─────────────────────────────────────────
--  COMPLAINTS  (upgraded)
-- ─────────────────────────────────────────
DROP TABLE IF EXISTS `complaints`;
CREATE TABLE `complaints` (
  `complaint_id`   int(10)      NOT NULL AUTO_INCREMENT,
  `user_name`      varchar(100) DEFAULT NULL,
  `userid`         varchar(100) DEFAULT NULL,
  `phone_number`   varchar(100) DEFAULT NULL,
  `category`       varchar(100) DEFAULT NULL,
  `location`       varchar(100) DEFAULT NULL,
  `adddress`       varchar(255) DEFAULT NULL,
  `waste_image`    varchar(100) DEFAULT NULL,
  `status`         varchar(50)  DEFAULT 'pending',

  -- NEW PRIORITY FIELDS
  `severity`       varchar(20)  DEFAULT 'Medium',
    -- values: Critical | High | Medium | Low
  `severity_score` int(3)       DEFAULT 4,
    -- Critical=10, High=7, Medium=4, Low=1
  `priority_score` float        DEFAULT 0,
    -- computed: severity_score*0.5 + waiting_days*0.3 + area_load*0.2
  `assigned_staff` varchar(100) DEFAULT NULL,
  `staff_id`       int(10)      DEFAULT NULL,

  -- TIMESTAMPS
  `created_at`     datetime     DEFAULT CURRENT_TIMESTAMP,
  `resolved_at`    datetime     DEFAULT NULL,

  PRIMARY KEY (`complaint_id`),
  KEY `fk_staff` (`staff_id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=latin1;

INSERT INTO `complaints`
  (`complaint_id`,`user_name`,`userid`,`phone_number`,`category`,
   `location`,`adddress`,`waste_image`,`status`,
   `severity`,`severity_score`,`priority_score`,`assigned_staff`,`created_at`)
VALUES
  (5,'CLOUDTECHNOLOGIES','ct123','8121583911','Hazardous',
   'Kukatpally','opposite lulu mall','waste2.jpg','pending',
   'High',7,12.5,'Ravi Kumar',NOW() - INTERVAL 3 DAY);

-- ─────────────────────────────────────────
--  QUESTIONS  (unchanged)
-- ─────────────────────────────────────────
DROP TABLE IF EXISTS `questions`;
CREATE TABLE `questions` (
  `qid`      int(10)       NOT NULL AUTO_INCREMENT,
  `question` varchar(1000) DEFAULT NULL,
  `answer`   varchar(1000) DEFAULT NULL,
  UNIQUE KEY `qid` (`qid`)
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=latin1;

INSERT INTO `questions` VALUES
(3,'Hi','Hi, how can I help you!'),
(4,'Hello','Hello, how are you?'),
(5,'How are you?','I am good. What about you?'),
(6,'how i can keep environment clean?','Reduce waste: reuse, recycle, and compost. Avoid single-use plastics.'),
(7,'What is waste management and why is it important?','The process of collecting, transporting, and disposing of waste in an environmentally safe way.'),
(8,'How can I reduce waste at home','Avoid plastic bags and bottles; use reusable cloth bags and stainless steel bottles instead.'),
(9,'What are the different types of waste','Hazardous, Liquid, Solid, Organic, and Recyclable waste.'),
(10,'What do I do with expired medications?','Bring them to authorised drug take-back programmes near you.'),
(11,'What are the best ways to handle garden waste?','Compost it in a sunny spot. Garden waste becomes excellent fertiliser.');

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;