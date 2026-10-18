package org.blackstufflabs.monsieurcuisine

import org.junit.Assert.*
import org.junit.Test

class HostPolicyTest {
    @Test fun stopRetainsTheRequestedDirection() {
        val transport=MockTransport(DeviceModel.MCC)
        val client=MonsieurCuisineClient(DeviceModel.MCC,transport)
        client.connect()
        client.startMotor(2,MotorDirection.COUNTER_CLOCKWISE)
        client.stopMotor()
        assertEquals(0,transport.sentFrames.last()[3].toInt())
        assertEquals(1,transport.sentFrames.last()[11].toInt())
        client.close()
    }
    @Test fun clockwiseDefaultMinimumAndHeatedReverseCaps() {
        val transport=MockTransport(DeviceModel.MCC)
        val client=MonsieurCuisineClient(DeviceModel.MCC,transport)
        client.connect()
        client.startMotor(9)
        assertEquals(0,transport.sentFrames.last()[11].toInt()) // wire CW
        assertEquals(9,transport.sentFrames.last()[5].toInt())
        client.startMotor(9,temperatureC=60)
        assertEquals(3,transport.sentFrames.last()[5].toInt())
        client.startMotor(9,MotorDirection.COUNTER_CLOCKWISE)
        assertEquals(3,transport.sentFrames.last()[5].toInt())
        client.startMotor(0,temperatureC=60)
        assertEquals(1,transport.sentFrames.last()[5].toInt())
        client.close()
    }

    @Test fun strictPolicyRefusesWithoutSending() {
        // Preserve the original two-argument constructor for Java consumers.
        assertNotNull(MonsieurCuisineClient::class.java.getConstructor(DeviceModel::class.java,Transport::class.java))
        val transport=MockTransport(DeviceModel.MCC)
        val client=MonsieurCuisineClient(DeviceModel.MCC,transport,HostPolicyMode.STRICT)
        client.connect()
        assertThrows(IllegalArgumentException::class.java) { client.startMotor(10,temperatureC=60) }
        assertTrue(transport.sentFrames.isEmpty())
        client.startMotor(2)
        assertEquals(1,transport.sentFrames.size)
        client.close()
    }
}
