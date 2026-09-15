import os

def update_file():
    filepath = "/home/at/Documents/ApexEstateHub/database/estatehub.sql"
    with open(filepath, 'r') as f:
        content = f.read()

    target_polls = """    results_announced_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP,
    ends_at TIMESTAMP,
    reminder_sent_at TIMESTAMP
);"""
    replacement_polls = """    results_announced_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP,
    ends_at TIMESTAMP,
    reminder_sent_at TIMESTAMP,
    qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT
);"""

    if target_polls in content:
        content = content.replace(target_polls, replacement_polls)
    else:
        print("Could not find target_polls in estatehub.sql")

    target_func = """CREATE OR REPLACE FUNCTION fn_trg_patrol_locations_qr()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.qr_payload IS NULL OR TRIM(NEW.qr_payload) = '' THEN
        NEW.qr_payload := NEW.society_id || '-PTL-' || NEW.id;
    END IF;
    RETURN NEW;
END;
$$;"""

    replacement_func = target_func + """

CREATE OR REPLACE FUNCTION fn_trg_polls_qr()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.qr_version = (1000 + FLOOR(RANDOM() * 9000))::INT;
    RETURN NEW;
END;
$$;"""

    if target_func in content:
        content = content.replace(target_func, replacement_func)
    else:
        print("Could not find target_func in estatehub.sql")

    target_trigger = """CREATE TRIGGER trg_patrol_locations_qr
    BEFORE INSERT ON patrol_locations
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_patrol_locations_qr();"""

    replacement_trigger = target_trigger + """

DROP TRIGGER IF EXISTS trg_polls_qr ON polls;

CREATE TRIGGER trg_polls_qr
    BEFORE UPDATE ON polls
    FOR EACH ROW
    EXECUTE FUNCTION fn_trg_polls_qr();"""

    if target_trigger in content:
        content = content.replace(target_trigger, replacement_trigger)
    else:
        print("Could not find target_trigger in estatehub.sql")

    with open(filepath, 'w') as f:
        f.write(content)
    print("Updated estatehub.sql")

if __name__ == "__main__":
    update_file()
