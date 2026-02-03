# XR Teleop 开发总结

> 记录从接收 XR UDP 数据到控制 LinkerHand O6 的开发工作

---

## 开发目标

接收来自 Android XR (Samsung Galaxy XR) 的手部追踪数据，通过 ROS2 控制双手 LinkerHand O6 灵巧手。

---

## 完成的开发工作

### 1. 创建 teleop_receiver 节点

**文件：** `linker_hand_ros2_sdk/linker_hand_ros2_sdk/teleop_receiver.py`

**功能：**
- 监听 UDP 端口 5000，接收来自 XR 设备的手部追踪数据
- 解析 JSON 格式的数据包
- 将 O6 控制值发布到 ROS2 Topic
- 支持左手、右手、双手三种模式

**接收的数据格式：**
```json
{
    "type": "hand_pose",
    "hand": "left",
    "o6_values": [0, 128, 255, 200, 150, 100]
}
```

**发布的 Topic：**
| Topic 名称 | 消息类型 | 说明 |
|-----------|---------|------|
| `/cb_left_hand_control_cmd` | JointState | 左手控制指令 |
| `/cb_right_hand_control_cmd` | JointState | 右手控制指令 |
| `/teleop_raw_data` | String | 原始数据（调试用） |

---

### 2. 创建 VR_teleop.launch.py 启动文件

**文件：** `linker_hand_ros2_sdk/launch/VR_teleop.launch.py`

**功能：**
- 一键启动所有 VR 遥操作所需的节点
- 启动左手驱动节点 (can0)
- 启动右手驱动节点 (can1)
- 延迟 3 秒后启动 teleop_receiver
- 5 秒后显示提示信息

**启动命令：**
```bash
ros2 launch linker_hand_ros2_sdk VR_teleop.launch.py
```

---

### 3. 修改 linker_hand_double.launch.py

**文件：** `linker_hand_ros2_sdk/launch/linker_hand_double.launch.py`

**修改内容：**
- 配置左手使用 can0
- 配置右手使用 can1
- 设置手型为 O6

---

### 4. 修改 gui_control.launch.py

**文件：** `gui_control/launch/gui_control.launch.py`

**修改内容：**
- 支持双手 GUI 控制
- 配置左手和右手节点参数

---

### 5. 注册 teleop_receiver 入口点

**文件：** `linker_hand_ros2_sdk/setup.py`

**添加内容：**
```python
entry_points={
    'console_scripts': [
        ...
        'teleop_receiver = linker_hand_ros2_sdk.teleop_receiver:main',
    ],
}
```

---

### 6. 创建 start_dual_hands.sh 启动脚本

**文件：** `/home/yuxia/linker_hand_ros2_sdk/start_dual_hands.sh`

**功能：**
- 引导用户插入 CAN 适配器
- 自动配置 can0 和 can1
- 启动 Docker 容器
- 显示使用说明

---

## 数据流

```
Android XR 设备
     │
     │  UDP (端口 5000)
     │  JSON: {"type":"hand_pose", "hand":"left/right", "o6_values":[...]}
     ▼
teleop_receiver 节点
     │
     ├──► /cb_left_hand_control_cmd ──► linker_hand_sdk_left ──► CAN0 ──► 左手
     │
     └──► /cb_right_hand_control_cmd ──► linker_hand_sdk_right ──► CAN1 ──► 右手
```

---

## O6 控制值说明

| 索引 | 手指 | 范围 | 说明 |
|-----|------|------|------|
| 0 | 大拇指 | 0-255 | 弯曲角度 |
| 1 | 食指 | 0-255 | 弯曲角度 |
| 2 | 中指 | 0-255 | 弯曲角度 |
| 3 | 无名指 | 0-255 | 弯曲角度 |
| 4 | 小指 | 0-255 | 弯曲角度 |
| 5 | 大拇指旋转 | 0-255 | 横向移动 |

---

## 使用方法

### 1. 在主机上启动
```bash
cd ~/linker_hand_ros2_sdk
./start_dual_hands.sh
```

### 2. 在 Docker 内启动 VR Teleop
```bash
cd /root/linker_hand_ros2_sdk
source install/setup.bash
ros2 launch linker_hand_ros2_sdk VR_teleop.launch.py
```

### 3. 可选：启动 GUI 控制
```bash
ros2 launch gui_control gui_control.launch.py
```

---

## 新增文件列表

| 文件 | 类型 | 说明 |
|-----|------|------|
| `teleop_receiver.py` | 新增 | UDP 接收节点 |
| `VR_teleop.launch.py` | 新增 | 组合启动文件 |
| `start_dual_hands.sh` | 新增 | 系统启动脚本 |
| `XR_Teleop_Development.md` | 新增 | 开发文档 |

## 修改文件列表

| 文件 | 修改内容 |
|-----|---------|
| `setup.py` | 添加 teleop_receiver 入口点 |
| `linker_hand_double.launch.py` | 配置双手 CAN |
| `gui_control.launch.py` | 支持双手 |

---

*文档更新时间: 2026-02*
