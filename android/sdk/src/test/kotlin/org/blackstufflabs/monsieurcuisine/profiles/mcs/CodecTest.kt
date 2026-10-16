package org.blackstufflabs.monsieurcuisine.profiles.mcs
import org.junit.Test
import org.junit.Assert.*
import org.json.JSONArray
import org.json.JSONObject


class CodecTest {
    private fun fixture(name: String)=javaClass.getResourceAsStream("/mcs/$name")!!.bufferedReader().use { it.readText() }
    @Test fun goldenAndSequence(){assertEquals("aa000a024f420001fe039f",McsCodec.hex(McsCodec.ota(3)));assertEquals(0x67,McsSequence(0x65).next());assertEquals(0,McsSequence(255).next())}
    @Test fun original900Envelopes(){val rows=JSONArray(fixture("envelope-reference-900.json"));assertEquals(900,rows.length());for(i in 0 until rows.length()){val r=rows.getJSONObject(i);assertEquals("case$i",r.getString("frame_hex"),McsCodec.hex(McsCodec.pack(McsCodec.unhex(r.getString("payload_hex")),r.getInt("sequence"))))}}
    @Test fun frozen900SdkVectors(){val rows=JSONArray(fixture("conformance-900.json"));assertEquals(900,rows.length())
        for(i in 0 until rows.length()){val row=rows.getJSONObject(i);val a=row.getJSONObject("arguments");val seq=a.optInt("sequence",1)
            val raw=when(row.getString("kind")){
                "manual"->McsCodec.manual(a.optInt("speed"),a.optInt("temperature"),a.optInt("seconds"),a.optBoolean("reverse"),seq)
                "operation"->McsCodec.operation(Operation(a.optInt("opcode",0x0802),a.optInt("speed_level"),a.optBoolean("reverse"),a.optInt("temperature_level"),a.optInt("constant_temperature"),a.optInt("function"),a.optInt("seconds"),a.optInt("scale_mode"),a.optInt("turbo_lock"),a.optInt("button"),a.optBoolean("legacy")),seq)
                else->McsCodec.ota(a.getInt("subcommand"),McsCodec.unhex(a.getString("data_hex")),a.optInt("packet_sequence"),seq)
            };assertEquals("case$i",row.getString("hex"),McsCodec.hex(raw));McsCodec.parse(raw)
        }
    }
    @Test fun telemetryMatchesPython(){val rows=JSONArray(fixture("android-rx-vectors.json"))
        for(i in 0 until rows.length()){val row=rows.getJSONObject(i);val d=row.getJSONObject("fields");val t=McsCodec.telemetry(McsCodec.unhex(row.getString("hex")))
            assertEquals(d.getInt("firmware_version"),t.firmware);assertEquals(d.getInt("error"),t.error);assertEquals(d.getInt("actual_temperature"),t.temperature)
            assertEquals(d.getInt("returned_temperature"),t.returnedTemperature);assertEquals(d.getInt("speed_level"),t.speedLevel);assertEquals(d.getInt("weight_raw"),t.weightRaw)
            assertEquals(d.getInt("temperature_unit"),t.temperatureUnit);assertEquals(d.getInt("turbo_key"),t.turboKey);assertEquals(d.getBoolean("lid_open"),t.lidOpen)
        }
    }
    @Test fun fragmentsConcatCorruptAndInterrupted(){val raw=McsCodec.manual(speed=4);for(split in 0..raw.size){val p=McsStreamParser();val out=p.feed(raw.copyOfRange(0,split))+p.feed(raw.copyOfRange(split,raw.size));assertEquals(1,out.size);assertArrayEquals(raw,out[0])}
        val bad=raw.copyOf();bad[bad.lastIndex]=(bad.last().toInt() xor 1).toByte();val p=McsStreamParser();assertEquals(2,p.feed(byteArrayOf(1,2)+bad+raw+raw).size);assertTrue(p.errors.isNotEmpty());p.feed(raw.copyOf(7));assertEquals(7,p.finish().size)
    }
    @Test fun partialTimeoutAndUnknown(){val raw=McsCodec.ota(2,ByteArray(256){0xaa.toByte()});val p=McsStreamParser();val got=mutableListOf<ByteArray>();raw.forEach{got.addAll(p.feed(byteArrayOf(it),0))};assertEquals(1,got.size)
        val q=McsStreamParser();q.feed(byteArrayOf(0xaa.toByte(),1,0)+McsCodec.ota(3),0);assertEquals(0,q.expire(500).size);assertEquals(1,q.expire(1100).size)
        val unknown=McsCodec.pack(byteArrayOf(0x12,0x34,99),bitmap=byteArrayOf(88));assertEquals(0x1234,McsCodec.parse(unknown).opcode)
    }
    @Test fun badRanges(){assertThrows(ProtocolException::class.java){McsCodec.manual(speed=11)};assertThrows(ProtocolException::class.java){McsCodec.manual(temperature=38)};assertThrows(ProtocolException::class.java){McsCodec.parse(McsCodec.ota(3).dropLast(1).toByteArray())}}
}

