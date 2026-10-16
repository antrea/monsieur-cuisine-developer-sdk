package org.blackstufflabs.monsieurcuisine

import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

/** Bounded demo command queue. STOP/disconnect invalidate work that has not begun. */
class CommandDispatcher(maximumPending: Int=32): AutoCloseable {
    private val generation=AtomicLong()
    private val executor=ThreadPoolExecutor(1,1,0,TimeUnit.MILLISECONDS,ArrayBlockingQueue(maximumPending))
    init { require(maximumPending>0) }
    fun submit(action: ()->Unit): Boolean {
        val token=generation.get()
        return try {
            executor.execute { if(generation.get()==token) action() };true
        } catch(_: RejectedExecutionException) { false }
    }
    fun invalidate() { generation.incrementAndGet();executor.queue.clear() }
    fun stop(action: ()->Unit): Boolean { invalidate();return submit(action) }
    override fun close() { invalidate();executor.shutdownNow() }
}
