package com.example.teleop.hand

import android.util.Log
import androidx.xr.arcore.Hand
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.StateFlow

/**
 * TeleopManager - Main controller for hand tracking teleoperation
 *
 * This class integrates:
 * - Hand pose conversion (26 joints -> 6 O6 values)
 * - Network transmission (UDP to ROS2)
 * - Data flow management
 *
 * Usage:
 *   val manager = TeleopManager("192.168.1.100", 5000)
 *   manager.start()
 *   // When hand state updates:
 *   manager.onLeftHandUpdate(handState)
 *   // When done:
 *   manager.stop()
 */
class TeleopManager(
    host: String = "192.168.1.100",
    port: Int = 5000
) {
    companion object {
        private const val TAG = "TeleopManager"
    }

    private val converter = HandPoseConverter()
    private val sender = HandDataSender(host, port)
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())

    @Volatile
    private var isRunning = false

    /**
     * Start the teleoperation system
     */
    fun start() {
        if (isRunning) {
            Log.w(TAG, "TeleopManager already running")
            return
        }

        sender.start()
        isRunning = true
        Log.i(TAG, "TeleopManager started")
    }

    /**
     * Stop the teleoperation system
     */
    fun stop() {
        isRunning = false
        sender.stop()
        scope.cancel()
        Log.i(TAG, "TeleopManager stopped")
    }

    /**
     * Process and send left hand state
     *
     * @param handState Left hand state from Android XR
     */
    fun onLeftHandUpdate(handState: Hand.State?) {
        if (!isRunning) return

        scope.launch {
            val o6Values = converter.convertToO6(handState)
            if (o6Values != null) {
                sender.updateLeftHand(o6Values)
                Log.d(TAG, "Left hand updated: ${o6Values.joinToString(",")}")
            }
        }
    }

    /**
     * Process and send right hand state
     *
     * @param handState Right hand state from Android XR
     */
    fun onRightHandUpdate(handState: Hand.State?) {
        if (!isRunning) return

        scope.launch {
            val o6Values = converter.convertToO6(handState)
            if (o6Values != null) {
                sender.updateRightHand(o6Values)
                Log.d(TAG, "Right hand updated: ${o6Values.joinToString(",")}")
            }
        }
    }

    /**
     * Collect from StateFlow and automatically process updates
     * Use this to connect directly to TeleopViewModel's hand state flows
     *
     * @param leftHandFlow StateFlow of left hand state
     * @param rightHandFlow StateFlow of right hand state
     */
    fun collectHandStates(
        leftHandFlow: StateFlow<Hand.State?>,
        rightHandFlow: StateFlow<Hand.State?>
    ) {
        // Collect left hand updates
        scope.launch {
            leftHandFlow.collect { state ->
                onLeftHandUpdate(state)
            }
        }

        // Collect right hand updates
        scope.launch {
            rightHandFlow.collect { state ->
                onRightHandUpdate(state)
            }
        }

        Log.i(TAG, "Started collecting hand state flows")
    }

    /**
     * Check if manager is running
     */
    fun isRunning(): Boolean = isRunning

    /**
     * Get the hand pose converter for direct access
     */
    fun getConverter(): HandPoseConverter = converter

    /**
     * Get the data sender for direct access
     */
    fun getSender(): HandDataSender = sender
}
