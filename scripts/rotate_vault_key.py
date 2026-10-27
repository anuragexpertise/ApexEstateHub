#!/usr/bin/env python3
"""
Run ON THE OPERATOR'S OWN MACHINE with SECRET_MASTER_KEY and the key-rotation database login (a member of
estatehub_keyrotator). The web host never holds either.

    python scripts/rotate_vault_key.py init      # first time: record master verifier + vault fingerprint
    python scripts/rotate_vault_key.py rotate    # new vault key, re-wrap all society keys, write recovery file
    python scripts/rotate_vault_key.py recover FILE   # print the vault key from a sealed recovery file

Environment: SECRET_MASTER_KEY, SECRET_VAULT_KEY (current), and the usual PG* / DATABASE_URL pointing at the
rotation login. After `rotate`: put the printed new key in the host .env, restart, then destroy the old key.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import psycopg2  # noqa: E402

from app.security import vault_rotation as vr  # noqa: E402
from database.db_config import connection_params  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["init", "rotate", "recover"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--sealed-out", default="vault_key.sealed")
    a = ap.parse_args()
    master = os.environ.get("SECRET_MASTER_KEY", "")
    try:
        if a.cmd == "recover":
            print(vr.unseal_vault_key(open(a.file, "rb").read(), master))
            return 0
        conn = psycopg2.connect(**connection_params())
        old = os.environ.get("SECRET_VAULT_KEY", "").split(",")[0]
        if a.cmd == "init":
            vr.init_meta(conn, master, old)
            open(a.sealed_out, "wb").write(vr.seal_vault_key(old, master))
            print(f"Initialised. Sealed recovery file written to {a.sealed_out}.")
        else:
            out = vr.rotate_vault_key(conn, old, master)
            open(a.sealed_out, "wb").write(out["sealed"])
            print(f"Re-wrapped {out['rewrapped']} keys. NEW SECRET_VAULT_KEY (put in host .env, never elsewhere):")
            print(out["new_vault_key"])
        return 0
    except (vr.MasterKeyError, vr.vault.SecretVaultError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
