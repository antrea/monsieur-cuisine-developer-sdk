package org.blackstufflabs.monsieurcuisine.demo

import android.app.Activity
import android.graphics.Typeface
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.widget.*
import org.blackstufflabs.monsieurcuisine.*
import java.net.SocketTimeoutException
import java.util.concurrent.Executors
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference

/** One native UI and lifecycle for both explicitly selected binary protocols. */
class MainActivity: Activity() {
    private val main=Handler(Looper.getMainLooper())
    private val generation=AtomicLong()
    private val commands=CommandDispatcher()
    private val receiver=Executors.newSingleThreadExecutor()
    private val active=AtomicReference<MonsieurCuisineClient?>()
    private val pendingFrames=ArrayBlockingQueue<Pair<Long,String>>(64)
    private val pendingTelemetry=AtomicReference<Pair<Long,DeviceState>?>()
    private val displayPosted=AtomicBoolean()
    @Volatile private var destroyed=false
    @Volatile private var connecting=false
    @Volatile private var selectedModel=DeviceModel.MCC
    private lateinit var models: Spinner;private lateinit var speeds: Spinner
    private lateinit var directions: Spinner;private lateinit var temperatures: Spinner
    private lateinit var port: EditText;private lateinit var duration: EditText
    private lateinit var status: TextView;private lateinit var telemetry: TextView;private lateinit var monitor: TextView
    private lateinit var connection: Button;private lateinit var start: Button;private lateinit var stop: Button
    private lateinit var temperatureAdapter: ArrayAdapter<String>
    private val lines=ArrayDeque<String>()
    private fun post(token:Long,action:()->Unit) { main.post { if(!destroyed && generation.get()==token) action() } }
    private fun line(text:String) {
        lines.addLast(text);while(lines.size>32)lines.removeFirst();monitor.text=lines.joinToString("\n")
    }
    private fun scheduleDisplay() {
        if(destroyed || !displayPosted.compareAndSet(false,true))return
        main.postDelayed({
            displayPosted.set(false)
            if(!destroyed) {
                val token=generation.get()
                pendingTelemetry.getAndSet(null)?.takeIf { it.first==token }?.second?.let { state ->
                    telemetry.text="${state.model}: ${state.observedSpeedValue} ${state.observedSpeedUnit}\n"+
                        "${state.direction} · ${state.actualTemperatureC} / ${state.targetTemperatureC} °C\n"+
                        "Weight ${state.weightGrams?.let { "$it g" } ?: "unknown unit ${state.rawFields["weightUnit"]}"} · Lid ${if(state.lidOpen)"OPEN" else "closed"}\n"+
                        "Error ${state.errorCode}: ${state.errorName} · Firmware ${state.firmware}"
                }
                val updates=mutableListOf<Pair<Long,String>>()
                pendingFrames.drainTo(updates)
                updates.filter { it.first==token }.forEach { lines.addLast(it.second) }
                while(lines.size>32)lines.removeFirst()
                if(updates.isNotEmpty())monitor.text=lines.joinToString("\n")
            }
        },50)
    }
    private fun queueFrame(token:Long,text:String) {
        if(generation.get()!=token || destroyed)return
        if(!pendingFrames.offer(token to text)) { pendingFrames.poll();pendingFrames.offer(token to text) }
        scheduleDisplay()
    }
    private fun connectedUi(connected:Boolean,message:String) {
        status.text=message;connection.text=if(connected || connecting) "Disconnect" else "Connect"
        start.isEnabled=connected;stop.isEnabled=connected;port.isEnabled=!connected && !connecting
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val content=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL;setPadding(24,36,24,24) }
        setContentView(ScrollView(this).apply { addView(content) })
        fun label(text:String,size:Float=15f)=TextView(this).apply { this.text=text;textSize=size;content.addView(this) }
        fun spinner(title:String,entries:List<String>):Spinner {
            label(title)
            return Spinner(this).apply { adapter=ArrayAdapter(this@MainActivity,android.R.layout.simple_spinner_dropdown_item,entries);content.addView(this) }
        }
        label("Monsieur Cuisine Developer SDK",23f)
        label("BlackStuff Labs · Synthetic PowerBoard · No hardware",12f)
        models=spinner("Device model",DeviceModel.entries.map { it.name })
        label("Android emulator host: 10.0.2.2 · original raw binary frames",12f)
        val row=LinearLayout(this)
        port=EditText(this).apply { setText(selectedModel.defaultPort.toString());hint="TCP port";inputType=InputType.TYPE_CLASS_NUMBER }
        row.addView(port,LinearLayout.LayoutParams(0,-2,1f))
        connection=Button(this).apply { text="Connect";setOnClickListener { if(active.get()!=null || connecting) disconnect("Disconnected") else connectTwin() } }
        row.addView(connection);content.addView(row)
        status=label("Disconnected — select a model and connect")
        speeds=spinner("Requested UI speed",(0..10).map(Int::toString)).apply { setSelection(3) }
        directions=spinner("Direction",listOf("Counter-clockwise","Clockwise"))
        label("Temperature target °C")
        temperatureAdapter=ArrayAdapter(this,android.R.layout.simple_spinner_dropdown_item,mutableListOf<String>())
        temperatures=Spinner(this).apply { adapter=temperatureAdapter;content.addView(this) }
        label("Duration seconds (MCS only; MCC has no timer field)",12f)
        duration=EditText(this).apply { setText("0");inputType=InputType.TYPE_CLASS_NUMBER;content.addView(this) }
        val controls=LinearLayout(this)
        start=Button(this).apply { text="START / apply";isEnabled=false;setOnClickListener {
            val speed=speeds.selectedItemPosition
            val direction=if(directions.selectedItemPosition==0)MotorDirection.COUNTER_CLOCKWISE else MotorDirection.CLOCKWISE
            val heat=temperatureAdapter.getItem(temperatures.selectedItemPosition)?.toInt() ?: 0
            val seconds=duration.text.toString().toIntOrNull()
            if(seconds==null) { status.text="Duration must be an integer";return@setOnClickListener }
            submit { it.startMotor(speed,direction,heat,seconds) }
        } }
        stop=Button(this).apply { text="STOP";isEnabled=false;setOnClickListener { submit(stopFirst=true) { it.stopMotor() } } }
        controls.addView(start,LinearLayout.LayoutParams(0,-2,2f));controls.addView(stop,LinearLayout.LayoutParams(0,-2,1f));content.addView(controls)
        telemetry=label("No current telemetry")
        label("TX / RX · Observations are not command acknowledgments",12f)
        monitor=label("",10f).apply { typeface=Typeface.MONOSPACE;setTextIsSelectable(true) }
        label("Simulation connection is enabled only in debug builds. Synthetic trajectories do not certify an appliance.",11f)
        models.onItemSelectedListener=object: android.widget.AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent:android.widget.AdapterView<*>?) {}
            override fun onItemSelected(parent:android.widget.AdapterView<*>?,view:android.view.View?,position:Int,id:Long) {
                val next=DeviceModel.entries[position]
                if(next!=selectedModel) { disconnect("Model changed — explicit Connect required");selectedModel=next;port.setText(next.defaultPort.toString()) }
                refreshCapabilities()
            }
        }
        refreshCapabilities()
        if(!BuildConfig.DEBUG) connectedUi(false,"Use a debug build for the simulation connection")
    }
    private fun refreshCapabilities() {
        val allowed=if(selectedModel==DeviceModel.MCC)
            org.blackstufflabs.monsieurcuisine.profiles.mcc.MccCodec.temperatureLevels
            else org.blackstufflabs.monsieurcuisine.profiles.mcs.McsCodec.temperatures
        temperatureAdapter.clear();temperatureAdapter.addAll(allowed.map(Int::toString));temperatureAdapter.notifyDataSetChanged();temperatures.setSelection(0)
        duration.isEnabled=selectedModel==DeviceModel.MCS;duration.setText("0")
    }
    private fun connectTwin() {
        if(!BuildConfig.DEBUG) { status.text="Simulation is disabled in release builds";return }
        val number=port.text.toString().toIntOrNull()
        if(number==null || number !in 1..65535) { status.text="Port must be 1..65535";return }
        val token=generation.incrementAndGet();val model=selectedModel
        val client=MonsieurCuisineClient(model,TwinTcpTransport(TwinEndpoint(port=number),model))
        client.onFrame={event -> queueFrame(token,"${event.model} ${event.direction} ${event.hex}") }
        active.set(client);connecting=true;connectedUi(false,"Connecting to $model on 10.0.2.2:$number")
        if(!commands.submit {
            try {
                if(generation.get()!=token) return@submit
                client.connect()
                if(generation.get()!=token) { client.close();return@submit }
                post(token) { connecting=false;connectedUi(true,"Connected to $model · simulation") }
                receiver.execute { receive(client,token) }
            } catch(error:Exception) {
                runCatching { client.close() };active.compareAndSet(client,null)
                post(token) { connecting=false;connectedUi(false,"Connection error: ${error.message}") }
            }
        }) { active.compareAndSet(client,null);connecting=false;connectedUi(false,"Command queue full") }
    }
    private fun submit(stopFirst:Boolean=false,action:(MonsieurCuisineClient)->Unit) {
        val client=active.get() ?: return
        val token=generation.get()
        val work:()->Unit={
            if(generation.get()==token && active.get()===client) {
                try { action(client) } catch(error:Exception) { post(token) { line("Command error: ${error.message}") } }
            }
        }
        val queued=if(stopFirst)commands.stop(work) else commands.submit(work)
        if(!queued)line("Command queue full; no command scheduled")
    }
    private fun receive(client:MonsieurCuisineClient,token:Long) {
        try {
            while(generation.get()==token && client.state==ConnectionState.CONNECTED) {
                try {
                    val state=client.receiveState()
                    if(generation.get()==token) { pendingTelemetry.set(token to state);scheduleDisplay() }
                } catch(_:SocketTimeoutException) { post(token) { line("Telemetry timeout; no command retry") } }
            }
        } catch(error:Exception) { post(token) { line("Connection ended: ${error.message}") } }
        finally {
            runCatching { client.close() };active.compareAndSet(client,null)
            post(token) { connecting=false;connectedUi(false,"Disconnected");telemetry.text="No current telemetry" }
        }
    }
    fun disconnect(message:String="Disconnected") {
        generation.incrementAndGet();commands.invalidate();connecting=false
        pendingFrames.clear();pendingTelemetry.set(null)
        val old=active.getAndSet(null)
        runCatching { old?.close() }
        if(!destroyed && ::status.isInitialized) { connectedUi(false,message);telemetry.text="No current telemetry" }
    }
    // Instrumentation drives the same visible controls. It does not construct a second SDK client.
    fun selectModelForTest(model:DeviceModel) { models.setSelection(model.ordinal) }
    fun selectedModelForTest()=selectedModel
    fun disconnectedForTest()=active.get()==null && !connecting
    fun setPortForTest(number:Int) { port.setText(number.toString()) }
    fun clickConnectForTest() { connection.performClick() }
    fun clickStartForTest(speed:Int,temperature:Int,seconds:Int) {
        speeds.setSelection(speed);temperatures.setSelection(temperatureAdapter.getPosition(temperature.toString()));duration.setText(seconds.toString());start.performClick()
    }
    fun clickStopForTest() { stop.performClick() }
    fun cachedStateForTest()=active.get()?.readState()
    override fun onStop() { disconnect("Disconnected on app background");super.onStop() }
    override fun onDestroy() { destroyed=true;disconnect();commands.close();receiver.shutdownNow();main.removeCallbacksAndMessages(null);super.onDestroy() }
}
