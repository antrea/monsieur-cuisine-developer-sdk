"""Bounded local image/ELF inspection; no mounting, execution or device access."""
from __future__ import annotations

import json
from pathlib import Path
import struct

from ..backup.image import RawImage, sha256_file
from ..backup.inventory import filesystem_info
from .bootimg import parse_boot_image
from .gpt import read_table
from .mtk import parse_preloader, parse_mtk_header

ELF_MACHINES = {3: "x86", 40: "ARM", 62: "x86_64", 183: "AArch64"}


def inspect_image(path, *, hash_content=False, cancelled=lambda: False):
    if not Path(path).is_file():
        raise ValueError("select a regular image file, never a device")
    image = RawImage(path)
    header = image.read_at(0, 4096)
    result = {"schema": "mcc-image-inspection-v1", "bytes": image.size, "read_only": True,
              "hardware_compatibility": "UNVERIFIED", "identifiers_included": False}
    if header[512:520] == b"EFI PART":
        table = read_table(image.read_at, disk_sectors=image.size // 512)
        result.update({"type": "gpt-disk", "problems": table.problems,
                       "partitions": [{"name": part.name, "offset": part.offset(512), "bytes": part.size(512)}
                                      for part in table.partitions]})
    elif header[:8] == b"ANDROID!":
        if image.size > 128 * 1024**2:
            raise ValueError("boot image exceeds 128 MiB inspection bound")
        boot = parse_boot_image(image.read_at(0, image.size))
        result.update({"type": "android-boot", "page_size": boot.page_size,
                       "header_version": boot.header_version, "sections": boot.sections()})
    elif header[:4] == b"\x7fELF":
        if len(header) < 52 or header[4] not in (1, 2) or header[5] not in (1, 2):
            raise ValueError("invalid ELF identification")
        machine = struct.unpack_from(("<" if header[5] == 1 else ">") + "H", header, 18)[0]
        result.update({"type": "elf", "bits": 32 if header[4] == 1 else 64,
                       "endianness": "little" if header[5] == 1 else "big",
                       "machine": machine, "architecture": ELF_MACHINES.get(machine, "unknown")})
    elif header[:9] == b"EMMC_BOOT":
        info = parse_preloader(image.read_at(0, min(image.size, 0x40000)))
        result.update({"type": "mtk-preloader", "emmc_boot": info.emmc_boot, "brlyt_offset": info.brlyt_offset})
    elif header[:4] == b"\x88\x16\x88\x58":
        wrapper = parse_mtk_header(header)
        result.update({"type": "mtk-wrapper", "payload_bytes": wrapper.size})
    else:
        try:
            result.update({"type": "ext4", "filesystem": filesystem_info(image)})
        except ValueError:
            result["type"] = "unknown raw data"
    if hash_content:
        result["sha256"] = sha256_file(path, cancelled=cancelled)
    return result


def inspect_elf(path, *, max_functions=64, max_instructions=2000):
    """Optional real disassembly of exported functions, never ELF execution."""
    if type(max_functions) is not int or not 1 <= max_functions <= 256:
        raise ValueError("max_functions must be 1..256")
    if type(max_instructions) is not int or not 1 <= max_instructions <= 10000:
        raise ValueError("max_instructions must be 1..10000")
    try:
        from elftools.elf.elffile import ELFFile
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB, CS_ARCH_ARM64, CS_ARCH_X86, CS_MODE_32, CS_MODE_64
    except ImportError as exc:
        raise RuntimeError("install the optional analysis extra for ELF symbols/disassembly") from exc
    path = Path(path)
    if path.stat().st_size > 64 * 1024**2:
        raise ValueError("ELF exceeds the analysis bound")
    report = inspect_image(path, hash_content=True)
    if report["type"] != "elf" or report["endianness"] != "little":
        raise ValueError("disassembly supports little-endian ARM/AArch64/x86 ELF only")
    with path.open("rb") as source:
        elf = ELFFile(source)
        if elf.num_sections() > 4096:
            raise ValueError("ELF section count exceeds analysis bound")
        needed, imports, functions = [], [], []
        for section in elf.iter_sections():
            if section.name == ".dynamic":
                needed = [tag.needed for tag in section.iter_tags() if tag.entry.d_tag == "DT_NEEDED"][:256]
        symbols = elf.get_section_by_name(".dynsym")
        if symbols is not None:
            if symbols.num_symbols() > 100000:
                raise ValueError("ELF symbol count exceeds analysis bound")
            ordered = sorted(symbols.iter_symbols(), key=lambda symbol: not symbol.name.startswith("Java_"))
            for symbol in ordered:
                if symbol["st_shndx"] == "SHN_UNDEF" and symbol.name and len(imports) < 1024:
                    imports.append(symbol.name[:1024])
                if (symbol["st_info"]["type"] != "STT_FUNC" or not isinstance(symbol["st_shndx"], int)
                        or not 0 < symbol["st_size"] <= 65536 or len(functions) >= max_functions):
                    continue
                raw_address = symbol["st_value"]
                address = raw_address & ~1 if elf["e_machine"] == "EM_ARM" else raw_address
                section = elf.get_section(symbol["st_shndx"])
                offset = section["sh_offset"] + address - section["sh_addr"]
                if offset < 0 or offset + symbol["st_size"] > path.stat().st_size:
                    raise ValueError("ELF function extends beyond its file")
                if elf["e_machine"] == "EM_ARM":
                    decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB if raw_address & 1 else CS_MODE_ARM)
                elif elf["e_machine"] == "EM_AARCH64":
                    decoder = Cs(CS_ARCH_ARM64, 0)
                elif elf["e_machine"] in ("EM_386", "EM_X86_64"):
                    decoder = Cs(CS_ARCH_X86, CS_MODE_32 if elf["e_machine"] == "EM_386" else CS_MODE_64)
                else:
                    raise ValueError("unsupported ELF instruction set")
                source.seek(offset)
                instructions = []
                for instruction in decoder.disasm(source.read(symbol["st_size"]), address):
                    if len(instructions) >= max_instructions:
                        break
                    instructions.append({"address": instruction.address, "bytes": instruction.bytes.hex(),
                                         "mnemonic": instruction.mnemonic, "operands": instruction.op_str})
                functions.append({"symbol": symbol.name[:1024], "address": address, "file_offset": offset,
                                  "bytes": symbol["st_size"], "instructions": instructions,
                                  "instruction_limit_reached": len(instructions) == max_instructions})
        report.update({"needed": needed, "imports": imports, "functions": functions,
                       "analysis": "static disassembly, not dynamic execution or proof of hardware behavior"})
    return report


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("image", "elf", "apk"))
    parser.add_argument("file", type=Path)
    parser.add_argument("--aapt")
    parser.add_argument("--hash", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.kind == "apk":
            from ..adb import inspect_apk, metadata_dict
            if not args.aapt:
                raise ValueError("APK inspection needs an explicit aapt executable")
            result = metadata_dict(inspect_apk(args.file, aapt=args.aapt))
        elif args.kind == "elf":
            result = inspect_elf(args.file)
        else:
            result = inspect_image(args.file, hash_content=args.hash)
        text = json.dumps(result, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as output:
                output.write(text)
        else:
            print(text, end="")
        return 0
    except (ValueError, OSError, RuntimeError):
        print(json.dumps({"error": "local image/analysis input rejected; check format, bounds and optional tools"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
