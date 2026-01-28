package com.example.teleop.hand

import android.util.Log
import androidx.xr.arcore.Hand
import androidx.xr.arcore.HandJointType
import androidx.xr.runtime.math.Vector3
import kotlin.math.sqrt
import kotlin.math.atan2
import kotlin.math.abs

/**
 * HandPoseConverter - Converts Android XR hand tracking data to LinkerHand O6 control values
 *
 * Android XR provides 26 hand joint positions.
 * LinkerHand O6 has 6 active degrees of freedom:
 *   - position[0]: Thumb bend (大拇指弯曲)
 *   - position[1]: Thumb yaw/lateral movement (大拇指横摆)
 *   - position[2]: Index finger bend (食指弯曲)
 *   - position[3]: Middle finger bend (中指弯曲)
 *   - position[4]: Ring finger bend (无名指弯曲)
 *   - position[5]: Pinky finger bend (小拇指弯曲)
 *
 * This class filters and converts 26 joints -> 6 control values (0-255)
 */
class HandPoseConverter {

    companion object {
        private const val TAG = "HandPoseConverter"

        // Maximum distance (meters) from palm to fingertip when fully extended
        // These values may need calibration based on actual hand size
        private const val THUMB_MAX_DIST = 0.08f
        private const val INDEX_MAX_DIST = 0.10f
        private const val MIDDLE_MAX_DIST = 0.11f
        private const val RING_MAX_DIST = 0.10f
        private const val PINKY_MAX_DIST = 0.08f

        // Thumb yaw range (meters) for lateral movement calculation
        private const val THUMB_YAW_RANGE = 0.06f
    }

    /**
     * Convert Hand.State from Android XR to O6 control values
     *
     * @param handState The hand state from Android XR hand tracking
     * @return IntArray of 6 values (0-255) for O6 control, or null if hand not detected
     */
    fun convertToO6(handState: Hand.State?): IntArray? {
        if (handState == null) {
            Log.d(TAG, "Hand state is null")
            return null
        }

        val joints = handState.handJoints

        // Get key joint positions
        val palm = joints[HandJointType.HAND_JOINT_TYPE_PALM]?.translation
        val wrist = joints[HandJointType.HAND_JOINT_TYPE_WRIST]?.translation

        // Thumb joints
        val thumbTip = joints[HandJointType.HAND_JOINT_TYPE_THUMB_TIP]?.translation
        val thumbDistal = joints[HandJointType.HAND_JOINT_TYPE_THUMB_DISTAL]?.translation
        val thumbProximal = joints[HandJointType.HAND_JOINT_TYPE_THUMB_PROXIMAL]?.translation
        val thumbMetacarpal = joints[HandJointType.HAND_JOINT_TYPE_THUMB_METACARPAL]?.translation

        // Other finger tips
        val indexTip = joints[HandJointType.HAND_JOINT_TYPE_INDEX_TIP]?.translation
        val middleTip = joints[HandJointType.HAND_JOINT_TYPE_MIDDLE_TIP]?.translation
        val ringTip = joints[HandJointType.HAND_JOINT_TYPE_RING_TIP]?.translation
        val pinkyTip = joints[HandJointType.HAND_JOINT_TYPE_LITTLE_TIP]?.translation

        // Validate required joints are present
        if (palm == null || wrist == null) {
            Log.w(TAG, "Palm or wrist not detected")
            return null
        }

        // Calculate bend values for each finger (0.0 = straight, 1.0 = fully bent)
        val thumbBend = calculateFingerBend(palm, thumbTip, THUMB_MAX_DIST)
        val thumbYaw = calculateThumbYaw(wrist, palm, thumbMetacarpal, thumbTip)
        val indexBend = calculateFingerBend(palm, indexTip, INDEX_MAX_DIST)
        val middleBend = calculateFingerBend(palm, middleTip, MIDDLE_MAX_DIST)
        val ringBend = calculateFingerBend(palm, ringTip, RING_MAX_DIST)
        val pinkyBend = calculateFingerBend(palm, pinkyTip, PINKY_MAX_DIST)

        // Convert normalized values (0.0-1.0) to O6 range (0-255)
        val result = intArrayOf(
            normalizedToO6(thumbBend),
            normalizedToO6(thumbYaw),
            normalizedToO6(indexBend),
            normalizedToO6(middleBend),
            normalizedToO6(ringBend),
            normalizedToO6(pinkyBend)
        )

        Log.d(TAG, "O6 values: ${result.joinToString(", ")}")
        return result
    }

