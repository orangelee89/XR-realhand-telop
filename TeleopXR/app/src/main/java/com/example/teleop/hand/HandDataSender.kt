package com.example.teleop.hand

import android.util.Log
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

/**
 * HandDataSender - Sends hand tracking data to ROS2 via UDP
 *
 * This class handles the network communication between the Android XR device
 * and the Ubuntu computer running ROS2 and LinkerHand SDK.
 *
 * Data Format (JSON):
 * {
 *   "type": "hand_pose",
 *   "hand": "left" | "right",
 *   "timestamp": 1234567890123,
 *   "o6_values": [0, 128, 255, 200, 150, 100],  // 6 values (0-255)
 *   "finger_bend": [0.0, 0.5, 1.0, 0.8, 0.6, 0.4]  // 6 normalized values
 * }
 */
class HandDataSender(
    private val host: String = "192.168.1.100",  // Ubuntu computer IP address
    private val port: Int = 5000                   // UDP port
) {
    companion object {
        private const val TAG = "HandDataSender"
        private const val SEND_INTERVAL_MS = 33L  // ~30 Hz send rate
    }

    private var socket: DatagramSocket? = null
    private var sendJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    // Latest data to send (updated from hand tracking)
    @Volatile
    private var latestLeftHandData: IntArray? = null

    @Volatile
    private var latestRightHandData: IntArray? = null

    @Volatile
    private var isRunning = false

    /**
     * Start the UDP sender
     * Creates socket and begins sending loop
     */
    fun start() {
        if (isRunning) {
            Log.w(TAG, "Sender already running")
            return
        }

        try {
            socket = DatagramSocket()
            isRunning = true
            startSendLoop()
            Log.i(TAG, "UDP sender started - target: $host:$port")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start sender: ${e.message}")
        }
    }

    /**
     * Stop the UDP sender
     * Cancels send loop and closes socket
     */
    fun stop() {
        isRunning = false
        sendJob?.cancel()
        sendJob = null

        socket?.close()
        socket = null

        Log.i(TAG, "UDP sender stopped")
    }

    /**
     * Update left hand data to be sent
     *
     * @param o6Values Array of 6 O6 control values (0-255)
     */
    fun updateLeftHand(o6Values: IntArray?) {
        latestLeftHandData = o6Values
    }

    /**
     * Update right hand data to be sent
     *
     * @param o6Values Array of 6 O6 control values (0-255)
     */
    fun updateRightHand(o6Values: IntArray?) {
        latestRightHandData = o6Values
    }

    /**
     * Start the periodic send loop
     * Sends latest hand data at fixed interval
     */
    private fun startSendLoop() {
        sendJob = scope.launch {
            while (isRunning) {
                try {
                    // Send left hand data if available
                    latestLeftHandData?.let { data ->
                        sendHandData("left", data)
                    }

                    // Send right hand data if available
                    latestRightHandData?.let { data ->
                        sendHandData("right", data)
                    }

                    delay(SEND_INTERVAL_MS)
                } catch (e: CancellationException) {
                    break
                } catch (e: Exception) {
                    Log.e(TAG, "Send loop error: ${e.message}")
                    delay(100)  // Brief delay before retry
                }
            }
        }
    }

    /**
     * Send hand data packet via UDP
     *
     * @param hand "left" or "right"
     * @param o6Values Array of 6 control values (0-255)
     */
    private suspend fun sendHandData(hand: String, o6Values: IntArray) {
        withContext(Dispatchers.IO) {
            try {
                val json = createJsonPayload(hand, o6Values)
                val data = json.toByteArray(Charsets.UTF_8)

                val address = InetAddress.getByName(host)
                val packet = DatagramPacket(data, data.size, address, port)

                socket?.send(packet)

                Log.v(TAG, "Sent $hand hand: ${o6Values.joinToString(",")}")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send $hand hand data: ${e.message}")
            }
        }
    }

    /**
     * Create JSON payload for hand data
     *
     * @param hand "left" or "right"
     * @param o6Values Array of 6 control values (0-255)
     * @return JSON string
     */
    private fun createJsonPayload(hand: String, o6Values: IntArray): String {
        val json = JSONObject().apply {
            put("type", "hand_pose")
            put("hand", hand)
            put("timestamp", System.currentTimeMillis())

            // O6 control values (0-255) - use JSONArray for proper JSON format
            val o6Array = JSONArray()
            o6Values.forEach { o6Array.put(it) }
            put("o6_values", o6Array)

            // Normalized values (0.0-1.0) for flexibility
            val bendArray = JSONArray()
            o6Values.forEach { bendArray.put(it / 255.0) }
            put("finger_bend", bendArray)
        }
        return json.toString()
    }

    /**
     * Send a single hand data packet immediately (non-periodic)
     * Useful for testing or one-off sends
     *
     * @param hand "left" or "right"
     * @param o6Values Array of 6 control values (0-255)
     */
    fun sendImmediate(hand: String, o6Values: IntArray) {
        scope.launch {
            sendHandData(hand, o6Values)
        }
    }

    /**
     * Check if sender is currently running
     */
    fun isRunning(): Boolean = isRunning

    /**
     * Update target host address
     * Must call stop() and start() to apply changes
     *
     * @param newHost New IP address
     */
    fun setHost(newHost: String): HandDataSender {
        return HandDataSender(newHost, port)
    }

    /**
     * Update target port
     * Must call stop() and start() to apply changes
     *
     * @param newPort New port number
     */
    fun setPort(newPort: Int): HandDataSender {
        return HandDataSender(host, newPort)
    }
}
