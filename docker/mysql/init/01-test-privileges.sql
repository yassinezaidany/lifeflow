-- The Django test runner creates/drops a `test_<DB_NAME>` database.
-- Grant the application user rights on test databases only (not global).
GRANT ALL PRIVILEGES ON `test\_%`.* TO 'lifeflow'@'%';
FLUSH PRIVILEGES;
