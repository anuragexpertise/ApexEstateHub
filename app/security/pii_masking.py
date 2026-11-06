import re


def _mask_middle(s, keep_start=2, keep_end=2, mask_char="*"):
    s = str(s or "")
    if len(s) <= keep_start + keep_end:
        return mask_char * len(s)
    return s[:keep_start] + mask_char * (len(s) - keep_start - keep_end) + s[-keep_end:]


def mask_mobile(value):
    v = str(value or "").strip()
    digits = re.sub(r"\D", "", v)
    if len(digits) < 4:
        return "*" * len(v) if v else ""
    return _mask_middle(digits, 2, 2)


def mask_pan(value):
    v = str(value or "").strip().upper()
    if len(v) < 4:
        return "*" * len(v)
    return v[:2] + "*" * (len(v) - 4) + v[-2:]


def mask_bank(value):
    v = str(value or "").strip()
    digits = re.sub(r"\D", "", v)
    if len(digits) < 4:
        return "*" * len(v)
    return "*" * (len(digits) - 4) + digits[-4:]


def mask_upi(value):
    v = str(value or "").strip()
    if "@" not in v:
        return _mask_middle(v, 2, 0)
    local, domain = v.split("@", 1)
    return _mask_middle(local, 2, 0) + "@" + domain


def mask_address(value):
    v = str(value or "").strip()
    if not v:
        return ""
    parts = v.split()
    if len(parts) <= 2:
        return "*" * len(v)
    return parts[0] + " " + "*" * (len(v) - len(parts[0]) - len(parts[-1])) + " " + parts[-1]


def redact_for_audit(value, key=None):
    k = (key or "").lower()
    if "mobile" in k or "phone" in k or "contact" in k:
        return mask_mobile(value)
    if "pan" in k:
        return mask_pan(value)
    if "bank" in k or "account" in k:
        return mask_bank(value)
    if "upi" in k:
        return mask_upi(value)
    if "address" in k:
        return mask_address(value)
    return value
