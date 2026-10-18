"""Actual read-only session comparison with privacy-minimized output."""
from __future__ import annotations

from .image import RawImage, sha256_file
from .inventory import inventory_session, privacy_class
from .session import BackupSession, GPT_PRIMARY, FULL_IMAGE, BOOT_AREAS
from ..firmware import gpt


def compare_sessions(first, second, *, progress=None, cancelled=lambda: False):
    from .verify import verify_session
    sessions = [BackupSession.open(first), BackupSession.open(second)]
    tables = []
    geometry = []
    for session in sessions:
        validation = verify_session(session.root, progress=progress, cancelled=cancelled)
        if not validation.passed:
            raise ValueError("a compared backup failed independent validation")
        view = RawImage(session.path(GPT_PRIMARY))
        table = gpt.read_table(view.read_at)
        if table.problems:
            raise ValueError("invalid GPT in compared backup")
        tables.append(table.by_name())
        geometry.append((table.header.backup_lba, table.header.first_usable_lba, table.header.last_usable_lba))
    rows = []
    layout_equal = geometry[0] == geometry[1]
    all_equal = True
    for name in sorted(set(tables[0]) | set(tables[1])):
        if cancelled():
            raise InterruptedError("backup comparison cancelled")
        parts = [table.get(name) for table in tables]
        same_geometry = (all(parts) and parts[0].first_lba == parts[1].first_lba and parts[0].last_lba == parts[1].last_lba
                         and parts[0].type_guid == parts[1].type_guid and parts[0].attributes == parts[1].attributes)
        layout_equal &= bool(same_geometry)
        files = [session.partition_file(name) if part else None for session, part in zip(sessions, parts)]
        same_content = False
        if all(files):
            if progress:
                progress("Comparing partition " + name)
            same_content = (files[0].stat().st_size == files[1].stat().st_size and
                sha256_file(files[0], cancelled=cancelled) == sha256_file(files[1], cancelled=cancelled))
        all_equal &= same_content
        rows.append({"name": name, "privacy": privacy_class(name), "both_present": all(files),
                     "same_geometry": bool(same_geometry), "same_content": same_content})
    builds = [inventory_session(session.root, cancelled=cancelled).build for session in sessions]
    common = set(builds[0]) & set(builds[1])
    model_keys = {"ro.product.model", "ro.product.board", "ro.hardware"}
    model_evidence = sorted(common & model_keys)
    model_equal = all(builds[0][key] == builds[1][key] for key in model_evidence) if model_evidence else None
    areas = {}
    for name in (*BOOT_AREAS, GPT_PRIMARY):
        files = [session.path(name) for session in sessions]
        areas[name] = (all(file.is_file() for file in files) and
            sha256_file(files[0], cancelled=cancelled) == sha256_file(files[1], cancelled=cancelled))
    full_hashes = [session.manifest.get(FULL_IMAGE) for session in sessions]
    same_user_area = full_hashes[0] == full_hashes[1] if all(full_hashes) else None
    return {"schema": "mcc-backup-comparison-v1", "read_only": True, "same_layout": layout_equal,
            "same_partition_content": all_equal, "partitions": rows,
            "both_backups_validated": True, "same_auxiliary_areas": areas, "same_full_user_area": same_user_area,
            "build_differences": {key: {"first": builds[0].get(key), "second": builds[1].get(key)}
                                  for key in sorted(set(builds[0]) | set(builds[1])) if builds[0].get(key) != builds[1].get(key)},
            "model_property_match": model_equal, "model_properties_compared": model_evidence,
            "hardware_compatibility": "UNVERIFIED", "device_identifiers_included": False,
            "restorability": "UNVERIFIED; matching files/layout do not prove hardware recovery"}
