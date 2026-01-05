-- Fix permissions for word_occurrences table
-- Run this as a superuser in pgAdmin

-- Grant all privileges on the table to local_db_user
GRANT ALL PRIVILEGES ON TABLE word_occurrences TO local_db_user;

-- Grant usage and select on the sequence (for id auto-increment)
GRANT USAGE, SELECT ON SEQUENCE word_occurrences_id_seq TO local_db_user;

-- Also grant to postgres if needed
GRANT ALL PRIVILEGES ON TABLE word_occurrences TO postgres;
GRANT USAGE, SELECT ON SEQUENCE word_occurrences_id_seq TO postgres;

-- To verify permissions were granted:
-- \dp word_occurrences

-- To see all users in the database:
-- SELECT usename FROM pg_user;
