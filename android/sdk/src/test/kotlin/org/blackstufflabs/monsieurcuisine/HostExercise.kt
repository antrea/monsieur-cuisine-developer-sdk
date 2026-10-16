package org.blackstufflabs.monsieurcuisine

/** Private harness entry point, packaged in host-tests only. Uses the public facade. */
object HostExercise {
    @JvmStatic fun main(args: Array<String>) {
        val model=DeviceModel.valueOf(args[0])
        val port=args.getOrNull(1)?.toInt() ?: model.defaultPort
        val client=MonsieurCuisineClient(model,TwinTcpTransport(TwinEndpoint("127.0.0.1",port),model))
        fun stage(value:String) { println(value);System.out.flush() }
        fun await(description:String,match:(DeviceState)->Boolean): DeviceState {
            val end=System.nanoTime()+8_000_000_000L
            while(System.nanoTime()<end) {
                val observed=client.receiveState()
                if(match(observed)) return observed
                Thread.sleep(60)
            }
            error("timeout: $description")
        }
        try {
            client.connect();await("initial telemetry") { it.observedSpeedValue==0.0 };stage("CONNECTED")
            client.startMotor(3,temperatureC=60,durationSeconds=if(model==DeviceModel.MCS)30 else 0)
            await("motor starts") { it.observedSpeedValue>0 };stage("STARTED")
            client.startMotor(5,temperatureC=60,durationSeconds=if(model==DeviceModel.MCS)30 else 0)
            await("speed changes") { if(model==DeviceModel.MCC) it.observedSpeedValue>=1000 else it.observedSpeedValue>=8 };stage("SPEED_CHANGED")
            check(client.readState()!=null);stage("TELEMETRY")
            client.stopMotor();await("motor stops") { it.observedSpeedValue==0.0 };stage("STOPPED")
            stage("AWAIT_HOST_ERROR")
            await("injected motor error") { it.errorCode==3 };stage("ERROR_OBSERVED")
            client.disconnect();check(client.readState()==null);stage("DISCONNECTED")
            client.connect();await("reconnect disarmed") { it.observedSpeedValue==0.0 };stage("RECONNECTED_DISARMED")
        } finally { client.close() }
    }
}
