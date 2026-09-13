CREATE TABLE IF NOT EXISTS `branches` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `branch_code` TEXT NOT NULL,
  `street` TEXT NOT NULL,
  `city` TEXT NOT NULL,
  `state` TEXT NOT NULL,
  `zip_code` TEXT NOT NULL,
  `country` TEXT NOT NULL,
  `contact` TEXT NOT NULL,
  `date_created` DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO `branches` (`id`, `branch_code`, `street`, `city`, `state`, `zip_code`, `country`, `contact`, `date_created`) VALUES
(1, 'vzTL0PqMogyOWhF', 'Branch 1 St., Quiapo', 'Manila', 'Metro Manila', '1001', 'Philippines', '+2 123 455 623', '2020-11-26 11:21:41'),
(3, 'KyIab3mYBgAX71t', 'SAmple', 'Cebu', 'Cebu', '6000', 'Philippines', '+1234567489', '2020-11-26 16:45:05'),
(4, 'dIbUK5mEh96f0Zc', 'Sample', 'Sample', 'Sample', '123456', 'Philippines', '123456', '2020-11-27 13:31:49');

CREATE TABLE IF NOT EXISTS `parcels` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `reference_number` TEXT NOT NULL,
  `sender_name` TEXT NOT NULL,
  `sender_address` TEXT NOT NULL,
  `sender_contact` TEXT NOT NULL,
  `recipient_name` TEXT NOT NULL,
  `recipient_address` TEXT NOT NULL,
  `recipient_contact` TEXT NOT NULL,
  `type` INTEGER NOT NULL,
  `from_branch_id` TEXT NOT NULL,
  `to_branch_id` TEXT NOT NULL,
  `weight` TEXT NOT NULL,
  `height` TEXT NOT NULL,
  `width` TEXT NOT NULL,
  `length` TEXT NOT NULL,
  `price` REAL NOT NULL,
  `status` INTEGER DEFAULT 0,
  `date_created` DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO `parcels` (`id`, `reference_number`, `sender_name`, `sender_address`, `sender_contact`, `recipient_name`, `recipient_address`, `recipient_contact`, `type`, `from_branch_id`, `to_branch_id`, `weight`, `height`, `width`, `length`, `price`, `status`, `date_created`) VALUES
(1, '201406231415', 'John Smith', 'Sample', '+123456', 'Claire Blake', 'Sample', 'Sample', 1, '1', '0', '30kg', '12in', '12in', '15in', 2500, 7, '2020-11-26 16:15:46'),
(2, '117967400213', 'John Smith', 'Sample', '+123456', 'Claire Blake', 'Sample', 'Sample', 2, '1', '3', '30kg', '12in', '12in', '15in', 2500, 1, '2020-11-26 16:46:03'),
(3, '983186540795', 'John Smith', 'Sample', '+123456', 'Claire Blake', 'Sample', 'Sample', 2, '1', '3', '20Kg', '10in', '10in', '10in', 1500, 2, '2020-11-26 16:46:03'),
(4, '514912669061', 'Claire Blake', 'Sample', '+123456', 'John Smith', 'Sample Address', '+12345', 2, '4', '1', '23kg', '12in', '12in', '15in', 1900, 0, '2020-11-27 13:52:14'),
(5, '897856905844', 'Claire Blake', 'Sample', '+123456', 'John Smith', 'Sample Address', '+12345', 2, '4', '1', '30kg', '10in', '10in', '10in', 1450, 0, '2020-11-27 13:52:14'),
(6, '505604168988', 'John Smith', 'Sample', '+123456', 'Sample', 'Sample', '+12345', 1, '1', '0', '23kg', '12in', '12in', '15in', 2500, 1, '2020-11-27 14:06:42');

CREATE TABLE IF NOT EXISTS `parcel_tracks` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `parcel_id` INTEGER NOT NULL,
  `status` INTEGER NOT NULL,
  `date_created` DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO `parcel_tracks` (`id`, `parcel_id`, `status`, `date_created`) VALUES
(1, 2, 1, '2020-11-27 09:53:27'),
(2, 3, 1, '2020-11-27 09:55:17'),
(3, 1, 1, '2020-11-27 10:28:01'),
(4, 1, 2, '2020-11-27 10:28:10'),
(5, 1, 3, '2020-11-27 10:28:16'),
(6, 1, 4, '2020-11-27 11:05:03'),
(7, 1, 5, '2020-11-27 11:05:17'),
(8, 1, 7, '2020-11-27 11:05:26'),
(9, 3, 2, '2020-11-27 11:05:41'),
(10, 6, 1, '2020-11-27 14:06:57');

CREATE TABLE IF NOT EXISTS `system_settings` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `name` TEXT NOT NULL,
  `email` TEXT NOT NULL,
  `contact` TEXT NOT NULL,
  `address` TEXT NOT NULL,
  `cover_img` TEXT NOT NULL
);

INSERT INTO `system_settings` (`id`, `name`, `email`, `contact`, `address`, `cover_img`) VALUES
(1, 'Courier Management System', 'info@sample.comm', '+6948 8542 623', '2102  Caldwell Road, Rochester, New York, 14608', '');

CREATE TABLE IF NOT EXISTS `users` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `firstname` TEXT NOT NULL,
  `lastname` TEXT NOT NULL,
  `email` TEXT NOT NULL,
  `password` TEXT NOT NULL,
  `type` INTEGER DEFAULT 2,
  `branch_id` INTEGER NOT NULL,
  `date_created` DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO `users` (`id`, `firstname`, `lastname`, `email`, `password`, `type`, `branch_id`, `date_created`) VALUES
(1, 'Administrator', '', 'admin', '0192023a7bbd73250516f069df18b500', 1, 0, '2020-11-26 10:57:04'),
(2, 'John', 'Smith', 'jsmith@sample.com', '1254737c076cf867dc53d60a0364f38e', 2, 1, '2020-11-26 11:52:04'),
(3, 'George', 'Wilson', 'gwilson@sample.com', 'd40242fb23c45206fadee4e2418f274f', 2, 4, '2020-11-27 13:32:12');
