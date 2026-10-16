package org.blackstufflabs.monsieurcuisine

import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.net.InetAddress
import java.net.ServerSocket
import java.net.SocketTimeoutException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.concurrent.thread
import org.blackstufflabs.monsieurcuisine.profiles.mcc.MccCodec
import org.blackstufflabs.monsieurcuisine.profiles.mcs.McsCodec

class SharedClientTest {
    private fun rx(model:DeviceModel):ByteArray = when(model) {
        DeviceModel.MCC -> javaClass.getResourceAsStream("/mcc/golden_rx_292.tsv")!!.bufferedReader().use {
            MccCodec.parseHex(it.readLines().first { row -> row.isNotBlank() && !row.startsWith("#") }.substringBefore('\t'))
        }
        DeviceModel.MCS -> org.json.JSONArray(javaClass.getResourceAsStream("/mcs/android-rx-vectors.json")!!.bufferedReader().readText())
            .getJSONObject(0).getString("hex").let(McsCodec::unhex)
    }
    @Test fun explicitModelsAndEndpointPolicy() {
        assertThrows(IllegalArgumentException::class.java) { MonsieurCuisineClient(DeviceModel.MCC,MockTransport(DeviceModel.MCS)) }
        for(host in listOf("0.0.0.0","localhost","192.168.1.1","example.com"))
            assertThrows(IllegalArgumentException::class.java) { TwinEndpoint(host) }
        assertThrows(IllegalArgumentException::class.java) { TwinEndpoint(port=0) }
    }
    @Test fun capabilitiesPreserveProtocolDifferencesAndInputBounds() {
        for(model in DeviceModel.entries) {
            val transport=MockTransport(model);val client=MonsieurCuisineClient(model,transport);client.connect()
            assertEquals(model==DeviceModel.MCS,client.capabilities.supportsDuration)
            assertThrows(IllegalArgumentException::class.java) { client.startMotor(11) }
            assertThrows(IllegalArgumentException::class.java) { client.startMotor(2,temperatureC=38) }
            if(model==DeviceModel.MCC) assertThrows(IllegalArgumentException::class.java) { client.startMotor(2,durationSeconds=1) }
            client.startMotor(3,MotorDirection.COUNTER_CLOCKWISE,60,if(model==DeviceModel.MCS)30 else 0)
            val frame=transport.sentFrames.last()
            if(model==DeviceModel.MCC) assertArrayEquals(MccCodec.encodeTx(org.blackstufflabs.monsieurcuisine.profiles.mcc.Operation.STANDARD,3,5,org.blackstufflabs.monsieurcuisine.profiles.mcc.Direction.COUNTER_CLOCKWISE),frame)
            else { val p=McsCodec.parse(frame).payload;assertEquals(6,p[8].toInt());assertEquals(1,p[9].toInt());assertEquals(1,p[11].toInt());assertEquals(30,p[19].toInt()) }
            client.close()
        }
    }
    @Test fun cachedReadsNeverInventQueriesAndReopenIsDisarmed() {
        for(model in DeviceModel.entries) {
            val transport=MockTransport(model);val client=MonsieurCuisineClient(model,transport);client.connect()
            assertNull(client.readState());assertNull(client.readTemperature())
            client.startMotor(5,temperatureC=60)
            transport.injectRawRx(rx(model));val state=client.receiveState()
            assertEquals(model,state.model)
            assertEquals(if(model==DeviceModel.MCC)SpeedUnit.RPM else SpeedUnit.RAW_MOTOR_LEVEL,state.observedSpeedUnit)
            val before=transport.sentFrames.size
            repeat(3) { assertEquals(state,client.readState());client.readTemperature();client.readErrors();client.readWeight() }
            assertEquals(before,transport.sentFrames.size)
            client.close();assertNull(client.readState());client.connect();assertNull(client.readState());assertEquals(before,transport.sentFrames.size)
            client.setDirection(MotorDirection.CLOCKWISE)
            val disarmed=transport.sentFrames.last()
            if(model==DeviceModel.MCC) assertEquals(0,disarmed[3].toInt())
            else assertEquals(0,McsCodec.parse(disarmed).payload[11].toInt())
            client.close()
        }
    }
    @Test fun duplicateConnectCannotResetAnActiveRequest() {
        for(model in DeviceModel.entries) {
            val transport=MockTransport(model);val client=MonsieurCuisineClient(model,transport);client.connect();client.startMotor(3)
            assertThrows(IOException::class.java) { client.connect() }
            client.setDirection(MotorDirection.CLOCKWISE)
            if(model==DeviceModel.MCC)assertEquals(3,transport.sentFrames.last()[5].toInt())
            else assertEquals(6,McsCodec.parse(transport.sentFrames.last()).payload[8].toInt())
            client.close()
        }
    }
    @Test fun disconnectedTransportHidesCachedTelemetryAndUnknownWeightUnitsStayUnknown() {
        for(model in DeviceModel.entries) {
            val transport=MockTransport(model);val client=MonsieurCuisineClient(model,transport);client.connect();transport.injectRawRx(rx(model))
            val observed=client.receiveState()
            if(model==DeviceModel.MCS) {
                assertEquals("2",observed.rawFields["weightUnit"]);assertNull(observed.weightGrams)
                assertNotNull(observed.rawFields["weightRaw"]);assertNotNull(observed.rawFields["decimalPlaces"])
            }
            transport.close();assertNull(client.readState());assertNull(client.readTemperature());client.close()
        }
    }
    @Test fun callbackLifecycleChangeCannotReturnStaleTelemetry() {
        for(model in DeviceModel.entries) {
            val transport=MockTransport(model);val client=MonsieurCuisineClient(model,transport);client.connect();transport.injectRawRx(rx(model))
            client.onFrame={ if(it.direction=="RX")client.close() }
            assertThrows(IOException::class.java) { client.receiveState() };assertNull(client.readState())
        }
    }
    @Test fun unsolicitedMcsTelemetryDoesNotCreateAQueryStorm() {
        val transport=MockTransport(DeviceModel.MCS);val client=MonsieurCuisineClient(DeviceModel.MCS,transport);client.connect()
        repeat(100) { transport.injectRawRx(rx(DeviceModel.MCS)) }
        repeat(100) { client.receiveState() }
        assertEquals("one initial query while draining already available observations",1,transport.sentFrames.size)
        client.close()
    }
    @Test fun realPushTrafficDrainsWithoutMatchingQueryGrowth() {
        ServerSocket(0,1,InetAddress.getByName("127.0.0.1")).use { server ->
            val sent=CountDownLatch(1);val release=CountDownLatch(1);val serverError=AtomicReference<Throwable?>()
            val worker=thread(isDaemon=true) {
                try { server.accept().use { peer ->
                    repeat(200) { peer.getOutputStream().write(rx(DeviceModel.MCS));peer.getOutputStream().flush();Thread.sleep(2) }
                    sent.countDown();release.await(2,TimeUnit.SECONDS)
                } } catch(error:Throwable) { serverError.set(error);sent.countDown() }
            }
            val client=MonsieurCuisineClient(DeviceModel.MCS,TwinTcpTransport(TwinEndpoint("127.0.0.1",server.localPort),DeviceModel.MCS))
            val queries=java.util.concurrent.atomic.AtomicInteger()
            client.onFrame={ if(it.direction=="TX")queries.incrementAndGet() }
            try {
                client.connect();val started=System.nanoTime()
                repeat(200) { assertEquals(DeviceModel.MCS,client.receiveState(2000).model) }
                val maximumQueries=((System.nanoTime()-started)/250_000_000L+2).toInt()
                assertTrue(sent.await(1,TimeUnit.SECONDS));assertTrue("polls remain bounded while200push frames drain",queries.get() in 1..maximumQueries)
                assertEquals(ConnectionState.CONNECTED,client.state);assertNull(serverError.get())
            } finally { release.countDown();client.close();worker.join(1000) }
        }
    }
    @Test fun mockCloseCancelsReceiveAndCopiesWrites() {
        for(model in DeviceModel.entries) {
            val transport=MockTransport(model);transport.connect()
            val original=WireProfiles.encode(model,RequestedOperation(),1);val expected=original.copyOf()
            transport.sendFrame(original);original.fill(0);assertArrayEquals(expected,transport.sentFrames.single())
            val done=CountDownLatch(1)
            val reader=thread(isDaemon=true) { try { transport.receiveFrame(10000);fail("closed read returned") } catch(_:IOException){} finally { done.countDown() } }
            transport.close();assertTrue(done.await(1,TimeUnit.SECONDS));reader.join(1000)
        }
    }
    @Test fun tcpBothModelsFragmentConcatTimeoutCancelAndExplicitReconnect() {
        for(model in DeviceModel.entries) {
            val complete=CountDownLatch(1)
            ServerSocket(0,1,InetAddress.getByName("127.0.0.1")).use { server ->
                val serverError=AtomicReference<Throwable?>()
                val worker=thread(isDaemon=true) {
                    try { server.accept().use { peer ->
                        val frame=rx(model);val output=peer.getOutputStream()
                        frame.forEach { output.write(byteArrayOf(it));output.flush() };output.write(frame+frame);output.flush()
                        peer.getInputStream().read()
                    } } catch(error:Throwable) { serverError.set(error) } finally { complete.countDown() }
                }
                val transport=TwinTcpTransport(TwinEndpoint("127.0.0.1",server.localPort),model);transport.connect()
                repeat(3) { assertArrayEquals(rx(model),transport.receiveFrame(1000)) }
                assertThrows(SocketTimeoutException::class.java) { transport.receiveFrame(40) };assertEquals(ConnectionState.CONNECTED,transport.state)
                val done=CountDownLatch(1)
                val reader=thread(isDaemon=true) { try { transport.receiveFrame(10000);fail("cancel did not wake receive") } catch(_:IOException){} finally { done.countDown() } }
                Thread.sleep(30);transport.close();assertTrue(done.await(1,TimeUnit.SECONDS));assertEquals(ConnectionState.DISCONNECTED,transport.state)
                reader.join(1000);assertTrue(complete.await(1,TimeUnit.SECONDS));worker.join(1000);assertNull(serverError.get())
            }
        }
    }
    @Test fun stopInvalidatesPendingStartsAndQueueIsBounded() {
        val dispatcher=CommandDispatcher(2);val entered=CountDownLatch(1);val release=CountDownLatch(1);val stopped=CountDownLatch(1)
        val actions=java.util.Collections.synchronizedList(mutableListOf<String>())
        try {
            assertTrue(dispatcher.submit { entered.countDown();release.await(2,TimeUnit.SECONDS);actions.add("in-flight") })
            assertTrue(entered.await(1,TimeUnit.SECONDS))
            assertTrue(dispatcher.submit { actions.add("old-start-1") });assertTrue(dispatcher.submit { actions.add("old-start-2") })
            assertFalse(dispatcher.submit { actions.add("overflow") })
            assertTrue(dispatcher.stop { actions.add("stop");stopped.countDown() });release.countDown()
            assertTrue(stopped.await(1,TimeUnit.SECONDS));assertEquals(listOf("in-flight","stop"),actions.toList())
        } finally { release.countDown();dispatcher.close() }
    }
}
