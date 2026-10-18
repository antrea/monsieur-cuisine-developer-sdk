"""Independent offline verification of an eMMC backup session.

Never talks to the appliance. Each check yields PASS, FAIL, WARN or SKIP with a
short detail, so integrity (bytes unchanged), completeness (what the backup
covers) and restorability (what would still need hardware) stay separate.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..firmware import bootimg, ext4, gpt, mtk
from .image import CompositeImage, RawImage, Segment, is_all_zero, sha256_file, sha256_image
from .session import BOOT_AREAS, DIRECT, EXTRACTED, FULL_IMAGE, GPT_PRIMARY, BackupSession

SECTOR = 512


@dataclass
class Check:
    id: str
    status: str
    detail: str
    data: dict = field(default_factory=dict)


@dataclass
class VerifyReport:
    session: str
    checks: list[Check] = field(default_factory=list)
    partitions: list[dict] = field(default_factory=list)

    def add(self, id, status, detail, **data):
        self.checks.append(Check(id, status, detail, data))

    @property
    def passed(self) -> bool:
        return not any(c.status == "FAIL" for c in self.checks)

    def to_dict(self) -> dict:
        return {"session": self.session, "passed": self.passed,
                "summary": {s: sum(c.status == s for c in self.checks) for s in ("PASS", "FAIL", "WARN", "SKIP")},
                "checks": [asdict(c) for c in self.checks], "partitions": self.partitions}


def _hash_manifest(session: BackupSession, report: VerifyReport, manifest: dict[str, str], base: Path, label: str,
                   progress):
    if not manifest:
        report.add(f"{label}.present", "SKIP" if label == "extracted" else "FAIL", f"{label} manifest missing")
        return {}
    changed, missing, hashes = [], [], {}
    for relative, expected in sorted(manifest.items()):
        target = (base / relative).resolve()
        if not target.is_relative_to(session.root):
            changed.append(relative)
            continue
        if not target.is_file():
            missing.append(relative)
            continue
        if progress:
            progress(f"SHA-256 {label}/{relative}")
        actual = sha256_file(target)
        hashes[relative] = actual
        if actual != expected:
            changed.append(relative)
    absent_ok = [m for m in missing if m == FULL_IMAGE]
    hard_missing = [m for m in missing if m != FULL_IMAGE]
    status = "FAIL" if changed or hard_missing else "PASS"
    report.add(f"{label}.hashes", status,
               f"{len(hashes) - len(changed)} of {len(manifest)} files re-hashed unchanged"
               + (f"; changed: {', '.join(changed)}" if changed else "")
               + (f"; missing: {', '.join(hard_missing)}" if hard_missing else "")
               + ("; full user-area image not present (checked by reconstruction)" if absent_ok else ""),
               changed=changed, missing=missing)
    return hashes


def compose_user_area(session: BackupSession, table: gpt.GptTable, primary_sector: bytes) -> CompositeImage:
    """User-area image from gpt_primary.bin + extracted partitions + a standard backup GPT; gaps are zero."""
    h = table.header
    size = (h.backup_lba + 1) * SECTOR
    primary = session.path(GPT_PRIMARY)
    segments = [Segment(0, primary.stat().st_size, primary, 0, label="gpt_primary")]
    for p in table.partitions:
        source = session.partition_file(p.name)
        if source is None:
            raise ValueError(f"partition {p.name} has no file in the session")
        if source.stat().st_size != p.size(SECTOR):
            raise ValueError(f"{source.name}: {source.stat().st_size} bytes, GPT says {p.size(SECTOR)}")
        segments.append(Segment(p.offset(SECTOR), p.size(SECTOR), source, 0, label=p.name))
    backup_header, entries_lba = gpt.build_backup(primary_sector, table.entries_raw, h)
    segments.append(Segment(entries_lba * SECTOR, len(table.entries_raw), data=table.entries_raw,
                            label="backup GPT entries (synthesized)"))
    segments.append(Segment(h.backup_lba * SECTOR, SECTOR, data=backup_header, label="backup GPT header (synthesized)"))
    return CompositeImage(size, segments)


def _identify(name: str, view: RawImage) -> dict:
    """Content signature of one partition (read-only, bounded)."""
    head = view.read_at(0, 4096)
    info: dict = {}
    if head[:8] == bootimg.BOOT_MAGIC:
        raw = view.read_at(0, view.size)
        image = bootimg.parse_boot_image(raw)
        kernel_name, _kernel = bootimg.unwrap_mtk(bootimg.section(raw, image, "kernel"))
        ramdisk_name, ramdisk = bootimg.unwrap_mtk(bootimg.section(raw, image, "ramdisk"))
        info = {"type": "android-boot", "header_version": image.header_version, "page_size": image.page_size,
                "kernel_size": image.kernel_size, "ramdisk_size": image.ramdisk_size, "cmdline": image.cmdline,
                "mtk_kernel_header": kernel_name, "mtk_ramdisk_header": ramdisk_name}
        try:
            entries = bootimg.list_cpio(bootimg.decompress_ramdisk(ramdisk))
            info["ramdisk_entries"] = len(entries)
        except ValueError as error:
            info["ramdisk_error"] = str(error)
    elif head[:4] == mtk.MTK_MAGIC:
        info = {"type": "mtk-image", "images": mtk.mtk_images(view.read_at(0, min(view.size, 64 * 1024 * 1024)))}
    else:
        sb_raw = view.read_at(ext4.SUPERBLOCK_OFFSET, 1024)
        try:
            sb = ext4.parse_superblock(sb_raw)
            info = {"type": "ext4", "volume_name": sb.volume_name, "block_size": sb.block_size,
                    "blocks": sb.blocks_count, "free_blocks": sb.free_blocks, "inodes": sb.inodes_count,
                    "free_inodes": sb.free_inodes, "clean": sb.clean, "mount_count": sb.mount_count,
                    "used_bytes": (sb.blocks_count - sb.free_blocks) * sb.block_size}
        except ValueError:
            if is_all_zero(view, 0, view.size):
                info = {"type": "empty (all zero)"}
            elif head.count(0xFF) == len(head) and view.read_at(view.size - 4096, 4096).count(0xFF) == 4096:
                info = {"type": "erased (0xFF at both ends)"}
            else:
                info = {"type": "data"}
    return info


def verify_session(folder, *, scatter: str | None = None, reconstruct: bool = True, identify: bool = True,
                   progress=None) -> VerifyReport:
    session = BackupSession.open(folder)
    report = VerifyReport(str(session.root))
    for problem in session.problems:
        report.add("session.metadata", "WARN", problem)

    # 1. Integrity: every file against its recorded SHA-256.
    hashes = _hash_manifest(session, report, session.manifest, session.root, "manifest", progress)
    extracted_hashes = _hash_manifest(session, report, session.extracted_manifest, session.root / EXTRACTED,
                                      "extracted", progress)

    # 2. The appliance only received read commands (as logged by the tool).
    if session.commands:
        bad = session.non_read_commands()
        report.add("session.read_only", "FAIL" if bad else "PASS",
                   f"{len(session.commands)} logged commands, all flash reads" if not bad
                   else f"non-read commands logged: {bad}", commands=session.commands)
    else:
        report.add("session.read_only", "SKIP", "no command log in the session")

    # 3. Partition table.
    primary_path = session.root / GPT_PRIMARY
    if not primary_path.is_file():
        report.add("gpt.primary", "FAIL", f"{GPT_PRIMARY} missing")
        return report
    primary_view = RawImage(primary_path)
    report.add("gpt.protective_mbr", "PASS" if gpt.protective_mbr_ok(primary_view.read_at(0, SECTOR)) else "FAIL",
               "LBA 0 is a protective MBR (type 0xEE, 55 AA)")
    try:
        table = gpt.read_table(primary_view.read_at, sector=SECTOR, header_lba=1)
    except ValueError as error:
        report.add("gpt.primary", "FAIL", f"primary GPT unreadable: {error}")
        return report
    h = table.header
    report.add("gpt.primary", "FAIL" if table.problems else "PASS",
               f"primary GPT: {len(table.partitions)} partitions, header and entry CRC32 "
               + ("valid" if h.header_crc_ok and table.entries_crc_ok else "INVALID")
               + (f"; problems: {table.problems}" if table.problems else ""),
               disk_guid=h.disk_guid, backup_lba=h.backup_lba, first_usable=h.first_usable_lba,
               last_usable=h.last_usable_lba)
    disk_size = (h.backup_lba + 1) * SECTOR
    for p in sorted(table.partitions, key=lambda p: p.first_lba):
        report.partitions.append({"name": p.name, "offset": p.offset(SECTOR), "size": p.size(SECTOR),
                                  "first_lba": p.first_lba, "last_lba": p.last_lba, "type_guid": p.type_guid,
                                  "attributes": p.attributes})
    for name in ("gpt.bin", "gpt_backup.bin"):
        copy = session.root / DIRECT / name
        if copy.is_file():
            data = copy.read_bytes()
            same = data == primary_view.read_at(0, len(data))
            report.add(f"gpt.copy.{name}", "PASS" if same else "WARN",
                       f"{DIRECT}/{name} ({len(data)} bytes) " + ("equals" if same else "differs from")
                       + f" the first {len(data)} bytes of {GPT_PRIMARY}")

    # 4. Direct reads vs extracted partitions; sizes vs GPT.
    by_name = table.by_name()
    agree, disagree, size_bad = [], [], []
    for p in table.partitions:
        direct = session.root / DIRECT / f"{p.name}.bin"
        extracted = session.root / EXTRACTED / f"{p.name}.bin"
        for f in (direct, extracted):
            if f.is_file() and f.stat().st_size != p.size(SECTOR):
                size_bad.append(f"{f.parent.name}/{f.name}")
        if direct.is_file() and extracted.is_file():
            d = hashes.get(f"{DIRECT}/{p.name}.bin") or sha256_file(direct)
            e = extracted_hashes.get(f"{p.name}.bin") or sha256_file(extracted)
            (agree if d == e else disagree).append(p.name)
    report.add("partitions.sizes", "FAIL" if size_bad else "PASS",
               "every partition file has the size the GPT declares" if not size_bad else f"wrong size: {size_bad}")
    report.add("partitions.cross_read", "FAIL" if disagree else "PASS" if agree else "SKIP",
               f"{len(agree)} partitions read twice (direct and from the full image) are identical"
               + (f"; differ: {disagree}" if disagree else ""), agree=agree, disagree=disagree)
    missing = [p.name for p in table.partitions if session.partition_file(p.name) is None]
    report.add("completeness.partitions", "FAIL" if missing else "PASS",
               f"all {len(table.partitions)} GPT partitions present as files" if not missing
               else f"no file for: {missing}")

    # 5. Full user area: the image itself, or a lossless reconstruction from the pieces.
    recorded = session.manifest.get(FULL_IMAGE)
    if session.has_full_image:
        full = RawImage(session.root / FULL_IMAGE)
        report.add("full_image.size", "PASS" if full.size == disk_size else "FAIL",
                   f"{full.size:,} bytes; GPT backup LBA implies {disk_size:,}")
        try:
            backup_table = gpt.read_table(full.read_at, sector=SECTOR, header_lba=h.backup_lba,
                                          disk_sectors=full.size // SECTOR)
            same = backup_table.entries_raw == table.entries_raw and backup_table.header.disk_guid == h.disk_guid
            report.add("gpt.backup", "PASS" if same and not backup_table.problems else "FAIL",
                       "backup GPT valid and identical to the primary" if same else "backup GPT differs")
        except ValueError as error:
            report.add("gpt.backup", "FAIL", f"backup GPT unreadable: {error}")
    elif reconstruct and not missing and not size_bad:
        image = compose_user_area(session, table, primary_view.read_at(SECTOR, SECTOR))
        covered = image.coverage()
        if recorded:
            digest = sha256_image(image, progress=(lambda done, total: progress(f"reconstruct {done}/{total}"))
                                  if progress else None)
            same = digest == recorded
            report.add("full_image.reconstruction", "PASS" if same else "FAIL",
                       ("the pieces reassemble into a user area whose SHA-256 equals the recorded "
                        f"{FULL_IMAGE} hash: the archive is a lossless copy of the full image") if same else
                       ("reassembled image hash differs from the recorded full-image hash: unallocated gaps or "
                        "the backup GPT region hold data the pieces do not carry"),
                       sha256=digest, recorded=recorded, coverage=covered)
        else:
            report.add("full_image.reconstruction", "SKIP", "no recorded full-image hash to compare with")
    else:
        report.add("full_image.reconstruction", "SKIP", "full image absent and reconstruction not possible")

    # 6. eMMC areas outside the user area.
    for name in BOOT_AREAS:
        path = session.root / name
        report.add(f"boot_area.{name}", "PASS" if path.is_file() else "FAIL",
                   f"{name} present ({path.stat().st_size:,} bytes)" if path.is_file() else f"{name} missing")
    boot1 = session.root / BOOT_AREAS[0]
    if boot1.is_file():
        info = mtk.parse_preloader(boot1.read_bytes()[:0x40000])
        good = info.emmc_boot and info.brlyt_offset is not None
        report.add("boot_area.preloader", "PASS" if good else "WARN",
                   "boot1 starts with EMMC_BOOT and holds a BRLYT layout record" if good
                   else "no MediaTek preloader layout found in boot1", **asdict(info))
    report.add("completeness.rpmb", "WARN", "the eMMC RPMB area is not part of the backup (not readable this way)")

    # 7. Content identification.
    if identify:
        for row in report.partitions:
            source = session.partition_file(row["name"])
            if source is not None:
                try:
                    row["content"] = _identify(row["name"], RawImage(source))
                except ValueError as error:
                    row["content"] = {"type": "unparsable", "error": str(error)}
                row["sha256"] = extracted_hashes.get(f"{row['name']}.bin")
        for name, expected in (("boot", "android-boot"), ("recovery", "android-boot"), ("system", "ext4"),
                               ("cache", "ext4"), ("userdata", "ext4")):
            row = next((r for r in report.partitions if r["name"] == name), None)
            if row is not None:
                actual = row.get("content", {}).get("type")
                report.add(f"content.{name}", "PASS" if actual == expected else "FAIL",
                           f"{name}: {actual} (expected {expected})")

    # 8. Optional reference scatter layout.
    if scatter:
        reference = read_scatter(Path(scatter))
        differ = [n for n, p in by_name.items()
                  if n in reference and reference[n] != (p.offset(SECTOR), p.size(SECTOR))]
        report.add("layout.scatter", "PASS" if not differ else "WARN",
                   f"{len(by_name) - len(differ)} of {len(by_name)} partitions match the reference scatter"
                   + (f"; differ: {differ}" if differ else ""), differ=differ)
    return report


def read_scatter(path: Path) -> dict[str, tuple[int, int]]:
    """{partition: (linear start, size)} from a MediaTek SP Flash Tool scatter file."""
    result, name, start = {}, None, None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        key, _, value = line.strip().partition(":")
        value = value.strip()
        if key == "partition_name":
            name, start = value, None
        elif key == "linear_start_addr" and name:
            start = int(value, 16)
        elif key == "partition_size" and name and start is not None:
            result[name] = (start, int(value, 16))
            name = None
    return result


def write_reports(report: VerifyReport, out_dir) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = report.to_dict()
    json_path = out / "backup_verification.json"
    json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    lines = [f"# Backup verification", "", f"Session: `{report.session}`", "",
             f"Result: **{'PASSED' if report.passed else 'FAILED'}** — " +
             ", ".join(f"{k} {v}" for k, v in data["summary"].items()), "", "| Check | Status | Detail |",
             "|---|---|---|"]
    lines += [f"| `{c.id}` | {c.status} | {c.detail.replace('|', '/')} |" for c in report.checks]
    lines += ["", "| Partition | Offset | Size | Content |", "|---|---|---|---|"]
    lines += [f"| {p['name']} | 0x{p['offset']:X} | 0x{p['size']:X} | {p.get('content', {}).get('type', '')} |"
              for p in report.partitions]
    md_path = out / "backup_verification.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path
