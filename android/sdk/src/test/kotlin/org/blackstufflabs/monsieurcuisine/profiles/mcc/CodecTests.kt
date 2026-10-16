package org.blackstufflabs.monsieurcuisine.profiles.mcc

import org.junit.Assert.*
import org.junit.Test

class CodecTests {
    private fun resource(name: String) = javaClass.getResourceAsStream("/mcc/$name")!!.bufferedReader().use { it.readLines().filter { line -> line.isNotBlank() && !line.startsWith("#") } }

    @Test fun goldenTxMatchesExistingPythonDossierVectors() {
        for (line in resource("golden_tx_292.tsv")) {
            val columns = line.split('\t')
            val raw = MccCodec.encodeTx(Operation.entries.single { it.wire == columns[0].toInt() },
                columns[1].toInt(), columns[2].toInt(), Direction.entries.single { it.androidValue == columns[3].toInt() }, columns[4] == "1")
            assertEquals(columns[5], MccCodec.hex(raw))
        }
    }
    @Test fun everyDocumentedTxCombinationHasCorrectBoundsAndChecksum() {
        var count = 0
        for (operation in Operation.entries) for (speed in 0..10) for (temperature in 0..19)
            for (direction in Direction.entries) for (tare in listOf(false,true)) {
                val raw = MccCodec.encodeTx(operation,speed,temperature,direction,tare)
                assertEquals(15,raw.size); assertEquals(1-direction.androidValue,raw[11].toInt())
                assertEquals(raw.take(13).sumOf { it.toInt() and 255 } and 255,raw[13].toInt() and 255)
                MccCodec.validate(raw,15); count++
            }
        assertEquals(6160,count)
    }
    @Test fun goldenRxCoversSignedUnsignedAndAllStatusBits() {
        for (line in resource("golden_rx_292.tsv")) {
            val split = line.indexOf('\t')
            assertEquals(line.substring(split+1), CodecProbe.fields(MccCodec.decodeRx(MccCodec.parseHex(line.substring(0,split)))))
        }
    }
    @Test fun rejectsEverySingleBitMutation() {
        val original = MccCodec.parseHex(resource("golden_rx_292.tsv").first().substringBefore('\t'))
        for (index in original.indices) for (bit in 0..7) {
            val changed = original.copyOf(); changed[index] = (changed[index].toInt() xor (1 shl bit)).toByte()
            assertThrows(MccProtocolException::class.java) { MccCodec.decodeRx(changed) }
        }
    }
    @Test fun fragmentedConcatenatedAndCorruptStreamsResynchronize() {
        val raw = MccCodec.parseHex(resource("golden_rx_292.tsv").first().substringBefore('\t'))
        for (cut in 1..26) {
            val parser = MccStreamParser()
            assertTrue(parser.feed(raw.copyOfRange(0,cut)).isEmpty())
            assertArrayEquals(raw,parser.feed(raw.copyOfRange(cut,27)).single())
            assertEquals(0,parser.bufferedBytes)
        }
        val parser = MccStreamParser()
        val bad = raw.copyOf(); bad[25] = (bad[25].toInt() xor 1).toByte()
        val frames = parser.feed(byteArrayOf(1,2,3)+bad+raw+raw)
        assertEquals(2,frames.size); assertTrue(parser.protocolIssueCount>0)
        parser.feed(ByteArray(10000) { 0x55.toByte() })
        assertTrue(parser.bufferedBytes<=26); assertTrue(parser.issues.size<=64)
    }
    @Test fun strictEncoderAndUnknownFieldsStayDistinct() {
        assertThrows(IllegalArgumentException::class.java) { MccCodec.encodeTx(speed=11) }
        assertThrows(IllegalArgumentException::class.java) { MccCodec.encodeTx(temperatureLevel=-1) }
        val raw = MccCodec.parseHex(resource("golden_rx_292.tsv").first().substringBefore('\t'))
        raw[24]=0xFE.toByte(); raw[25]=MccCodec.checksum(raw.copyOfRange(0,25)).toByte()
        val state=MccCodec.decodeRx(raw)
        assertEquals(254,state.unknownByte24);assertEquals(-2,state.unknownByte24Signed)
    }
}

/** Host-only differential probe. Uses the exact SDK code consumed by the app. */
object CodecProbe {
    fun fields(s: MccState): String = listOf(s.status,s.motorHeaterState,s.motorOn,s.heaterOn,s.scaleStable,
        s.direction.androidValue,s.errorDetected,s.errorCode,s.androidErrorCode,s.aboveTargetTemperature,
        s.bowlNtcDetected,s.lidOpen,s.extendedState,s.targetSpeedLevel,s.targetRpm,s.actualRpm,
        s.targetTemperatureLevel,s.targetTemperature,s.actualTemperature,s.weight,s.firmwareVersion,
        s.scaleStateRaw,s.scaleState,s.calibrationStep,s.unknownByte24,s.actualSpeedLevel,
        s.targetSpeedLevelSigned,s.targetTemperatureLevelSigned,s.unknownByte24Signed,s.androidScaleState).joinToString("\t")
    @JvmStatic fun main(args: Array<String>) {
        generateSequence(::readLine).forEach { line ->
            val p=line.split('\t')
            when(p[0]) {
                "TX" -> println(MccCodec.hex(MccCodec.encodeTx(Operation.entries.single { it.wire==p[1].toInt() },p[2].toInt(),p[3].toInt(),Direction.entries.single { it.androidValue==p[4].toInt() },p[5]=="1")))
                "RX" -> println(fields(MccCodec.decodeRx(MccCodec.parseHex(p[1]))))
                else -> error("unsupported host test operation")
            }
        }
    }
}

