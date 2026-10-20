package org.blackstufflabs.monsieurcuisine

import java.io.IOException
import java.net.SocketTimeoutException
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

/** Worker-thread API. Writes do not wait for or fabricate acknowledgments. */
enum class HostPolicyMode { OEM, STRICT }

class MonsieurCuisineClient @JvmOverloads constructor(val model: DeviceModel, val transport: Transport,
                           val hostPolicy: HostPolicyMode = HostPolicyMode.OEM): AutoCloseable {
    val capabilities=WireProfiles.capabilities(model)
    private val lifecycle=Any();private val commands=Any();private val epoch=AtomicLong()
    private var connecting=false;private var requested=RequestedOperation();private var sequence=0
    private var lastQueryAtNanos: Long?=null
    @Volatile private var observed: DeviceState?=null
    @Volatile var onFrame: ((FrameEvent)->Unit)?=null
    init { require(model==transport.model) { "model/transport mismatch" } }
    val state get()=transport.state
    val sessionGeneration get()=epoch.get()
    fun connect() {
        val generation=synchronized(lifecycle) {
            if(connecting || state==ConnectionState.CONNECTED || state==ConnectionState.CONNECTING)
                throw IOException("already connected or connecting")
            connecting=true;observed=null
            synchronized(commands) { requested=RequestedOperation();sequence=0;lastQueryAtNanos=null }
            epoch.incrementAndGet()
        }
        try {
            transport.connect()
            synchronized(lifecycle) {
                if(epoch.get()!=generation) {
                    // close() ran before the transport had a session to close:
                    // release the socket opened afterwards instead of leaking it.
                    transport.close()
                    throw IOException("client connection cancelled")
                }
                connecting=false
            }
        } catch(error: Exception) {
            synchronized(lifecycle) { if(epoch.get()==generation) { connecting=false;transport.close() } }
            throw error
        }
    }
    private fun nextSequence(): Int {
        sequence=(sequence+1) and 255
        if(sequence==0x66) sequence=0x67
        return sequence
    }
    private fun write(build: (RequestedOperation)->RequestedOperation) {
        val generation=epoch.get()
        val bytes=synchronized(commands) {
            if(epoch.get()!=generation) throw IOException("obsolete command discarded")
            val candidate=build(requested)
            val next=if(model==DeviceModel.MCC && candidate.running) {
                require(candidate.speed in 0..10) { "speed must be 0..10" }
                val cap=if(candidate.temperatureC>0 || candidate.direction==MotorDirection.COUNTER_CLOCKWISE) 3 else 10
                val adapted=candidate.speed.coerceIn(1,cap)
                require(hostPolicy!=HostPolicyMode.STRICT || adapted==candidate.speed) { "MCC host speed policy" }
                observed?.let { state ->
                    require(!state.lidOpen && state.errorCode==0) { "MCC host start gate" }
                    require(state.actualTemperatureC<60 || adapted<4) { "hot-speed confirmation unavailable in Kotlin client" }
                }
                candidate.copy(speed=adapted)
            } else candidate
            val frame=WireProfiles.encode(model,next,nextSequence())
            transport.sendFrame(frame);requested=next;frame
        }
        if(epoch.get()==generation) onFrame?.invoke(FrameEvent(model,generation,"TX",WireProfiles.hex(bytes)))
    }
    fun startMotor(speed: Int, direction: MotorDirection=MotorDirection.CLOCKWISE,
                   temperatureC: Int=0, durationSeconds: Int=0) =
        write { RequestedOperation(true,speed,direction,temperatureC,durationSeconds) }
    fun stopMotor() = write { RequestedOperation(direction=it.direction) }
    fun setDirection(direction: MotorDirection) = write { it.copy(direction=direction) }
    private fun receiveRaw(timeoutMillis: Int,generation:Long):ByteArray {
        require(timeoutMillis>0)
        val deadline=System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(timeoutMillis.toLong())
        while(true) {
            val poll=synchronized(commands) {
                if(epoch.get()!=generation) throw IOException("obsolete poll discarded")
                val previous=lastQueryAtNanos
                if(capabilities.telemetryRequiresQuery && (previous==null || System.nanoTime()-previous>=250_000_000L)) {
                    WireProfiles.poll(model,nextSequence())!!.also {
                        transport.sendFrame(it);lastQueryAtNanos=System.nanoTime()
                    }
                } else null
            }
            if(poll!=null && epoch.get()==generation) onFrame?.invoke(FrameEvent(model,generation,"TX",WireProfiles.hex(poll)))
            val remaining=deadline-System.nanoTime()
            if(remaining<=0)throw SocketTimeoutException("telemetry deadline expired")
            // A stream of unsolicited frames must not create a matching stream
            // of new queries. Poll cadence is independent of receive throughput.
            val untilQuery=synchronized(commands) {
                if(capabilities.telemetryRequiresQuery)250_000_000L-(System.nanoTime()-(lastQueryAtNanos ?: 0L)) else remaining
            }
            val waitMillis=TimeUnit.NANOSECONDS.toMillis(minOf(remaining,untilQuery.coerceAtLeast(1))).coerceAtLeast(1).toInt()
            try { return transport.receiveFrame(waitMillis) }
            catch(timeout:SocketTimeoutException) {
                if(!capabilities.telemetryRequiresQuery || System.nanoTime()>=deadline)throw timeout
            }
        }
    }
    /** Receives observations, querying MCS at most four times/second within the caller's deadline. */
    fun receiveState(timeoutMillis: Int=1000): DeviceState {
        val generation=epoch.get()
        val raw=receiveRaw(timeoutMillis,generation)
        val decoded=WireProfiles.decode(model,raw,generation)
        synchronized(lifecycle) {
            if(epoch.get()!=generation || state!=ConnectionState.CONNECTED) throw IOException("stale telemetry discarded")
            observed=decoded
        }
        if(epoch.get()==generation) onFrame?.invoke(FrameEvent(model,generation,"RX",decoded.rawHex))
        synchronized(lifecycle) {
            if(epoch.get()!=generation || state!=ConnectionState.CONNECTED) throw IOException("session changed during telemetry callback")
        }
        return decoded
    }
    /** Cached observation; null until telemetry arrives or after a lifecycle transition. */
    fun readState(): DeviceState?=if(state==ConnectionState.CONNECTED)observed else null
    fun readTemperature(): Int?=readState()?.actualTemperatureC
    fun readWeight(): Double?=readState()?.weightGrams
    fun readErrors(): Pair<Int,String>?=readState()?.let { it.errorCode to it.errorName }
    fun disconnect()=close()
    override fun close() {
        synchronized(lifecycle) {
            epoch.incrementAndGet();connecting=false;observed=null
            transport.close()
            // A new connect resets requests under the command lock. Do not wait
            // for that lock here: socket closure must cancel pending work promptly.
        }
    }
}
