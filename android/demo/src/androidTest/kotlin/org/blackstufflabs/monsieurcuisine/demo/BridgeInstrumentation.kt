package org.blackstufflabs.monsieurcuisine.demo

import android.app.Activity
import android.app.Instrumentation
import android.content.Intent
import android.os.Bundle
import android.util.Log
import org.blackstufflabs.monsieurcuisine.*

/** Real Activity/control exercise. The host injects error 3 on AWAIT_HOST_ERROR. */
class BridgeInstrumentation: Instrumentation() {
    private var arguments=Bundle()
    override fun onCreate(arguments:Bundle?) { super.onCreate(arguments);this.arguments=arguments ?: Bundle();start() }
    override fun onStart() {
        val result=Bundle();var activity:MainActivity?=null
        fun stage(text:String) { Log.i("MCSDK_E2E",text);sendStatus(1,Bundle().apply { putString("stage",text) }) }
        try {
            arguments.getString("dataAction")?.let {
                result.putString("data", AppDataFixture.run(targetContext,it))
                result.putBoolean("passed",true)
                finish(Activity.RESULT_OK,result)
                return
            }
            val model=DeviceModel.valueOf(arguments.getString("model","MCC"))
            val number=arguments.getString("port",model.defaultPort.toString()).toInt()
            val current=startActivitySync(Intent(targetContext,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
            activity=current
            fun waitFor(description:String,condition:()->Boolean) {
                val deadline=System.nanoTime()+10_000_000_000L
                while(System.nanoTime()<deadline) { if(condition())return;Thread.sleep(60) }
                error("timeout: $description")
            }
            fun select(next:DeviceModel) {
                runOnMainSync { current.selectModelForTest(next) }
                waitFor("model selected") { current.selectedModelForTest()==next }
                check(current.disconnectedForTest()) { "model selection auto-connected" }
            }
            // Both directions exercise the visible selector and invalidate the old session.
            select(DeviceModel.MCS);select(DeviceModel.MCC);select(model);stage("UI_MODEL_SWITCHED_BOTH_DIRECTIONS")
            runOnMainSync { current.setPortForTest(number);current.clickConnectForTest() }
            waitFor("initial observed state") { current.cachedStateForTest()?.let { it.model==model && it.observedSpeedValue==0.0 }==true };stage("CONNECTED")
            runOnMainSync { current.clickStartForTest(3,60,if(model==DeviceModel.MCS)30 else 0) }
            waitFor("motor starts") { current.cachedStateForTest()?.observedSpeedValue?.let { it>0 }==true };stage("STARTED")
            runOnMainSync { current.clickStartForTest(5,60,if(model==DeviceModel.MCS)30 else 0) }
            waitFor("speed changes") { current.cachedStateForTest()?.observedSpeedValue?.let { it>=if(model==DeviceModel.MCC)1000 else 8 }==true };stage("SPEED_CHANGED")
            check(current.cachedStateForTest()?.rawHex?.isNotBlank()==true);stage("TELEMETRY")
            runOnMainSync { current.clickStopForTest() }
            waitFor("motor stops") { current.cachedStateForTest()?.observedSpeedValue==0.0 };stage("STOPPED")
            stage("AWAIT_HOST_ERROR")
            waitFor("injected motor error") { current.cachedStateForTest()?.errorCode==3 };stage("ERROR_OBSERVED")
            runOnMainSync { current.clickConnectForTest() };waitFor("disconnect") { current.disconnectedForTest() };stage("DISCONNECTED")
            runOnMainSync { current.clickConnectForTest() }
            waitFor("reconnected disarmed") { current.cachedStateForTest()?.observedSpeedValue==0.0 };stage("RECONNECTED_DISARMED")
            runOnMainSync { current.selectModelForTest(if(model==DeviceModel.MCC)DeviceModel.MCS else DeviceModel.MCC) }
            waitFor("model switch disconnects") { current.disconnectedForTest() };stage("CONNECTED_MODEL_SWITCH_DISARMED")
            runOnMainSync { callActivityOnStop(current) }
            check(current.disconnectedForTest());stage("BACKGROUND_DISCONNECTED")
            result.putBoolean("passed",true);result.putString("detail","Activity controls, both selector directions, binary telemetry, STOP, fault, reconnect and background lifecycle passed for $model")
            finish(Activity.RESULT_OK,result)
        } catch(error:Throwable) {
            result.putBoolean("passed",false);result.putString("detail",error.toString());finish(Activity.RESULT_CANCELED,result)
        } finally { activity?.let { runOnMainSync { it.disconnect() } } }
    }
}
