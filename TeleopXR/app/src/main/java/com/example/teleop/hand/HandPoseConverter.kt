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

        // Distance range (meters) from palm to fingertip
        // MAX = fully extended (straight), MIN = fully bent (fist)
        // 校准后的数值 - 缩小范围以获得完整的0-255输出
        private const val THUMB_MAX_DIST = 0.10f   // 手指伸直时的距离
        private const val THUMB_MIN_DIST = 0.05f   // 手指弯曲时的距离
        private const val INDEX_MAX_DIST = 0.12f
        private const val INDEX_MIN_DIST = 0.06f
        private const val MIDDLE_MAX_DIST = 0.13f
        private const val MIDDLE_MIN_DIST = 0.06f
        private const val RING_MAX_DIST = 0.12f
        private const val RING_MIN_DIST = 0.06f
        private const val PINKY_MAX_DIST = 0.10f
        private const val PINKY_MIN_DIST = 0.05f

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

        // DEBUG: 打印 handState 的完整信息
        Log.i(TAG, "=== HAND STATE DEBUG ===")
        Log.i(TAG, "handState class: ${handState::class.java.name}")
        Log.i(TAG, "handState toString: $handState")

        val joints = handState.handJoints

        Log.i(TAG, "joints is null: ${joints == null}")
        Log.i(TAG, "joints size: ${joints?.size ?: 0}")
        Log.i(TAG, "joints keys: ${joints?.keys?.joinToString() ?: "null"}")

        if (joints != null && joints.isNotEmpty()) {
            joints.forEach { (jointType, pose) ->
                val pos = pose.translation
                Log.i(TAG, "Joint $jointType: x=${pos.x}, y=${pos.y}, z=${pos.z}")
            }
        } else {
            Log.w(TAG, "joints map is empty or null!")
        }

        // Get key joint positions
        val palm = joints[HandJointType.HAND_JOINT_TYPE_PALM]?.translation
        val wrist = joints[HandJointType.HAND_JOINT_TYPE_WRIST]?.translation

        // Thumb joints
        val thumbTip = joints[HandJointType.HAND_JOINT_TYPE_THUMB_TIP]?.translation
        val thumbDistal = joints[HandJointType.HAND_JOINT_TYPE_THUMB_DISTAL]?.translation
        val thumbProximal = joints[HandJointType.HAND_JOINT_TYPE_THUMB_PROXIMAL]?.translation
        val thumbMetacarpal = joints[HandJointType.HAND_JOINT_TYPE_THUMB_METACARPAL]?.translation

        // Index finger joints (need metacarpal for palm plane)
        val indexMetacarpal = joints[HandJointType.HAND_JOINT_TYPE_INDEX_METACARPAL]?.translation
        val indexTip = joints[HandJointType.HAND_JOINT_TYPE_INDEX_TIP]?.translation

        // Other finger tips
        val middleTip = joints[HandJointType.HAND_JOINT_TYPE_MIDDLE_TIP]?.translation
        val ringTip = joints[HandJointType.HAND_JOINT_TYPE_RING_TIP]?.translation
        val pinkyTip = joints[HandJointType.HAND_JOINT_TYPE_LITTLE_TIP]?.translation

        // DEBUG: 打印关键关节位置
        Log.i(TAG, "Palm: $palm, Wrist: $wrist")
        Log.i(TAG, "ThumbTip: $thumbTip, IndexTip: $indexTip")
        Log.i(TAG, "MiddleTip: $middleTip, RingTip: $ringTip, PinkyTip: $pinkyTip")

        // Validate required joints are present
        if (palm == null || wrist == null) {
            Log.w(TAG, "Palm or wrist not detected")
            return null
        }

        // Calculate bend values for each finger (0.0 = straight, 1.0 = fully bent)
        val thumbBend = calculateFingerBend(palm, thumbTip, THUMB_MIN_DIST, THUMB_MAX_DIST, "thumb")
        val thumbYaw = calculateThumbYaw(wrist, palm, indexMetacarpal, thumbMetacarpal, thumbTip)
        val indexBend = calculateFingerBend(palm, indexTip, INDEX_MIN_DIST, INDEX_MAX_DIST, "index")
        val middleBend = calculateFingerBend(palm, middleTip, MIDDLE_MIN_DIST, MIDDLE_MAX_DIST, "middle")
        val ringBend = calculateFingerBend(palm, ringTip, RING_MIN_DIST, RING_MAX_DIST, "ring")
        val pinkyBend = calculateFingerBend(palm, pinkyTip, PINKY_MIN_DIST, PINKY_MAX_DIST, "pinky")

        // DEBUG: 打印伸直程度 (0=握拳, 1=伸直)
        Log.i(TAG, "Extend values - thumb:${"%.2f".format(thumbBend)}, thumbYaw:${"%.2f".format(thumbYaw)}, index:${"%.2f".format(indexBend)}, middle:${"%.2f".format(middleBend)}, ring:${"%.2f".format(ringBend)}, pinky:${"%.2f".format(pinkyBend)}")

        // Convert normalized values (0.0-1.0) to O6 range (0-255)
        val result = intArrayOf(
            normalizedToO6(thumbBend),
            normalizedToO6(thumbYaw),
            normalizedToO6(indexBend),
            normalizedToO6(middleBend),
            normalizedToO6(ringBend),
            normalizedToO6(pinkyBend)
        )

        Log.i(TAG, ">>> O6 OUTPUT: ${result.joinToString(", ")} <<<")
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
    private fun calculateFingerBend(palm: Vector3?, tip: Vector3?, minDistance: Float, maxDistance: Float, fingerName: String = ""): Float {
        if (palm == null || tip == null) {
            Log.w(TAG, "$fingerName: palm or tip is null!")
            return 0.5f  // Return middle value if joints not detected
        }

        val distance = distance3D(palm, tip)

        // 计算伸直程度（注意：这里输出的是"伸直程度"，不是"弯曲程度"）
        // distance = maxDistance → 手指伸直 → 输出 1.0 → O6 = 255
        // distance = minDistance → 手指弯曲(握拳) → 输出 0.0 → O6 = 0
        val range = maxDistance - minDistance
        val extend = (distance - minDistance) / range

        Log.i(TAG, "$fingerName: dist=${"%.3f".format(distance)}, range=[${"%.3f".format(minDistance)}-${"%.3f".format(maxDistance)}], extend=${"%.2f".format(extend)}")

        return extend.coerceIn(0f, 1f)
    }

    /**
     * Calculate thumb yaw (lateral movement / abduction-adduction)
     * 使用手掌局部坐标系，不受手掌朝向影响
     *
     * 0 = thumb tucked in (adducted, 大拇指收拢)
     * 1 = thumb spread out (abducted, 大拇指张开)
     *
     * @param wrist Wrist position
     * @param palm Palm center position
     * @param indexMeta Index metacarpal position (用于建立手掌平面)
     * @param thumbMeta Thumb metacarpal position
     * @param thumbTip Thumb tip position
     * @return Normalized yaw value (0.0 to 1.0)
     */
    private fun calculateThumbYaw(
        wrist: Vector3?,
        palm: Vector3?,
        indexMeta: Vector3?,
        thumbMeta: Vector3?,
        thumbTip: Vector3?
    ): Float {
        if (wrist == null || palm == null || thumbTip == null || indexMeta == null || thumbMeta == null) {
            Log.w(TAG, "thumbYaw: missing joints")
            return 0.5f
        }

        // 1. 建立手掌局部坐标系
        // palmForward: 从手腕到掌心的方向 (手指方向)
        val palmForward = normalize(Vector3(
            palm.x - wrist.x,
            palm.y - wrist.y,
            palm.z - wrist.z
        ))

        // palmRight: 从掌心到食指根部的方向 (手掌右侧)
        val toIndex = Vector3(
            indexMeta.x - palm.x,
            indexMeta.y - palm.y,
            indexMeta.z - palm.z
        )

        // palmNormal: 手掌法向量 (掌心朝向) = forward × toIndex
        val palmNormal = normalize(cross(palmForward, toIndex))

        // palmRight: 修正后的手掌右侧 = normal × forward
        val palmRight = normalize(cross(palmNormal, palmForward))

        // 2. 计算大拇指方向（从大拇指根部到指尖）
        val thumbDir = Vector3(
            thumbTip.x - thumbMeta.x,
            thumbTip.y - thumbMeta.y,
            thumbTip.z - thumbMeta.z
        )

        // 3. 把大拇指方向投影到手掌局部坐标系
        val thumbInPalmRight = dot(thumbDir, palmRight)    // 左右分量
        val thumbInPalmForward = dot(thumbDir, palmForward) // 前后分量

        // 4. 计算角度 (atan2 返回 -PI 到 PI)
        val angle = atan2(thumbInPalmRight, thumbInPalmForward)

        // 5. 归一化到 0-1
        // 大拇指收拢时 angle ≈ -PI/2, 张开时 angle ≈ 0 或正值
        // 映射: -PI/2 → 0, 0 → 0.5, PI/2 → 1
        val normalizedYaw = (angle + Math.PI.toFloat() / 2) / Math.PI.toFloat()

        Log.i(TAG, "thumbYaw: angle=${"%.2f".format(Math.toDegrees(angle.toDouble()))}°, yaw=${"%.2f".format(normalizedYaw)}")

        return normalizedYaw.coerceIn(0f, 1f)
    }

    // 向量运算辅助函数
    private fun normalize(v: Vector3): Vector3 {
        val len = sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
        return if (len > 0.0001f) Vector3(v.x / len, v.y / len, v.z / len) else v
    }

    private fun cross(a: Vector3, b: Vector3): Vector3 {
        return Vector3(
            a.y * b.z - a.z * b.y,
            a.z * b.x - a.x * b.z,
            a.x * b.y - a.y * b.x
        )
    }

    private fun dot(a: Vector3, b: Vector3): Float {
        return a.x * b.x + a.y * b.y + a.z * b.z
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
