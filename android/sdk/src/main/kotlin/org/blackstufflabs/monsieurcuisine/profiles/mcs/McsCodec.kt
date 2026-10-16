package org.blackstufflabs.monsieurcuisine.profiles.mcs

/** Original historical MC30 codec. Wire facts from static APK research; no hardware claim. */
class ProtocolException(message: String): IllegalArgumentException(message)
data class Frame(val raw: ByteArray, val bitmap: ByteArray, val subtype: Int, val sequence: Int,
                 val opcode: Int, val payload: ByteArray, val checksum: Int)
class McsSequence(private var value: Int=0) {
    init { require(value in 0..255) }
    @Synchronized fun next(): Int { value=(value+1) and 255; if(value==0x66)value=0x67; return value }
}
data class Operation(val opcode: Int=0x0802,val speedLevel: Int=0,val reverse: Boolean=false,
    val temperatureLevel: Int=0,val constantTemperature: Int=0,val function: Int=0,val seconds: Int=0,
    val scaleMode: Int=0,val turboLock: Int=0,val button: Int=0,val legacy: Boolean=false)
data class Telemetry(val frame: Frame,val firmware: Int,val state: Int,val error: Int,val returnCode: Int,
    val temperatureLevel: Int,val returnedTemperature: Int,val temperature: Int,val temperatureUnit: Int,
    val speedLevel: Int,val directionRaw: Int,val turboKey: Int,val function: Int,val weightRaw: Int,
    val weightUnit: Int,val decimalPlaces: Int,val scaleState: Int,val calibrationStep: Int,
    val countdownSeconds: Int,val lightRaw: Int,val buttonRaw: Int) {
    val lidOpen get()=(state and 0x80)!=0
    val ntcAbsent get()=(state and 0x40)!=0
    val scaleStable get()=(state and 4)!=0
    val uiSpeed get()=speedLevel/2
    val errorName get()=McsCodec.errors[error] ?: "UNKNOWN"
    val weight get()=weightRaw/Math.pow(10.0,decimalPlaces.toDouble())
}
object McsCodec {
    val temperatures=listOf(0,37,40,45,50,55,60,65,70,75,80,85,90,95,100,105,110,115,120,125,130)
    val errors=mapOf(0 to "NORMAL",1 to "SERIAL_PORT_ERROR",3 to "MOTOR_FAILURE",4 to "VOLTAGE_OVERLOAD",5 to "MOTOR_ERROR",6 to "DRY_BURN_ALARM",7 to "OVER_TEMPERATURE_PROTECTION",8 to "TIMEOUT_PROTECTION",9 to "OTHER_ERROR")
    private val operations=setOf(0x0801,0x0802,0x0803,0x0805)
    fun u8(v: Byte)=v.toInt() and 255
    private fun uint(v: Int,max: Int,name: String) { if(v !in 0..max)throw ProtocolException("$name outside 0..$max") }
    private fun put16(p: ByteArray,i: Int,v: Int) { p[i]=(v ushr 8).toByte();p[i+1]=v.toByte() }
    fun u16(p: ByteArray,i: Int)=(u8(p[i]) shl 8) or u8(p[i+1])
    private fun s16(p: ByteArray,i: Int)=u16(p,i).toShort().toInt()
    private fun s32(p: ByteArray,i: Int)=(u8(p[i]) shl 24) or (u8(p[i+1]) shl 16) or (u8(p[i+2]) shl 8) or u8(p[i+3])
    fun pack(payload: ByteArray,sequence: Int=1,subtype: Int=0,bitmap: ByteArray=byteArrayOf(0x4f,0x42)): ByteArray {
        uint(sequence,255,"sequence");uint(subtype,255,"subtype")
        if(payload.size<2 || bitmap.size !in 1..255)throw ProtocolException("opcode/bitmap bounds")
        val total=7+bitmap.size+payload.size
        if(total>65536)throw ProtocolException("frame too large")
        val out=ByteArray(total);out[0]=0xaa.toByte();put16(out,1,total-1);out[3]=bitmap.size.toByte()
        bitmap.copyInto(out,4);out[4+bitmap.size]=subtype.toByte();out[5+bitmap.size]=sequence.toByte()
        payload.copyInto(out,6+bitmap.size);out[out.lastIndex]=checksum(out).toByte();return out
    }
    fun checksum(raw: ByteArray): Int { var sum=0;for(i in 1 until raw.lastIndex)sum=(sum+u8(raw[i])) and 255;return sum }
    fun parse(raw: ByteArray): Frame {
        if(raw.size<10 || u8(raw[0])!=0xaa)throw ProtocolException("invalid/incomplete header")
        if(u16(raw,1)+1!=raw.size)throw ProtocolException("length mismatch")
        if(checksum(raw)!=u8(raw.last()))throw ProtocolException("checksum mismatch")
        val n=u8(raw[3]);val start=6+n
        if(n==0 || raw.size<start+3)throw ProtocolException("bitmap/payload bounds")
        val payload=raw.copyOfRange(start,raw.lastIndex)
        return Frame(raw.copyOf(),raw.copyOfRange(4,4+n),u8(raw[4+n]),u8(raw[5+n]),u16(payload,0),payload,u8(raw.last()))
    }
    private fun timer(seconds: Int): ByteArray {
        uint(seconds,255*3600+3599,"seconds")
        return byteArrayOf((seconds/3600).toByte(),(seconds/60%60).toByte(),(seconds%60).toByte())
    }
    fun operation(c: Operation=Operation(),sequence: Int=1): ByteArray {
        if(c.opcode !in operations)throw ProtocolException("unsupported operation opcode")
        uint(c.speedLevel,20,"speed level");uint(c.temperatureLevel,20,"temperature level")
        for((v,n) in listOf(c.constantTemperature to "constant",c.function to "function",c.scaleMode to "scale mode",c.turboLock to "turbo",c.button to "button"))uint(v,255,n)
        val p=ByteArray(if(c.legacy)26 else 30);put16(p,0,c.opcode)
        p[2]=c.temperatureLevel.toByte();p[3]=0;p[4]=c.constantTemperature.toByte() // APK compatibility quirk
        p[8]=c.speedLevel.toByte();p[9]=if(c.reverse)1 else 0;p[10]=c.turboLock.toByte();p[11]=c.function.toByte()
        p[13]=c.scaleMode.toByte();timer(c.seconds).copyInto(p,17);p[25]=c.button.toByte();return pack(p,sequence)
    }
    fun manual(speed: Int=0,temperature: Int=0,seconds: Int=0,reverse: Boolean=false,sequence: Int=1): ByteArray {
        uint(speed,10,"UI speed");uint(seconds,5940,"manual seconds")
        val level=temperatures.indexOf(temperature);if(level<0)throw ProtocolException("temperature absent from table")
        return operation(Operation(speedLevel=speed*2,temperatureLevel=level,function=1,seconds=seconds,reverse=reverse),sequence)
    }
    fun ota(subcommand: Int,data: ByteArray=byteArrayOf(),packetSequence: Int=0,sequence: Int=1): ByteArray {
        val tail=when(subcommand) {
            1 -> { if(data.size!=16)throw ProtocolException("metadata must be 16 bytes");data.copyOf() }
            2 -> { if(data.size>256)throw ProtocolException("segment >256");uint(packetSequence,65535,"packet sequence");ByteArray(258).also{put16(it,0,packetSequence);data.copyInto(it,2)} }
            3,4,6 -> { if(data.isNotEmpty())throw ProtocolException("query has no data");byteArrayOf() }
            else -> throw ProtocolException("unsupported outbound OTA")
        };return pack(byteArrayOf(0xfe.toByte(),subcommand.toByte())+tail,sequence)
    }
    fun telemetry(raw: ByteArray): Telemetry {
        val f=parse(raw);val p=f.payload
        if(!f.bitmap.contentEquals(byteArrayOf(0x4f,0x42)) || f.subtype!=0 || f.opcode !in operations || p.size!=39)throw ProtocolException("not active multo RX48")
        if(u8(p[32])>59 || u8(p[33])>59)throw ProtocolException("invalid countdown HMS")
        return Telemetry(f,u16(p,2),u8(p[4]),u8(p[7]),u8(p[8]),p[9].toInt(),s16(p,10),s16(p,12),p[14].toInt(),
            p[17].toInt(),u8(p[18]),p[19].toInt(),u8(p[20]),s32(p,22),u8(p[21]) ushr 4,u8(p[21]) and 15,
            u8(p[26]),u8(p[27]),u8(p[31])*3600+u8(p[32])*60+u8(p[33]),u8(p[37]),u8(p[38]))
    }
    fun hex(raw: ByteArray)=raw.joinToString(""){ "%02x".format(u8(it)) }
    fun unhex(text: String): ByteArray { val s=text.filterNot{it.isWhitespace()};if(s.length%2!=0)throw ProtocolException("odd HEX length");return ByteArray(s.length/2){s.substring(it*2,it*2+2).toInt(16).toByte()} }
}

