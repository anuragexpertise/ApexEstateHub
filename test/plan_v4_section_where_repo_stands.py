"""
Tests mapping to: ApexEstateHub Gold-Standard Plan v4 - "Where the repo stands"
"""
import os
import re

import pytest


class TestV4RepoStandStatus:
    def test_phase0_has_service_layer_and_db_engines(self):
        assert os.path.exists("database/estatehub.sql")
        assert os.path.exists("database/db_manager.py")
        assert os.path.isdir("app/services")

    def test_phase1_ci_security_scans_present(self):
        assert os.path.exists(".github/workflows/tests.yml")
        content = open(".github/workflows/tests.yml").read()
        assert "postgres" in content.lower()
        assert "pip-audit" in content
        assert "bandit" in content
        assert "gitleaks" in content

    def test_phase1_key_vault_and_anchors_present(self):
        assert os.path.exists("app/services/signing_service.py") or os.path.exists("app/services/secret_vault.py")
        assert os.path.exists("scripts/anchor_ledgers.py")
        assert os.path.exists("database/migrations/001_society_signing_keys.sql")

    def test_phase1_gst_authority_and_44ab_flag_present(self):
        assert os.path.exists("database/gst_export.py")
        assert os.path.exists("app/services/statutory_rules.py")
        assert os.path.exists("app/dash_apps/callbacks/drilldown_callbacks.py")

    def test_phase2_core_modules_present(self):
        assert os.path.exists("app/services/document_signing.py") or os.path.exists("app/services/signing_service.py")
        assert os.path.exists("app/services/compliance_certificate.py") or os.path.exists("app/services/compliance_certificate_service.py")
        assert os.path.exists("app/services/ratification_service.py")

    def test_phase3_auditor_tieout_and_guards_present(self):
        assert os.path.exists("app/services/auditor_checks.py")
        estatehub = open("database/estatehub.sql").read()
        assert "tie" in estatehub.lower() or "expenses_vs_ledger" in estatehub
        assert os.path.exists("database/money.py")
        money = open("database/money.py").read()
        assert "Decimal" in money

    def test_phase4_migration_file_exists_only(self):
        migrations = []
        if os.path.isdir("database/migrations"):
            migrations = [f for f in os.listdir("database/migrations") if f.endswith(".sql")]
        assert "001_society_signing_keys.sql" in migrations
        assert len(migrations) == 1

    def test_float_count_reduced_from_v3(self):
        total = 0
        for root, _, files in os.walk("app"):
            for fn in files:
                if fn.endswith(".py"):
                    try:
                        content = open(os.path.join(root, fn)).read()
                        total += len(re.findall(r'\bfloat\s*\(', content))
                    except Exception:
                        pass
        for root, _, files in os.walk("database"):
            for fn in files:
                if fn.endswith(".py"):
                    try:
                        content = open(os.path.join(root, fn)).read()
                        total += len(re.findall(r'\bfloat\s*\(', content))
                    except Exception:
                        pass
        assert total <= 300
