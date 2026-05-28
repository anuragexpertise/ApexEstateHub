CREATE TABLE IF NOT EXISTS role_permissions (
    id SERIAL PRIMARY KEY,
    society_id INT REFERENCES societies (id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    card_id VARCHAR(100) NOT NULL,
    permission VARCHAR(20) NOT NULL CHECK (permission IN ('view', 'create', 'edit', 'delete')),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (COALESCE(society_id, 0), role, card_id, permission)
);