    /**
     * Calculate finger bend based on distance from palm to fingertip
     *
     * When finger is straight: tip is far from palm -> bend = 0
     * When finger is bent: tip is close to palm -> bend = 1
     *
     * @param palm Palm position
     * @param tip Fingertip position
     * @param maxDistance Maximum distance when finger is fully extended
     * @return Normalized bend value (0.0 to 1.0)
     */
    private fun calculateFingerBend(palm: Vector3?, tip: Vector3?, maxDistance: Float): Float {
        if (palm == null || tip == null) {
            return 0.5f  // Return middle value if joints not detected
        }

        val distance = distance3D(palm, tip)

        // Invert: small distance = high bend, large distance = low bend
        val bend = 1.0f - (distance / maxDistance)

        return bend.coerceIn(0f, 1f)
    }

    /**
     * Calculate thumb yaw (lateral movement / abduction-adduction)
     *
     * This measures how much the thumb moves sideways relative to the palm plane.
     * 0 = thumb tucked in (adducted)
     * 1 = thumb spread out (abducted)
     *
     * @param wrist Wrist position
     * @param palm Palm center position
     * @param thumbMeta Thumb metacarpal position
     * @param thumbTip Thumb tip position
     * @return Normalized yaw value (0.0 to 1.0)
     */
    private fun calculateThumbYaw(
        wrist: Vector3?,
        palm: Vector3?,
        thumbMeta: Vector3?,
        thumbTip: Vector3?
    ): Float {
        if (wrist == null || palm == null || thumbTip == null) {
            return 0.5f  // Return middle value if joints not detected
        }

        // Calculate palm forward direction (wrist to palm)
        val palmForward = Vector3(
            palm.x - wrist.x,
            palm.y - wrist.y,
            palm.z - wrist.z
        )

        // Calculate thumb direction relative to palm
        val thumbDir = Vector3(
            thumbTip.x - palm.x,
            thumbTip.y - palm.y,
            thumbTip.z - palm.z
        )

        // Calculate lateral component (perpendicular to palm forward)
        // Using simplified approach: measure x-axis offset
        val lateralOffset = thumbTip.x - palm.x

        // Normalize to 0-1 range
        val normalizedYaw = (lateralOffset + THUMB_YAW_RANGE / 2) / THUMB_YAW_RANGE

        return normalizedYaw.coerceIn(0f, 1f)
    }

    /**
     * Convert normalized value (0.0-1.0) to O6 control range (0-255)
     */
    private fun normalizedToO6(value: Float): Int {
        return (value * 255).toInt().coerceIn(0, 255)
    }

    /**
     * Calculate Euclidean distance between two 3D points
     */
    private fun distance3D(a: Vector3, b: Vector3): Float {
        val dx = a.x - b.x
        val dy = a.y - b.y
        val dz = a.z - b.z
        return sqrt(dx * dx + dy * dy + dz * dz)
    }

    /**
     * Get finger bend values as a FloatArray for JSON serialization
     *
     * @param handState The hand state from Android XR
     * @return FloatArray of 6 normalized values (0.0-1.0), or null if hand not detected
     */
    fun getFingerBendNormalized(handState: Hand.State?): FloatArray? {
        val o6Values = convertToO6(handState) ?: return null
        return FloatArray(6) { i -> o6Values[i] / 255f }
    }
}
