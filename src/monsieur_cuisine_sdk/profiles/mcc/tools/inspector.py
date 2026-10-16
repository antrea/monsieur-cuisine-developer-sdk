"""Field-by-field inspection of the complete observed TX/RX envelope."""

from __future__ import annotations

from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import decode_frame

TX_FIELDS = (
    (0,1,"start","55 start marker"),(1,1,"size","Total frame length"),(2,1,"type","A1 TX kind"),
    (3,1,"operation","Known build292 opcode; unknown values retained"),(4,1,"tare_raw","A9 requests tare; otherwise00"),
    (5,1,"speed_level","Requested level0..10, not RPM"),(6,1,"temperature_level","Requested application temperature level0..19"),
    (7,4,"reserved","Offsets7..10 emitted zero by observed serializer"),(11,1,"wire_direction","00 CW /01 CCW; inverse of Android enum"),
    (12,1,"calibration","00 normal,E6 ENTER,E9 START; documentation only"),
    (13,1,"checksum","Sum offsets0..12 modulo256"),(14,1,"end","AA terminator"),
)
RX_FIELDS = (
    (0,1,"start","55 start marker"),(1,1,"size","Total frame length"),(2,1,"type","B1 RX kind"),
    (3,1,"status","Motor/heater low2bits; stable,CW,error,above-target,NTC,lid-open"),
    (4,1,"extended_state","3steam,4toast,5knead; others undefined"),(5,1,"error_code","Board code, distinct from Android mapped code"),
    (6,1,"target_speed_level","Raw requested level; original Java getter sign extends"),
    (7,2,"target_rpm","Unsigned16 big endian"),(9,2,"actual_rpm","Unsigned16 big endian"),
    (11,1,"target_temperature_level","Raw level; original Java getter sign extends"),
    (12,2,"target_temperature","Unsigned16 big endian; Celsius application label"),
    (14,2,"actual_temperature","Unsigned16 big endian; Celsius application label"),
    (16,4,"weight","Signed32 big endian; grams application label"),
    (20,2,"firmware_version","Unsigned16 big endian, reported version value"),
    (22,1,"scale_state_raw","Priority masks4 overload,1 calibration,2 normal; Android fallback overload"),
    (23,1,"calibration_step","0init,1zero,2onekg,3threekg,4success,5overload,7failure"),
    (24,1,"unknown_byte_24","Unknown semantics; raw preserved, signed Java view available"),
    (25,1,"checksum","Sum offsets0..24 modulo256"),(26,1,"end","AA terminator"),
)


def inspect_frame(raw: bytes | str) -> dict[str, object]:
    frame = decode_frame(raw)
    decoded = frame.to_dict()
    fields = []
    for offset,width,name,meaning in TX_FIELDS if frame.kind == "TX" else RX_FIELDS:
        value = decoded.get(name, int.from_bytes(frame.raw[offset:offset+width], "big"))
        fields.append({"offset":offset,"width":width,"name":name,"raw_hex":frame.raw[offset:offset+width].hex(" ").upper(),
                       "value":value,"meaning":meaning})
    return {"kind":frame.kind,"raw_hex":decoded["raw_hex"],"fields":fields,"decoded":decoded,
            "scope":"Observed build292 application protocol; no assertion of physical safety"}
