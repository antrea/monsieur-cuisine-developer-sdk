package org.blackstufflabs.monsieurcuisine

import org.blackstufflabs.monsieurcuisine.profiles.mcc.MccCodec
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.concurrent.thread

/** Regressions for independent-audit findings A1 (close racing connect) and A2 (MCC burst). */
class ClientRaceAndBurstTest {
    private class GatedTransport(val inner: Transport): Transport {
        val entered=CountDownLatch(1); val release=CountDownLatch(1)
        override val model get()=inner.model
        override val state get()=inner.state
        override val lastError get()=inner.lastError
        override fun connect() { entered.countDown(); release.await(5,TimeUnit.SECONDS); inner.connect() }
        override fun sendFrame(frame: ByteArray)=inner.sendFrame(frame)
        override fun receiveFrame(timeoutMillis: Int)=inner.receiveFrame(timeoutMillis)
        override fun close()=inner.close()
    }

    private fun mccRx(): ByteArray=javaClass.getResourceAsStream("/mcc/golden_rx_292.tsv")!!.bufferedReader().use {
        MccCodec.parseHex(it.readLines().first { row -> row.isNotBlank() && !row.startsWith("#") }.substringBefore('\t'))
    }

    @Test fun closeDuringConnectReleasesTheTransport() {
        ServerSocket(0,50,InetAddress.getByName("127.0.0.1")).use { server ->
            val accepted=AtomicReference<Socket?>()
            val acceptor=thread(isDaemon=true) { try { accepted.set(server.accept()) } catch(_: Throwable) {} }
            val tcp=TwinTcpTransport(TwinEndpoint("127.0.0.1",server.localPort),DeviceModel.MCC)
            val gated=GatedTransport(tcp)
            val client=MonsieurCuisineClient(DeviceModel.MCC,gated)
            val failure=AtomicReference<Throwable?>()
            val connector=thread { try { client.connect() } catch(t: Throwable) { failure.set(t) } }
            assertTrue(gated.entered.await(2,TimeUnit.SECONDS))
            client.close()
            gated.release.countDown()
            connector.join(5000); acceptor.join(2000)
            assertTrue(failure.get() is IOException)
            assertEquals(ConnectionState.DISCONNECTED,tcp.state)
            assertThrows(IOException::class.java) { client.stopMotor() }
            client.connect()   // an explicit new connect is possible again
            assertEquals(ConnectionState.CONNECTED,client.state)
            client.close(); accepted.get()?.close()
        }
    }

    @Test fun mccBurstAboveTheQueueBoundIsReceivedWithoutFailingTheSession() {
        ServerSocket(0,1,InetAddress.getByName("127.0.0.1")).use { server ->
            val frame=mccRx(); val count=200
            val worker=thread(isDaemon=true) {
                try { server.accept().use { peer ->
                    val all=java.io.ByteArrayOutputStream(); repeat(count) { all.write(frame) }
                    peer.getOutputStream().write(all.toByteArray()); peer.getOutputStream().flush(); Thread.sleep(1500)
                } } catch(_: Throwable) {}
            }
            val client=MonsieurCuisineClient(DeviceModel.MCC,TwinTcpTransport(TwinEndpoint("127.0.0.1",server.localPort),DeviceModel.MCC))
            client.connect(); Thread.sleep(300)
            repeat(count) { assertEquals(DeviceModel.MCC,client.receiveState(1000).model) }
            assertEquals(ConnectionState.CONNECTED,client.state)
            client.close(); worker.join(2000)
        }
    }
}
