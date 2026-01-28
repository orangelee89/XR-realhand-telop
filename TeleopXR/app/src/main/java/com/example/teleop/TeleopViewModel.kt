package com.example.teleop

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.xr.arcore.Hand
import androidx.xr.arcore.RenderViewpoint
import androidx.xr.runtime.Session
import androidx.xr.runtime.math.Pose
import com.example.teleop.hand.TeleopManager
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * TeleopViewModel - ViewModel for hand tracking and teleoperation
 *
 * This ViewModel:
 * 1. Collects hand tracking data from Android XR SDK
 * 2. Exposes hand state as StateFlow for UI
 * 3. Sends hand data to ROS2 via TeleopManager
 *
 * Hand tracking data flow:
 *   Android XR SDK -> TeleopViewModel -> TeleopManager -> UDP -> ROS2 -> LinkerHand O6
 *
 * Head tracking note:
 *   The SDK declared head pose API but didn't implement it yet.
 *   Using left eye's pose (RenderViewpoint.left) as workaround.
 */
class TeleopViewModel: ViewModel() {

    // Hand state flows - exposed for UI observation
    private val _leftHand = MutableStateFlow<Hand.State?>(null)
    private val _rightHand = MutableStateFlow<Hand.State?>(null)
    private val _headPose = MutableStateFlow<Pose?>(null)

    val leftHand = _leftHand.asStateFlow()
    val rightHand = _rightHand.asStateFlow()
    val headPose = _headPose.asStateFlow()

    // Connection status
    private val _isConnected = MutableStateFlow(false)
    val isConnected = _isConnected.asStateFlow()

    // Polling job for hand tracking
    private var pollingJob: Job? = null

    // Teleop manager for sending data to ROS2
    // TODO: Make host configurable via settings UI
    private var teleopManager: TeleopManager? = null

    // Configuration - change these for your setup
    private var targetHost = "192.168.1.100"  // Ubuntu computer IP
    private var targetPort = 5000              // UDP port

    init {
        Log.d(LOGCAT_TAG, "TeleopViewModel initialized")
    }

    /**
     * Start hand tracking and teleoperation
     *
     * @param session Android XR session
     */
    fun start(session: Session) {
        if (pollingJob?.isActive == true) {
            Log.i(LOGCAT_TAG, "Polling job is already active, not starting now")
            return
        }
        Log.d(LOGCAT_TAG, "Starting hand tracking and teleoperation")

        // Initialize and start teleop manager
        teleopManager = TeleopManager(targetHost, targetPort)
        teleopManager?.start()
        _isConnected.value = true

        // Start hand tracking collection
        pollingJob = viewModelScope.launch {

            // Collect left hand state
            launch {
                Hand.left(session)?.state?.collect { handState ->
                    _leftHand.value = handState

                    // Send to ROS2 via teleop manager
                    teleopManager?.onLeftHandUpdate(handState)

                    Log.d(LOGCAT_TAG, "Left hand updated")
                }
            }

            // Collect right hand state
            launch {
                Hand.right(session)?.state?.collect { handState ->
                    _rightHand.value = handState

                    // Send to ROS2 via teleop manager
                    teleopManager?.onRightHandUpdate(handState)

                    Log.d(LOGCAT_TAG, "Right hand updated")
                }
            }

            // Collect head pose (using left eye as workaround)
            // Note: SDK declared head pose but didn't implement it
            launch {
                val headViewPoint = RenderViewpoint.left(session)
                Log.d(LOGCAT_TAG, "Head tracking mode: ${session.config.headTracking}")
                Log.i(LOGCAT_TAG, "Using left eye viewpoint for head pose: $headViewPoint")

                headViewPoint?.state?.collect { state ->
                    val fov = state.fieldOfView
                    val pose = state.pose
                    _headPose.value = pose
                    Log.v(LOGCAT_TAG, "Head pose: $pose, FOV: $fov")
                }
            }
        }

        Log.i(LOGCAT_TAG, "Hand tracking and teleoperation started")
    }

    /**
     * Stop hand tracking and teleoperation
     */
    fun stop() {
        Log.d(LOGCAT_TAG, "Stopping hand tracking and teleoperation")

        // Cancel polling job
        pollingJob?.cancel()
        pollingJob = null

        // Stop teleop manager
        teleopManager?.stop()
        teleopManager = null

        // Clear state
        _leftHand.value = null
        _rightHand.value = null
        _headPose.value = null
        _isConnected.value = false

        Log.i(LOGCAT_TAG, "Hand tracking and teleoperation stopped")
    }

    /**
     * Configure target host for ROS2 communication
     *
     * @param host IP address of Ubuntu computer running ROS2
     */
    fun setTargetHost(host: String) {
        targetHost = host
        Log.i(LOGCAT_TAG, "Target host set to: $host")

        // Restart teleop manager if running
        if (teleopManager?.isRunning() == true) {
            teleopManager?.stop()
            teleopManager = TeleopManager(targetHost, targetPort)
            teleopManager?.start()
        }
    }

    /**
     * Configure target port for ROS2 communication
     *
     * @param port UDP port number
     */
    fun setTargetPort(port: Int) {
        targetPort = port
        Log.i(LOGCAT_TAG, "Target port set to: $port")

        // Restart teleop manager if running
        if (teleopManager?.isRunning() == true) {
            teleopManager?.stop()
            teleopManager = TeleopManager(targetHost, targetPort)
            teleopManager?.start()
        }
    }

    /**
     * Get current target host
     */
    fun getTargetHost(): String = targetHost

    /**
     * Get current target port
     */
    fun getTargetPort(): Int = targetPort

    /**
     * Clean up when ViewModel is cleared
     */
    override fun onCleared() {
        super.onCleared()
        stop()
        Log.d(LOGCAT_TAG, "TeleopViewModel cleared")
    }

    companion object {
        private const val LOGCAT_TAG = "TeleopViewModel"
    }
}
