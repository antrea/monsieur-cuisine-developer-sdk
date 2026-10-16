package org.blackstufflabs.monsieurcuisine

import java.io.Closeable
import java.io.EOFException
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException
import java.util.concurrent.TimeUnit

interface Transport: Closeable {
    val model: DeviceModel
    val state: ConnectionState
    val lastError: IOException?
    fun connect()
    fun sendFrame(frame: ByteArray)
    fun receiveFrame(timeoutMillis: Int = 1000): ByteArray
    fun disconnect() = close()
}
/** Contract only. A physical serial adapter is not supplied. */
interface HardwareTransport: Transport

data class TwinEndpoint(val host: String="10.0.2.2", val port: Int=8765) {
    init {
        require(host in setOf("10.0.2.2","127.0.0.1")) { "only emulator host or literal localhost is permitted" }
        require(port in 1..65535)
    }
}

/** Blocking duplex I/O. One reader, serialized writes, explicit reconnect, no command replay. */
class TwinTcpTransport(val endpoint: TwinEndpoint, override val model: DeviceModel,
                       private val connectTimeoutMillis: Int=3000): Transport {
    constructor(model: DeviceModel): this(TwinEndpoint(port=model.defaultPort),model)
    private class Session(val socket: Socket, val parser: FrameParser) {
        val ready=ArrayDeque<ByteArray>()
    }
    private val lifecycle=Any(); private val writer=Any(); private val reader=Any()
    @Volatile override var state=ConnectionState.DISCONNECTED; private set
    @Volatile override var lastError: IOException?=null; private set
    @Volatile private var session: Session?=null
    init { require(connectTimeoutMillis>0) }
    override fun connect() {
        val next=Session(Socket(),WireProfiles.parser(model))
        synchronized(lifecycle) {
            if(session!=null) { next.socket.close(); throw IOException("disconnect before reconnecting") }
            session=next; state=ConnectionState.CONNECTING; lastError=null
        }
        try {
            next.socket.tcpNoDelay=true
            next.socket.connect(InetSocketAddress(endpoint.host,endpoint.port),connectTimeoutMillis)
            synchronized(lifecycle) {
                if(session!==next) throw IOException("connection cancelled")
                state=ConnectionState.CONNECTED
            }
        } catch(error: IOException) { fail(next,error); throw error }
    }
    private fun current(): Session {
        val found=session
        if(found==null || state!=ConnectionState.CONNECTED) throw IOException("not connected")
        return found
    }
    private fun fail(found: Session,error: IOException) {
        synchronized(lifecycle) {
            if(session===found) { session=null;state=ConnectionState.FAILED;lastError=error }
        }
        runCatching { found.socket.close() }
    }
    override fun sendFrame(frame: ByteArray) {
        val bytes=frame.copyOf()
        WireProfiles.validateTx(model,bytes)
        val found=current()
        synchronized(writer) {
            if(session!==found) throw IOException("obsolete write discarded")
            try { found.socket.getOutputStream().write(bytes);found.socket.getOutputStream().flush() }
            catch(error: IOException) { fail(found,error);throw error }
        }
    }
    override fun receiveFrame(timeoutMillis: Int): ByteArray = synchronized(reader) {
        require(timeoutMillis>0)
        val found=current()
        val deadline=System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(timeoutMillis.toLong())
        try {
            while(true) {
                if(session!==found) throw IOException("obsolete receive discarded")
                if(found.ready.isNotEmpty()) return@synchronized found.ready.removeFirst().copyOf()
                found.ready.addAll(found.parser.expire())
                if(found.ready.size>128) throw IOException("response queue bound exceeded")
                if(found.ready.isNotEmpty()) continue
                val remaining=deadline-System.nanoTime()
                if(remaining<=0) throw SocketTimeoutException("telemetry deadline expired")
                found.socket.soTimeout=TimeUnit.NANOSECONDS.toMillis(remaining).coerceIn(1,100).toInt()
                try {
                    val chunk=ByteArray(4096)
                    val count=found.socket.getInputStream().read(chunk)
                    if(count<0) throw EOFException("peer disconnected")
                    found.ready.addAll(found.parser.feed(chunk.copyOf(count)))
                    if(found.ready.size>128) throw IOException("response queue bound exceeded")
                } catch(_: SocketTimeoutException) { /* check frame expiry and caller deadline */ }
            }
            @Suppress("UNREACHABLE_CODE") byteArrayOf()
        } catch(timeout: SocketTimeoutException) { throw timeout }
        catch(error: IOException) { fail(found,error);throw error }
    }
    override fun close() {
        val old=synchronized(lifecycle) {
            val found=session;session=null;state=ConnectionState.DISCONNECTED;found
        }
        old?.socket?.close() // no reader/writer lock: close must wake blocked I/O
    }
}

/** Explicit frame fixture; never a second appliance physics engine. */
class MockTransport(override val model: DeviceModel): Transport {
    private val condition=java.lang.Object()
    private val received=ArrayDeque<ByteArray>();private val sent=mutableListOf<ByteArray>()
    private var parser=WireProfiles.parser(model);private var generation=0L
    @Volatile override var state=ConnectionState.DISCONNECTED; private set
    override val lastError: IOException? get()=null
    val sentFrames get()=synchronized(condition) { sent.map { it.copyOf() } }
    override fun connect() = synchronized(condition) {
        if(state==ConnectionState.CONNECTED) throw IOException("already connected")
        generation++;received.clear();parser=WireProfiles.parser(model);state=ConnectionState.CONNECTED;condition.notifyAll()
    }
    fun injectRawRx(data: ByteArray) = synchronized(condition) {
        check(state==ConnectionState.CONNECTED)
        val frames=parser.feed(data)
        if(received.size+frames.size>128) throw IOException("mock queue bound exceeded")
        received.addAll(frames);condition.notifyAll()
    }
    override fun sendFrame(frame: ByteArray) = synchronized(condition) {
        if(state!=ConnectionState.CONNECTED) throw IOException("not connected")
        val bytes=frame.copyOf();WireProfiles.validateTx(model,bytes);sent.add(bytes);Unit
    }
    override fun receiveFrame(timeoutMillis: Int): ByteArray = synchronized(condition) {
        require(timeoutMillis>0)
        val epoch=generation
        val deadline=System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(timeoutMillis.toLong())
        while(received.isEmpty() && state==ConnectionState.CONNECTED && generation==epoch) {
            val left=deadline-System.nanoTime()
            if(left<=0) throw SocketTimeoutException("mock telemetry deadline expired")
            condition.wait(TimeUnit.NANOSECONDS.toMillis(left).coerceAtLeast(1))
        }
        if(state!=ConnectionState.CONNECTED || generation!=epoch) throw IOException("mock session closed")
        received.removeFirst().copyOf()
    }
    override fun close() = synchronized(condition) {
        generation++;state=ConnectionState.DISCONNECTED;received.clear();condition.notifyAll()
    }
}