/** Bounded partial/concatenated stream parser. Timeout is host policy, not MCU watchdog. */
class McsStreamParser(val maxFrame: Int=4096,val timeoutMillis: Long=1000) {
    private var buffer=byteArrayOf();private var since: Long?=null
    val errors=java.util.ArrayDeque<String>()
    init { require(maxFrame in 10..65536 && timeoutMillis>0) }
    private fun error(text: String) { if(errors.size>=1024)errors.removeFirst();errors.addLast(text) }
    fun feed(data: ByteArray,now: Long=System.nanoTime()/1_000_000): List<ByteArray> {
        // Process bounded pieces rather than retaining an arbitrary caller-sized input.
        if(data.size>4096) { val frames=mutableListOf<ByteArray>();data.asList().chunked(4096).forEach{frames.addAll(feed(it.toByteArray(),now))};return frames }
        buffer+=data;val frames=mutableListOf<ByteArray>()
        while(buffer.isNotEmpty()) {
            if(McsCodec.u8(buffer[0])!=0xaa) { val next=buffer.indexOf(0xaa.toByte()).let{if(it<0)buffer.size else it};buffer=buffer.copyOfRange(next,buffer.size);since=null;error("noise:$next");continue }
            if(since==null)since=now
            if(buffer.size<3)break
            val total=McsCodec.u16(buffer,1)+1
            if(total !in 10..maxFrame){buffer=buffer.copyOfRange(1,buffer.size);since=null;error("length:$total");continue}
            if(buffer.size<total)break
            val raw=buffer.copyOfRange(0,total)
            try { McsCodec.parse(raw) } catch(e: ProtocolException) { buffer=buffer.copyOfRange(1,buffer.size);since=null;error(e.message ?: "corrupt");continue }
            frames.add(raw);buffer=buffer.copyOfRange(total,buffer.size);since=null
        };return frames
    }
    fun expire(now: Long=System.nanoTime()/1_000_000): List<ByteArray> {
        if(buffer.isNotEmpty() && since!=null && now-since!!>=timeoutMillis){buffer=buffer.copyOfRange(1,buffer.size);since=null;error("timeout")}
        return feed(byteArrayOf(),now)
    }
    fun finish(): ByteArray { val tail=buffer;buffer=byteArrayOf();since=null;if(tail.isNotEmpty())error("interrupted:${tail.size}");return tail }
}

