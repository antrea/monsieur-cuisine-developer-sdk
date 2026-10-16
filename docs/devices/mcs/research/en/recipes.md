> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Recipes and database research

**CONFIRMED_IN_APK:** tgi-v6.db uses greenDAO schema9, encrypted opening through SQLCipher and 29 registered tables. Filename v6 is not schema6. Raw bootstrap databases and migration code exist in the original app; none is distributed here. No database key was exported or decryption performed for this toolkit.

The visible model relates Recipe/FactoryRecipe/Category to ServingSize, Step, DeviceSetting and ordered Parameter entities. Device settings include reverse, turbo, size, texture, cleaningMode and mode; parameters hold speed, temperature, time and weight. Additional entities describe ingredient groups/amounts/translations, authors/tags/nutrients, media, favorites, notes/history/ratings, planning and paired devices. This is factual structure, not a copied catalog. Android normalizes some parameter combinations before constructing serial inputs; raw DAO values alone do not establish exactly what reaches the board.

Guided cooking schedules steps in Android and sends ordinary motor/thermal/timer fields. There is no evidence the MCU parses ingredient text, videos or recipe JSON. Cloud recipe synchronization is distinct from APK/Android/MCU updates. Offline local storage support does not establish today's recipe availability without login.

`examples/synthetic-recipe.json` is an original tutorial object with two made-up steps. Translate its speed/temperature/seconds fields through encode_manual; it is not an OEM DTO importer. MCC's localized embedded JSON/DBRecipes layout is different and cannot be substituted. Do not add paid Cookidoo/Bimby catalogs, personal account data, extracted databases or manufacturer media. A future neutral recipe model needs explicit adapters, units, mode mappings and provenance.
