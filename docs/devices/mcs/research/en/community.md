> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Community references and attribution

These links are research references preserved from the earlier investigation, not runtime services or guarantees about future project status.

- [AroPix/MCS2MQTT](https://github.com/AroPix/MCS2MQTT), examined commit `ae5ecac66455fa703b8a13881118b678d9530c30`: Android Xposed/LSPosed hooks add a decoded application listener and publish temperature/weight/time/speed/recipe information to MQTT. It does not decode UART framing. Obfuscated hook names differ from acquired1.2.14.15; direct compatibility was not demonstrated. No explicit application-code license was found in the examined checkout, so no source is copied here.
- [MCS discussion #38](https://github.com/EliasKotlyar/Monsieur-Cuisine-Connect-Hack/issues/38): community observations, listener work and historical acquisition context. A claimed replacement application was not located as acquired source; it is not part of this toolkit.
- [Historical discussion #31](https://github.com/EliasKotlyar/Monsieur-Cuisine-Connect-Hack/issues/31): historical update/database context; do not treat old temporary links as current acquisitions.
- [Monsieur-Cuisine-Connect-Hack](https://github.com/EliasKotlyar/Monsieur-Cuisine-Connect-Hack): broader research context, with different models/builds requiring separate evidence.
- [1101011 MCS hardware notes](https://1101011.xyz/lidl-monsieur-cuisine-smart/index.html): Android platform/security-chip context; does not identify the motor MCU.
- [MrVain74/ha-monsieur-cuisine](https://github.com/MrVain74/ha-monsieur-cuisine): external community integration reference, not a UART specification source or bundled dependency.

Original research directly checked APK/Smali registry and serializer behavior; attribution to community work does not turn all observations into independently measured hardware facts. GitHub visibility alone is not permission to relicense code. No community source code is included. Installation/root/hooking procedures were not executed by this toolkit.
