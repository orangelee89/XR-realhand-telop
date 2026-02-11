#!/bin/bash
# Dual Hand VR Teleop Startup Script

set -e

echo "========================================"
echo "  LinkerHand Dual Hand VR Teleop Setup"
echo "========================================"

# Step 1: Prompt to plug in CAN adapters
echo ""
echo "[Step 1] Please plug in the CAN adapters:"
echo "  - First plug LEFT hand  -> will be can0"
echo "  - Then plug RIGHT hand  -> will be can1"
echo ""
read -p "Press ENTER when both CAN adapters are plugged in..."

# Step 2: Setup CAN0 (Left Hand)
echo ""
echo "[Step 2] Setting up can0 (Left Hand)..."

setup_can() {
    local can_name=$1
    local tty_device=$2

    # Try native CAN first
    if sudo /usr/sbin/ip link set $can_name up type can bitrate 1000000 2>/dev/null; then
        echo "  [OK] $can_name set up using native CAN"
        return 0
    fi

    # Check if already exists
    if ip link show $can_name &>/dev/null; then
        echo "  [OK] $can_name already exists"
        return 0
    fi

    # Try slcand
    if [ -e "$tty_device" ]; then
        echo "  [INFO] Trying slcand with $tty_device..."
        sudo slcand -o -s8 -t hw -S 1000000 $tty_device $can_name
        sleep 1
        sudo ip link set $can_name up
        if ip link show $can_name &>/dev/null; then
            echo "  [OK] $can_name set up using slcand ($tty_device)"
            return 0
        fi
    fi

    echo "  [FAIL] Could not set up $can_name"
    return 1
}

# Setup can0
if ! setup_can "can0" "/dev/ttyACM0"; then
    setup_can "can0" "/dev/ttyACM1" || {
        echo "[ERROR] Failed to setup can0. Check your CAN adapter."
        exit 1
    }
fi

# Step 3: Setup CAN1 (Right Hand)
echo ""
echo "[Step 3] Setting up can1 (Right Hand)..."

if ! setup_can "can1" "/dev/ttyACM1"; then
    setup_can "can1" "/dev/ttyACM2" || {
        echo "[ERROR] Failed to setup can1. Check your CAN adapter."
        exit 1
    }
fi

# Step 4: Verify CAN interfaces
echo ""
echo "[Step 4] Verifying CAN interfaces..."
echo "  Available CAN interfaces:"
ip link show | grep -E "can[0-9]:" || echo "  None found!"

if ! ip link show can0 &>/dev/null; then
    echo "[ERROR] can0 not found!"
    exit 1
fi

if ! ip link show can1 &>/dev/null; then
    echo "[ERROR] can1 not found!"
    exit 1
fi

echo "  [OK] Both can0 and can1 are ready"

# Step 5: Start Docker
echo ""
echo "[Step 5] Starting RealHand Docker..."
echo ""
read -p "Press ENTER to start Docker container..."

# Check if container is already running
if docker ps | grep -q realhand; then
    echo "  [INFO] realhand container already running"
else
    echo "  [INFO] Starting realhand container..."
    docker start realhand 2>/dev/null || {
        echo "  [INFO] Container not found, please start it manually"
        echo "  Run: docker run ... (your docker run command)"
        exit 1
    }
fi

# Step 6: Instructions for inside Docker
echo ""
echo "========================================"
echo "  Docker is ready!"
echo "========================================"
echo ""
echo "To open another Docker terminal, run in a NEW terminal:"
echo ""
echo "  docker exec -it realhand bash"
echo ""
echo "----------------------------------------"
echo ""
echo "Now run inside the Docker container:"
echo ""
echo "  # Terminal 1: Start dual hands"
echo "  cd /root/linker_hand_ros2_sdk && source install/setup.bash"
echo "  ros2 launch linker_hand_ros2_sdk linker_hand_double.launch.py"
echo ""
echo "  # Terminal 2: Start teleop receiver"
echo "  cd /root/linker_hand_ros2_sdk && source install/setup.bash"
echo "  ros2 run linker_hand_ros2_sdk teleop_receiver --ros-args -p port:=5000 -p hand_type:=both"
echo ""
echo "Or use the combined launch file:"
echo "  ros2 launch linker_hand_ros2_sdk VR_teleop.launch.py"
echo ""
echo "  # Optional: GUI control"
echo "  ros2 launch gui_control gui_control.launch.py"
echo ""

# Enter docker
echo "Entering Docker container..."
docker exec -it realhand bash
