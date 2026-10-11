-- migration to update vw_apartment_users
CREATE OR REPLACE VIEW vw_apartment_users AS
SELECT 
    id,
    society_id,
    name,
    email,
    user_type,
    created_at,
    linked_id AS apartment_id
FROM users
WHERE role = 'apartment';
