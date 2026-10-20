# MCC build 292 software-reference vectors

`mcc_292_vectors.jsonl` contains 9,642 input/output records produced by locally
executing the original `PowerBoard`, `CookingUtils` and `Limits` bytecode from
the owner's private MCC backup in an isolated JVM. The complete private run
compared 57,998 cases; this deterministic subset is the portable regression set.
Only inputs and resulting values/bytes are included: no manufacturer code,
binary, firmware image, recipe, personal data or device identifier is distributed.

The reference is the Android host application `de.silpion.mc2`, version 1.1.28,
build 292. These vectors verify host serialization, decoding and pure conversion
functions, not the controller firmware, physical dynamics or hardware safety.
Static cooking/UI policy observations have a different evidence level and are
identified separately in the documentation.

Run `python -m unittest discover -s tests -p test_oem_golden_vectors.py -v` after
installing the SDK. Plain JSONL is used so the ordinary public-source audit can
inspect all records without a binary exception or a decompression dependency.
