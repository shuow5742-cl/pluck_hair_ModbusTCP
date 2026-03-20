#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # 指定源码编码为 UTF-8。

from __future__ import annotations  # 允许在类型注解中直接引用尚未定义的类名。

# ============================== 第1块：统一配置区 ==============================  # 说明这是统一配置区。

import json  # 导入 json，用于处理 JSON-RPC 请求和响应。
import math  # 导入数学库，用于校验数值是否合法。
import struct  # 导入结构体库，用于 INT32/FLOAT32 与寄存器之间互转。
import threading  # 导入线程库，用于主循环线程和算法心跳线程。
import time  # 导入时间库，用于轮询和超时控制。
import urllib.error  # 导入 urllib 异常模块，用于捕获 HTTP 请求异常。
import urllib.request  # 导入 urllib 请求模块，用于发送 JSON-RPC HTTP 请求。
from typing import Any, Callable, Optional  # 导入类型标注工具。

from pymodbus.client import ModbusTcpClient  # 导入 Modbus TCP 客户端。

PLC_IP = "192.168.1.88"  # PLC 的 IP 地址，现场修改统一改这里。
PLC_PORT = 502  # PLC 的 Modbus TCP 端口，现场修改统一改这里。
UNIT_ID = 1  # PLC 的从站号，现场修改统一改这里。
CONNECT_TIMEOUT = 3.0  # 建立 Modbus TCP 连接超时时间，单位秒。
WORD_ORDER = "little"  # 32 位数据字序，沿用你现场已经验证通过的 little。
POLL_INTERVAL = 0.10  # 主循环轮询 PLC 的周期，单位秒。
HEARTBEAT_PERIOD = 1.0  # 算法心跳更新周期，单位秒。
ENABLE_PLC_HEARTBEAT_CHECK = False  # 是否启用 PLC 心跳检测，当前先默认关闭。
PLC_HEARTBEAT_TIMEOUT = 5.0  # PLC 心跳超时时间，单位秒。
RPC_URL = "http://127.0.0.1:18080/jsonrpc"  # 算法主程序 JSON-RPC 服务地址。
RPC_TIMEOUT = 300.0  # 单次 JSON-RPC 请求的超时时间，单位秒。
FIXED_TARGET_Z = 50.16  # 固定下发给 PLC 的 Z 值，算法主程序不再提供。
STATE_NEW_TARGET = "new_target"  # 主程序返回：当前是新异物坐标。
STATE_RETRY_1 = "retry_1"  # 主程序返回：当前是第一次复抓。
STATE_RETRY_2 = "retry_2"  # 主程序返回：当前是第二次复抓。
STATE_NO_TARGET = "no_target"  # 主程序返回：当前视野已经没有异物。
VALID_ALGO_STATES = {STATE_NEW_TARGET, STATE_RETRY_1, STATE_RETRY_2, STATE_NO_TARGET}  # 定义主程序允许返回的状态字符串集合。
LOG_PREFIX = "[ModbusTCP_auto_rpc]"  # 统一日志前缀，便于现场识别输出来源。

# ============================ 第2块：统一地址定义区 ============================  # 说明这是统一地址定义区。


def md_to_offset(md_no: int) -> int:  # 把 MD 号转换成 pymodbus 使用的寄存器偏移地址。
    return md_no * 2  # 按你现场已验证的规则：MDn 对应偏移 n*2。


# ---------------- PLC写、算法读：MD500-MD530 ----------------  # 说明下面是 PLC 输入区地址。

MD_FIRST_TRIGGER = 500  # 首次拍照触发信号 MD500-501。
MD_COORD_ACK = 502  # PLC 反馈结果正常/异常信号 MD502-503。
MD_RECHECK_TRIGGER = 504  # 复拍触发信号 MD504-505。
MD_PLC_HEARTBEAT = 506  # PLC 心跳 MD506-507。

# ---------------- 算法写、PLC读：MD531-MD560 ----------------  # 说明下面是算法输出区地址。

MD_RESULT_STATUS = 531  # 结果状态信号 MD531-532。
MD_TARGET_X = 533  # 目标 X 坐标 MD533-534。
MD_TARGET_Y = 535  # 目标 Y 坐标 MD535-536。
MD_TARGET_Z = 537  # 目标 Z 坐标 MD537-538。
MD_TARGET_U = 539  # 目标 U 坐标 MD539-540。
MD_ALGO_HEARTBEAT = 541  # 算法心跳 MD541-542。
MD_ALGO_FAULT = 543  # 算法故障码 MD543-544。
MD_ALGO_BUSY = 545  # 算法忙碌状态 MD545-546。
MD_RETRY_COUNT = 547  # 当前目标挑取次数 MD547-548。
MD_REMAIN_COUNT = 549  # 当前异物数量 MD549-550。
MD_RESET_REQUEST = 551  # 算法复位请求 MD551-552。

PLC_READ_MD_LIST = [  # 定义算法允许读取的 PLC 输入区地址列表。
    MD_FIRST_TRIGGER,  # 首次拍照触发。
    MD_COORD_ACK,  # PLC 反馈结果正常/异常。
    MD_RECHECK_TRIGGER,  # 复拍触发。
    MD_PLC_HEARTBEAT,  # PLC 心跳。
]

ALGO_WRITE_MD_LIST = [  # 定义算法允许写入的算法输出区地址列表。
    MD_RESULT_STATUS,  # 结果状态。
    MD_TARGET_X,  # X 坐标。
    MD_TARGET_Y,  # Y 坐标。
    MD_TARGET_Z,  # Z 坐标。
    MD_TARGET_U,  # U 坐标。
    MD_ALGO_HEARTBEAT,  # 算法心跳。
    MD_ALGO_FAULT,  # 故障码。
    MD_ALGO_BUSY,  # 忙碌状态。
    MD_RETRY_COUNT,  # 挑取次数。
    MD_REMAIN_COUNT,  # 当前异物数量。
    MD_RESET_REQUEST,  # 复位请求。
]

# ============================ 第3块：状态常量定义区 ============================  # 说明这是状态常量定义区。

RESULT_NONE = 0  # 当前无新结果。
RESULT_READY = 1  # 当前有新坐标可读取。
RESULT_NO_OBJECT = 2  # 当前视野无异物。

ACK_INIT = 0  # PLC 尚未反馈，或本轮已复位。
ACK_OK = 1  # PLC 反馈本轮收到的数据正常。
ACK_ERROR = 2  # PLC 反馈本轮收到的数据异常。

BUSY_IDLE = 0  # 算法空闲。
BUSY_WORKING = 1  # 算法忙碌。

RESET_NONE = 0  # 无复位请求。
RESET_REQUESTED = 1  # 请求 PLC 执行上层复位。

TASK_FIRST_DETECT = "first_detect"  # 首次拍照检测任务类型。
TASK_RECHECK_DETECT = "recheck_detect"  # 复拍检测任务类型。

STATE_INIT = "INIT"  # 初始化状态。
STATE_WAIT_FIRST_TRIGGER = "WAIT_FIRST_TRIGGER"  # 等待首次触发状态。
STATE_WAIT_PLC_ACK_AFTER_FIRST = "WAIT_PLC_ACK_AFTER_FIRST"  # 等待首次结果 PLC 反馈状态。
STATE_WAIT_RECHECK_TRIGGER = "WAIT_RECHECK_TRIGGER"  # 等待复拍触发状态。
STATE_WAIT_PLC_ACK_AFTER_RECHECK = "WAIT_PLC_ACK_AFTER_RECHECK"  # 等待复拍结果 PLC 反馈状态。
STATE_PAUSED_ON_PLC_ACK_ERROR = "PAUSED_ON_PLC_ACK_ERROR"  # PLC 反馈异常后暂停状态。
STATE_FAULT = "FAULT"  # 故障状态。
STATE_STOPPED = "STOPPED"  # 已停止状态。

FAULT_NONE = 0  # 无故障。
FAULT_CONNECT = 1001  # 连接 PLC 失败。
FAULT_READ = 1002  # 读取 PLC 失败。
FAULT_WRITE = 1003  # 写入 PLC 失败。
FAULT_HEARTBEAT_TIMEOUT = 1004  # PLC 心跳超时。
FAULT_INVALID_RESULT = 1005  # 算法返回结果非法。
FAULT_RPC_ERROR = 1006  # JSON-RPC 调用失败。
FAULT_PLC_ACK_ERROR = 1007  # PLC 反馈数据异常。

# ============================== 第4块：公共工具函数区 ==============================  # 说明这是公共工具函数区。


def log(message: str) -> None:  # 定义统一日志输出函数。
    print(f"{LOG_PREFIX} {message}")  # 打印带统一前缀的日志。


def is_number(value: Any) -> bool:  # 定义检查对象是否为数字的函数。
    return isinstance(value, (int, float))  # 只允许 int 和 float 作为数字类型。


def validate_coord_value(value: Any, name: str) -> None:  # 定义坐标校验函数。
    if not is_number(value):  # 如果坐标不是数字。
        raise ValueError(f"{name} 必须是数字")  # 抛出异常提示坐标类型错误。
    if math.isnan(float(value)) or math.isinf(float(value)):  # 如果坐标是 NaN 或 inf。
        raise ValueError(f"{name} 不能是 NaN 或 inf")  # 抛出异常提示坐标值非法。


def validate_int_value(value: Any, name: str, min_value: int = 0) -> None:  # 定义整型字段校验函数。
    if not isinstance(value, int):  # 如果字段不是 int。
        raise ValueError(f"{name} 必须是 int")  # 抛出异常提示类型错误。
    if value < min_value:  # 如果字段小于允许最小值。
        raise ValueError(f"{name} 不能小于 {min_value}")  # 抛出异常提示数值范围错误。


# ============================== 第5块：底层 Modbus 读写类 ==============================  # 说明这是底层 Modbus 通信类。


class SafeModbusClient:  # 定义安全版 Modbus 客户端类。
    def __init__(self, host: str, port: int, timeout: float, unit_id: int) -> None:  # 定义初始化函数。
        self.host = host  # 保存 PLC IP。
        self.port = port  # 保存 PLC 端口。
        self.timeout = timeout  # 保存连接超时时间。
        self.unit_id = unit_id  # 保存从站号。
        self.client = ModbusTcpClient(host=host, port=port, timeout=timeout)  # 创建底层 pymodbus 客户端。

    def connect(self) -> bool:  # 定义建立连接的函数。
        return self.client.connect()  # 调用 pymodbus connect 方法建立连接。

    def close(self) -> None:  # 定义关闭连接的函数。
        self.client.close()  # 关闭底层 TCP 连接。

    def _read_holding_registers(self, address: int, count: int):  # 定义读保持寄存器的底层函数。
        try:  # 先尝试使用较新 pymodbus 参数名。
            return self.client.read_holding_registers(address=address, count=count, device_id=self.unit_id)  # 用 device_id 读取寄存器。
        except TypeError:  # 如果当前版本不支持 device_id。
            return self.client.read_holding_registers(address=address, count=count, slave=self.unit_id)  # 回退到 slave 参数。

    def _write_register(self, address: int, value: int):  # 定义写单个寄存器的底层函数。
        try:  # 先尝试使用较新 pymodbus 参数名。
            return self.client.write_register(address=address, value=value, device_id=self.unit_id)  # 用 device_id 写寄存器。
        except TypeError:  # 如果当前版本不支持 device_id。
            return self.client.write_register(address=address, value=value, slave=self.unit_id)  # 回退到 slave 参数。

    def _bytes_to_regs(self, data: bytes) -> tuple[int, int]:  # 定义把 4 字节拆分成 2 个寄存器的函数。
        reg_high = int.from_bytes(data[0:2], "big")  # 取前 2 字节作为高字寄存器值。
        reg_low = int.from_bytes(data[2:4], "big")  # 取后 2 字节作为低字寄存器值。
        if WORD_ORDER == "big":  # 如果高字在前。
            return reg_high, reg_low  # 返回高字、低字顺序。
        return reg_low, reg_high  # 否则返回低字、高字顺序。

    def _regs_to_bytes(self, reg1: int, reg2: int) -> bytes:  # 定义把 2 个寄存器拼成 4 字节的函数。
        if WORD_ORDER == "big":  # 如果高字在前。
            return reg1.to_bytes(2, "big") + reg2.to_bytes(2, "big")  # 按高字在前拼接成 4 字节。
        return reg2.to_bytes(2, "big") + reg1.to_bytes(2, "big")  # 按低字在前拼接成 4 字节。

    def read_two_registers(self, md_no: int) -> tuple[int, int]:  # 定义读取 2 个寄存器的函数。
        validate_md_read(md_no)  # 先校验该地址是否允许算法读取。
        address = md_to_offset(md_no)  # 计算寄存器偏移地址。
        resp = self._read_holding_registers(address=address, count=2)  # 从 PLC 读取 2 个寄存器。
        if resp.isError():  # 如果读取返回错误。
            raise RuntimeError(f"读取失败：MD{md_no}，offset={address}，response={resp}")  # 抛出异常便于上层统一处理。
        if not hasattr(resp, "registers") or len(resp.registers) < 2:  # 如果返回结果长度异常。
            raise RuntimeError(f"读取结果异常：MD{md_no}，offset={address}，response={resp}")  # 抛出异常。
        return resp.registers[0], resp.registers[1]  # 返回读取到的两个寄存器原始值。

    def write_two_registers(self, md_no: int, reg1: int, reg2: int) -> None:  # 定义写入 2 个寄存器的函数。
        validate_md_write(md_no)  # 先校验该地址是否允许算法写入。
        address = md_to_offset(md_no)  # 计算寄存器偏移地址。
        resp1 = self._write_register(address=address, value=reg1)  # 先写第一个寄存器。
        if resp1.isError():  # 如果第一个寄存器写失败。
            raise RuntimeError(f"写入失败：MD{md_no}，offset={address}，response={resp1}")  # 抛出异常。
        resp2 = self._write_register(address=address + 1, value=reg2)  # 再写第二个寄存器。
        if resp2.isError():  # 如果第二个寄存器写失败。
            raise RuntimeError(f"写入失败：MD{md_no}，offset={address + 1}，response={resp2}")  # 抛出异常。

    def read_int32(self, md_no: int) -> int:  # 定义读取 INT32 的函数。
        reg1, reg2 = self.read_two_registers(md_no)  # 先读两个寄存器。
        data = self._regs_to_bytes(reg1, reg2)  # 把两个寄存器拼成 4 字节。
        return struct.unpack(">i", data)[0]  # 按大端有符号 32 位整型解包并返回。

    def write_int32(self, md_no: int, value: int) -> None:  # 定义写入 INT32 的函数。
        data = struct.pack(">i", int(value))  # 把 int 打包成 4 字节。
        reg1, reg2 = self._bytes_to_regs(data)  # 把 4 字节拆成两个寄存器。
        self.write_two_registers(md_no, reg1, reg2)  # 把两个寄存器写到 PLC。

    def write_float32(self, md_no: int, value: float) -> None:  # 定义写入 FLOAT32 的函数。
        data = struct.pack(">f", float(value))  # 把 float 打包成 4 字节。
        reg1, reg2 = self._bytes_to_regs(data)  # 把 4 字节拆成两个寄存器。
        self.write_two_registers(md_no, reg1, reg2)  # 把两个寄存器写到 PLC。


# ============================== 第6块：权限校验区 ==============================  # 说明这是寄存器访问权限校验区。


def validate_md_read(md_no: int) -> None:  # 定义算法读地址校验函数。
    if md_no not in PLC_READ_MD_LIST and md_no not in ALGO_WRITE_MD_LIST:  # 如果地址不在允许读取的列表中。
        raise ValueError(f"禁止读取未定义地址：MD{md_no}")  # 拒绝读取未定义地址。


def validate_md_write(md_no: int) -> None:  # 定义算法写地址校验函数。
    if md_no not in ALGO_WRITE_MD_LIST:  # 如果地址不在算法允许写的列表中。
        raise ValueError(f"禁止写入非算法输出区地址：MD{md_no}")  # 拒绝写入 PLC 输入区或未定义区。


# ============================== 第7块：JSON-RPC 客户端区 ==============================  # 说明这是 JSON-RPC 客户端区。


class JsonRpcClient:  # 定义简单的 JSON-RPC HTTP 客户端类。
    def __init__(self, url: str, timeout: float = RPC_TIMEOUT) -> None:  # 定义初始化函数。
        self.url = url  # 保存 RPC 服务地址。
        self.timeout = timeout  # 保存请求超时时间。
        self._rpc_id = 0  # 保存 RPC 请求自增编号。

    def call(self, method: str, params: dict[str, Any]) -> Any:  # 定义发送 JSON-RPC 调用的函数。
        self._rpc_id += 1  # 每次调用前把 RPC 请求编号递增。
        payload = {  # 组装 JSON-RPC 2.0 标准请求体。
            "jsonrpc": "2.0",  # 指定 JSON-RPC 协议版本。
            "id": self._rpc_id,  # 写入本次请求编号。
            "method": method,  # 写入本次调用的方法名。
            "params": params,  # 写入本次调用的参数。
        }
        data = json.dumps(payload).encode("utf-8")  # 把请求体编码成 UTF-8 字节串。
        request = urllib.request.Request(  # 创建 HTTP POST 请求对象。
            self.url,  # 指定请求地址。
            data=data,  # 指定 POST 的字节数据。
            headers={"Content-Type": "application/json"},  # 指定请求内容类型为 JSON。
            method="POST",  # 指定 HTTP 方法为 POST。
        )
        try:  # 尝试发送 HTTP 请求。
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:  # 发送请求并等待响应。
                raw = resp.read().decode("utf-8")  # 读取响应内容并解码成字符串。
        except urllib.error.URLError as exc:  # 如果请求失败。
            raise RuntimeError(f"JSON-RPC 请求失败：{exc}") from exc  # 抛出统一运行时异常。
        try:  # 尝试解析 JSON 响应。
            body = json.loads(raw)  # 把响应字符串解析为 Python 对象。
        except json.JSONDecodeError as exc:  # 如果响应不是合法 JSON。
            raise RuntimeError(f"JSON-RPC 响应不是合法 JSON：{raw}") from exc  # 抛出统一运行时异常。
        if "error" in body and body["error"] is not None:  # 如果 JSON-RPC 返回 error。
            raise RuntimeError(f"JSON-RPC 返回错误：{body['error']}")  # 抛出统一运行时异常。
        if "result" not in body:  # 如果 JSON-RPC 响应缺少 result 字段。
            raise RuntimeError(f"JSON-RPC 响应缺少 result：{body}")  # 抛出统一运行时异常。
        return body["result"]  # 返回 JSON-RPC result 字段内容。


# ============================== 第8块：自动通信核心类 ==============================  # 说明这是自动通信状态机核心类。


class AutoModbusCamRpcRunner:  # 定义基于 JSON-RPC 的自动通信运行器类。
    def __init__(
        self,
        plc_ip: str = PLC_IP,
        plc_port: int = PLC_PORT,
        unit_id: int = UNIT_ID,
        rpc_url: str = RPC_URL,
        poll_interval: float = POLL_INTERVAL,
        heartbeat_period: float = HEARTBEAT_PERIOD,
        plc_heartbeat_timeout: float = PLC_HEARTBEAT_TIMEOUT,
        enable_plc_heartbeat_check: bool = ENABLE_PLC_HEARTBEAT_CHECK,
        event_callback: Optional[Callable[[str, dict[str, Any]], None]] = None,
    ) -> None:  # 定义初始化函数。
        self.mb = SafeModbusClient(plc_ip, plc_port, CONNECT_TIMEOUT, unit_id)  # 创建底层 Modbus 客户端。
        self.rpc = JsonRpcClient(rpc_url, RPC_TIMEOUT)  # 创建 JSON-RPC 客户端。
        self.poll_interval = poll_interval  # 保存 PLC 轮询周期。
        self.heartbeat_period = heartbeat_period  # 保存算法心跳周期。
        self.plc_heartbeat_timeout = plc_heartbeat_timeout  # 保存 PLC 心跳超时时间。
        self.enable_plc_heartbeat_check = enable_plc_heartbeat_check  # 保存是否启用 PLC 心跳检测。
        self.event_callback = event_callback  # 保存可选事件回调函数。
        self.state = STATE_STOPPED  # 初始化时先标记为停止状态。
        self._stop_event = threading.Event()  # 创建停止事件，供线程退出使用。
        self._pause_event = threading.Event()  # 创建暂停事件，供人工暂停使用。
        self._main_thread: Optional[threading.Thread] = None  # 保存主循环线程对象。
        self._heartbeat_thread: Optional[threading.Thread] = None  # 保存心跳线程对象。
        self.connected = False  # 记录当前是否已连接 PLC。
        self.last_plc_heartbeat: Optional[int] = None  # 保存上一次 PLC 心跳值。
        self.last_plc_heartbeat_change_time = time.time()  # 保存最近一次 PLC 心跳变化时间。
        self.last_first_trigger = 0  # 保存上一次首次触发信号值，用于边沿检测。
        self.last_recheck_trigger = 0  # 保存上一次复拍触发信号值，用于边沿检测。
        self.algo_heartbeat_value = 0  # 保存算法心跳当前值。
        self.task_seq = 0  # 保存任务自增编号。
        self.last_sent_result_status = RESULT_NONE  # 保存上一轮已经发给 PLC 的结果状态。
        self.last_fault_code = FAULT_NONE  # 保存最近一次故障码，便于恢复时清零。

    def start(self) -> None:  # 定义启动自动通信的函数。
        if self._main_thread and self._main_thread.is_alive():  # 如果主循环线程已经在运行。
            log("自动通信已在运行，忽略重复 start()。")  # 输出提示，避免重复启动。
            return  # 直接返回，不重复启动。
        self._stop_event.clear()  # 清除停止事件，准备正常启动。
        self._pause_event.clear()  # 清除暂停事件，准备正常运行。
        self._main_thread = threading.Thread(target=self._run_loop, name="AutoModbusRpcMain", daemon=True)  # 创建主循环线程。
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="AutoModbusRpcHeartbeat", daemon=True)  # 创建心跳线程。
        self._main_thread.start()  # 启动主循环线程。
        self._heartbeat_thread.start()  # 启动心跳线程。
        log("自动通信线程已启动。")  # 输出启动成功日志。

    def stop(self) -> None:  # 定义停止自动通信的函数。
        self._stop_event.set()  # 设置停止事件，通知线程退出。
        self._pause_event.clear()  # 清除暂停事件，避免 stop 时被 pause 卡住。
        if self._main_thread and self._main_thread.is_alive():  # 如果主循环线程存在且仍在运行。
            self._main_thread.join(timeout=2.0)  # 等待主循环线程退出。
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():  # 如果心跳线程存在且仍在运行。
            self._heartbeat_thread.join(timeout=2.0)  # 等待心跳线程退出。
        self._safe_close()  # 关闭 PLC 连接。
        self.state = STATE_STOPPED  # 更新状态为已停止。
        log("自动通信已停止。")  # 输出停止日志。

    def pause(self) -> None:  # 定义人工暂停函数。
        self._pause_event.set()  # 设置暂停事件。
        log("自动通信已人工暂停。")  # 输出暂停日志。

    def resume(self) -> None:  # 定义恢复函数。
        self._pause_event.clear()  # 清除暂停事件。
        if self.state == STATE_PAUSED_ON_PLC_ACK_ERROR:  # 如果之前是 PLC 反馈异常暂停状态。
            self.state = STATE_WAIT_FIRST_TRIGGER  # 先简单恢复到等待首次触发状态。
        log("自动通信已恢复运行。")  # 输出恢复日志。

    def reset_cycle(self) -> None:  # 定义强制复位当前流程的函数。
        self._initialize_safe_outputs()  # 重新把算法输出区写为安全状态。
        self.last_first_trigger = 0  # 清首次触发边沿历史值。
        self.last_recheck_trigger = 0  # 清复拍触发边沿历史值。
        self.last_sent_result_status = RESULT_NONE  # 清上一轮结果状态。
        self.state = STATE_WAIT_FIRST_TRIGGER  # 回到等待首次触发状态。
        log("当前流程已强制复位到等待首次触发状态。")  # 输出复位日志。

    def _run_loop(self) -> None:  # 定义自动通信主循环。
        try:  # 尝试执行整个主循环流程。
            self.state = STATE_INIT  # 启动后先进入初始化状态。
            self._ensure_connected()  # 先确保 PLC 已连接。
            self._initialize_safe_outputs()  # 启动后先初始化输出区为安全状态。
            self.state = STATE_WAIT_FIRST_TRIGGER  # 初始化完成后进入等待首次触发状态。
            while not self._stop_event.is_set():  # 只要没有收到停止命令就一直循环。
                if self._pause_event.is_set():  # 如果当前被人工暂停。
                    time.sleep(self.poll_interval)  # 暂停期间只轻量等待，不做业务流程推进。
                    continue  # 继续下一次循环。
                snap = self._read_plc_snapshot()  # 读取 PLC 输入区最新快照。
                self._check_plc_heartbeat_timeout()  # 按当前配置检查 PLC 心跳是否超时。
                self._run_state_machine_once(snap)  # 根据当前状态和 PLC 快照推进一步状态机。
                time.sleep(self.poll_interval)  # 每轮循环后按设定周期稍作等待。
        except Exception as exc:  # 如果主循环中出现未处理异常。
            self._handle_fault(FAULT_CONNECT, f"主循环异常：{exc}")  # 统一进入故障处理。
        finally:  # 无论是否异常，最后都执行收尾动作。
            self._safe_close()  # 安全关闭 PLC 连接。

    def _heartbeat_loop(self) -> None:  # 定义算法心跳后台线程。
        while not self._stop_event.is_set():  # 只要没有收到停止命令就一直循环。
            if self._pause_event.is_set():  # 如果当前被人工暂停。
                time.sleep(self.heartbeat_period)  # 暂停期间也保留定期等待。
                continue  # 继续下一轮循环。
            if self.connected:  # 只有在 PLC 已连接时才尝试更新心跳。
                try:  # 尝试更新算法心跳。
                    self.algo_heartbeat_value += 1  # 将算法心跳值自增 1。
                    self.mb.write_int32(MD_ALGO_HEARTBEAT, self.algo_heartbeat_value)  # 把新心跳值写给 PLC。
                except Exception as exc:  # 如果更新心跳失败。
                    self._handle_fault(FAULT_WRITE, f"更新算法心跳失败：{exc}")  # 统一走故障处理。
            time.sleep(self.heartbeat_period)  # 每次更新后等待下一个心跳周期。

    def _run_state_machine_once(self, snap: dict[str, int]) -> None:  # 定义单步状态机推进函数。
        if self.state == STATE_WAIT_FIRST_TRIGGER:  # 如果当前在等待首次触发状态。
            if self._is_rising_edge(self.last_first_trigger, snap["first_trigger"]):  # 如果检测到首次触发从 0 跳到 1。
                self._emit_event("first_trigger_detected", {"value": snap["first_trigger"]})  # 向上层发送首次触发事件。
                self._set_busy(BUSY_WORKING)  # 告诉 PLC 算法开始忙碌。
                result = self._call_detect(task_type=TASK_FIRST_DETECT)  # 通过 JSON-RPC 调算法主程序执行首次检测。
                self._publish_detection_result(result)  # 按协议顺序把结果发布给 PLC。
                self.state = STATE_WAIT_PLC_ACK_AFTER_FIRST  # 状态切换为等待 PLC 对首次结果的反馈。
            self.last_first_trigger = snap["first_trigger"]  # 更新首次触发历史值，用于下一轮边沿检测。
            self.last_recheck_trigger = snap["recheck_trigger"]  # 同步更新复拍触发历史值。
            return  # 本轮处理结束直接返回。

        if self.state == STATE_WAIT_PLC_ACK_AFTER_FIRST:  # 如果当前在等待 PLC 对首次结果的反馈。
            if snap["coord_ack"] == ACK_OK:  # 如果 PLC 反馈当前这轮数据正常。
                self._clear_result_status()  # 按你最新定义，在 ACK_OK 后把结果状态清为 0。
                self._emit_event("plc_ack_ok", {"phase": "first", "status": self.last_sent_result_status})  # 发出 PLC 正常反馈事件。
                if self.last_sent_result_status == RESULT_NO_OBJECT:  # 如果上一轮结果是“当前区无异物”。
                    self._initialize_safe_outputs()  # 当前区结束，重新初始化输出区。
                    self.state = STATE_WAIT_FIRST_TRIGGER  # 回到等待下一轮首次触发状态。
                else:  # 如果上一轮结果还是有目标坐标可取。
                    self.state = STATE_WAIT_RECHECK_TRIGGER  # 进入等待复拍触发状态。
            elif snap["coord_ack"] == ACK_ERROR:  # 如果 PLC 反馈当前这轮数据异常。
                self._handle_plc_ack_error("first")  # 统一进入 PLC 反馈异常处理。
            self.last_recheck_trigger = snap["recheck_trigger"]  # 同步刷新复拍触发历史值。
            return  # 本轮处理结束直接返回。

        if self.state == STATE_WAIT_RECHECK_TRIGGER:  # 如果当前在等待复拍触发状态。
            if self._is_rising_edge(self.last_recheck_trigger, snap["recheck_trigger"]):  # 如果检测到复拍信号从 0 跳到 1。
                self._emit_event("recheck_trigger_detected", {"value": snap["recheck_trigger"]})  # 向上层发送复拍触发事件。
                self._set_busy(BUSY_WORKING)  # 告诉 PLC 算法再次开始忙碌。
                result = self._call_detect(task_type=TASK_RECHECK_DETECT)  # 通过 JSON-RPC 调算法主程序执行复拍检测。
                self._publish_detection_result(result)  # 按协议顺序把复拍结果发布给 PLC。
                self.state = STATE_WAIT_PLC_ACK_AFTER_RECHECK  # 状态切换为等待 PLC 对复拍结果的反馈。
            self.last_recheck_trigger = snap["recheck_trigger"]  # 更新复拍触发历史值，用于下一轮边沿检测。
            self.last_first_trigger = snap["first_trigger"]  # 同步更新首次触发历史值。
            return  # 本轮处理结束直接返回。

        if self.state == STATE_WAIT_PLC_ACK_AFTER_RECHECK:  # 如果当前在等待 PLC 对复拍结果的反馈。
            if snap["coord_ack"] == ACK_OK:  # 如果 PLC 反馈复拍结果正常。
                self._clear_result_status()  # 按你最新定义，在 ACK_OK 后把结果状态清为 0。
                self._emit_event("plc_ack_ok", {"phase": "recheck", "status": self.last_sent_result_status})  # 发出 PLC 正常反馈事件。
                if self.last_sent_result_status == RESULT_NO_OBJECT:  # 如果复拍结果说明当前区已经无异物。
                    self._initialize_safe_outputs()  # 当前区结束，重新初始化输出区。
                    self.state = STATE_WAIT_FIRST_TRIGGER  # 回到等待下一轮首次触发状态。
                else:  # 如果复拍后仍有目标需要继续流程。
                    self.state = STATE_WAIT_RECHECK_TRIGGER  # 继续等待下一次复拍触发。
            elif snap["coord_ack"] == ACK_ERROR:  # 如果 PLC 反馈复拍结果异常。
                self._handle_plc_ack_error("recheck")  # 统一进入 PLC 反馈异常处理。
            self.last_recheck_trigger = snap["recheck_trigger"]  # 更新复拍触发历史值。
            return  # 本轮处理结束直接返回。

        if self.state == STATE_PAUSED_ON_PLC_ACK_ERROR:  # 如果当前处于 PLC 反馈异常暂停状态。
            time.sleep(self.poll_interval)  # 此状态下只保持线程存活和心跳，不继续推进业务流程。
            return  # 本轮处理结束直接返回。

        if self.state == STATE_FAULT:  # 如果当前处于故障状态。
            time.sleep(self.poll_interval)  # 此状态下只保持线程存活，等待外部处理。
            return  # 本轮处理结束直接返回。

    def _call_detect(self, task_type: str) -> dict[str, Any]:  # 定义调用算法主程序检测接口的函数。
        self.task_seq += 1  # 把内部任务流水号递增 1。
        params = {  # 组装 JSON-RPC 调用参数。
            "task_id": self.task_seq,  # 写入当前任务编号。
            "task_type": task_type,  # 写入任务类型。
            "trigger_source": "MD500-501" if task_type == TASK_FIRST_DETECT else "MD504-505",  # 写入触发来源。
        }
        self._emit_event("rpc_call_started", params)  # 向上层发送 RPC 调用开始事件。
        try:  # 尝试通过 JSON-RPC 调算法主程序。
            result = self.rpc.call("detect_once", params)  # 调用算法主程序 detect_once 方法。
        except Exception as exc:  # 如果 JSON-RPC 调用失败。
            self._handle_fault(FAULT_RPC_ERROR, f"JSON-RPC 调用失败：{exc}")  # 统一进入 RPC 故障处理。
            raise  # 继续抛出异常让主循环终止当前流程。
        if not isinstance(result, dict):  # 如果算法主程序返回的不是字典对象。
            raise RuntimeError(f"JSON-RPC 返回结果类型错误：{type(result)}")  # 抛出异常提示返回类型不合法。
        self._emit_event("rpc_call_finished", {"task_id": self.task_seq, "task_type": task_type})  # 向上层发送 RPC 调用结束事件。
        return result  # 返回算法主程序的检测结果字典。

    def _ensure_connected(self) -> None:  # 定义确保 PLC 已连接的函数。
        if self.connected:  # 如果当前已经处于连接状态。
            return  # 直接返回，不重复连接。
        self.connected = self.mb.connect()  # 尝试建立与 PLC 的连接。
        if not self.connected:  # 如果连接失败。
            raise RuntimeError(f"连接 PLC 失败：{self.mb.host}:{self.mb.port}，unit_id={self.mb.unit_id}")  # 抛出异常交给上层处理。
        self._emit_event("plc_connected", {"ip": self.mb.host, "port": self.mb.port, "unit_id": self.mb.unit_id})  # 向上层发出 PLC 已连接事件。
        log(f"连接 PLC 成功：{self.mb.host}:{self.mb.port}，unit_id={self.mb.unit_id}")  # 输出连接成功日志。

    def _safe_close(self) -> None:  # 定义安全关闭连接的函数。
        if self.connected:  # 如果当前仍处于已连接状态。
            try:  # 尝试关闭底层连接。
                self.mb.close()  # 关闭底层 TCP 连接。
            finally:  # 无论关闭是否报错，都更新内部连接状态。
                self.connected = False  # 标记当前已经断开连接。
                self._emit_event("plc_disconnected", {})  # 向上层发出 PLC 断开连接事件。

    def _initialize_safe_outputs(self) -> None:  # 定义把算法输出区初始化为安全状态的函数。
        self._write_int32(MD_RESULT_STATUS, RESULT_NONE)  # 初始化结果状态为 0。
        self._write_float32(MD_TARGET_X, 0.0)  # 初始化 X 坐标为 0.0。
        self._write_float32(MD_TARGET_Y, 0.0)  # 初始化 Y 坐标为 0.0。
        self._write_float32(MD_TARGET_Z, 0.0)  # 初始化 Z 坐标为 0.0。
        self._write_float32(MD_TARGET_U, 0.0)  # 初始化 U 坐标为 0.0。
        self._write_int32(MD_ALGO_FAULT, FAULT_NONE)  # 初始化故障码为 0。
        self._write_int32(MD_ALGO_BUSY, BUSY_IDLE)  # 初始化忙碌状态为空闲。
        self._write_int32(MD_RETRY_COUNT, 0)  # 初始化当前目标挑取次数为 0。
        self._write_int32(MD_REMAIN_COUNT, 0)  # 初始化当前异物数量为 0。
        self._write_int32(MD_RESET_REQUEST, RESET_NONE)  # 初始化复位请求为 0。
        self.last_fault_code = FAULT_NONE  # 更新内部故障码缓存为无故障。
        self.last_sent_result_status = RESULT_NONE  # 更新内部最后发送状态为无新结果。
        log("算法输出区已初始化为安全状态。")  # 输出初始化完成日志。

    def _read_plc_snapshot(self) -> dict[str, int]:  # 定义读取 PLC 输入区快照的函数。
        try:  # 尝试读取 PLC 输入区。
            first_trigger = self.mb.read_int32(MD_FIRST_TRIGGER)  # 读取首次拍照触发值。
            coord_ack = self.mb.read_int32(MD_COORD_ACK)  # 读取 PLC 反馈结果正常/异常值。
            recheck_trigger = self.mb.read_int32(MD_RECHECK_TRIGGER)  # 读取复拍触发值。
            plc_heartbeat = self.mb.read_int32(MD_PLC_HEARTBEAT)  # 读取 PLC 心跳值。
        except Exception as exc:  # 如果读取 PLC 输入区失败。
            self._handle_fault(FAULT_READ, f"读取 PLC 输入区失败：{exc}")  # 统一进入故障处理。
            raise  # 把异常继续抛出，让上层主循环退出当前轮。
        self._update_plc_heartbeat_watch(plc_heartbeat)  # 更新 PLC 心跳监视信息。
        return {  # 返回当前 PLC 输入区快照字典。
            "first_trigger": first_trigger,  # 填入首次触发值。
            "coord_ack": coord_ack,  # 填入 PLC 反馈值。
            "recheck_trigger": recheck_trigger,  # 填入复拍触发值。
            "plc_heartbeat": plc_heartbeat,  # 填入 PLC 心跳值。
        }

    def _update_plc_heartbeat_watch(self, heartbeat_value: int) -> None:  # 定义更新 PLC 心跳监视信息的函数。
        if self.last_plc_heartbeat is None:  # 如果这是第一次读到 PLC 心跳。
            self.last_plc_heartbeat = heartbeat_value  # 先保存当前心跳值。
            self.last_plc_heartbeat_change_time = time.time()  # 记录当前时间为最近变化时间。
            return  # 本次处理结束。
        if heartbeat_value != self.last_plc_heartbeat:  # 如果当前 PLC 心跳与上一次不同。
            self.last_plc_heartbeat = heartbeat_value  # 更新为最新 PLC 心跳值。
            self.last_plc_heartbeat_change_time = time.time()  # 更新最近一次变化时间。

    def _check_plc_heartbeat_timeout(self) -> None:  # 定义检查 PLC 心跳是否超时的函数。
        if not self.enable_plc_heartbeat_check:  # 如果当前配置为不检查 PLC 心跳。
            return  # 直接跳过 PLC 心跳超时判断。
        if self.last_plc_heartbeat is None:  # 如果还没读到过 PLC 心跳。
            return  # 先不判断超时。
        if (time.time() - self.last_plc_heartbeat_change_time) > self.plc_heartbeat_timeout:  # 如果超过允许时间还没变化。
            self._handle_fault(FAULT_HEARTBEAT_TIMEOUT, "PLC 心跳超时")  # 进入 PLC 心跳超时故障处理。
            raise RuntimeError("PLC 心跳超时")  # 抛出异常让主循环尽快停止当前流程。

    def _set_busy(self, busy_value: int) -> None:  # 定义写算法忙碌状态的函数。
        self._write_int32(MD_ALGO_BUSY, busy_value)  # 把忙碌状态写给 PLC。

    def _clear_result_status(self) -> None:  # 定义清结果状态的函数。
        self._write_int32(MD_RESULT_STATUS, RESULT_NONE)  # 把 MD531-532 清为 0。
        self.last_sent_result_status = RESULT_NONE  # 更新内部最后发送结果状态为 0。
        log("结果状态已按规则清为 0000。")  # 输出结果状态清零日志。

    def _publish_detection_result(self, result: dict[str, Any]) -> None:  # 定义按协议顺序发布检测结果的函数。
        clean_result = self._validate_and_normalize_result(result)  # 先校验并标准化算法主程序返回的结果。
        self._write_int32(MD_ALGO_FAULT, clean_result["fault_code"])  # 先把业务故障码写给 PLC。
        self._write_int32(MD_REMAIN_COUNT, clean_result["remain_count"])  # 第一步：当前异物数量字段已停用，这里固定写 0 占位。
        self._write_int32(MD_RETRY_COUNT, clean_result["pick_retry_count"])  # 第二步：写当前目标挑取次数。
        self._write_float32(MD_TARGET_X, clean_result["x"])  # 第三步：写 X 坐标。
        self._write_float32(MD_TARGET_Y, clean_result["y"])  # 第三步：写 Y 坐标。
        self._write_float32(MD_TARGET_Z, clean_result["z"])  # 第三步：写固定或初始化后的 Z 值。
        self._write_float32(MD_TARGET_U, clean_result["u"])  # 第三步：写 U 坐标。
        self._write_int32(MD_RESULT_STATUS, clean_result["result_status"])  # 第四步：最后写结果状态。
        self._set_busy(BUSY_IDLE)  # 整个发布完成后再把算法忙碌状态写回空闲。
        self.last_sent_result_status = clean_result["result_status"]  # 记录本轮实际已发送给 PLC 的结果状态。
        self.last_fault_code = clean_result["fault_code"]  # 记录本轮业务故障码。
        self._emit_event("result_sent", clean_result)  # 向上层发送“结果已发送”事件。
        log(  # 输出结果发布日志。
            f"已发布结果：task_id={clean_result['task_id']}，task_type={clean_result['task_type']}，"
            f"algo_state={clean_result['state']}，pick_retry_count={clean_result['pick_retry_count']}，"
            f"x={clean_result['x']:.3f}，y={clean_result['y']:.3f}，z={clean_result['z']:.3f}，u={clean_result['u']:.3f}，"
            f"result_status={clean_result['result_status']}"
        )

    def _validate_and_normalize_result(self, result: dict[str, Any]) -> dict[str, Any]:  # 定义校验并标准化检测结果的函数。
        required_keys = [  # 定义算法主程序返回结果必须包含的字段列表。
            "task_id",  # 任务编号字段。
            "task_type",  # 任务类型字段。
            "state",  # 主程序返回的业务状态字符串字段。
        ]
        for key in required_keys:  # 逐个检查结果中是否存在所有必要字段。
            if key not in result:  # 如果缺少必要字段。
                raise ValueError(f"算法返回结果缺少字段：{key}")  # 抛出异常提示字段缺失。
        validate_int_value(result["task_id"], "task_id", 1)  # 校验任务编号必须为正整数。
        if result["task_type"] not in (TASK_FIRST_DETECT, TASK_RECHECK_DETECT):  # 如果任务类型不是允许值。
            raise ValueError(f"task_type 非法：{result['task_type']}")  # 抛出异常提示任务类型非法。
        if result["state"] not in VALID_ALGO_STATES:  # 如果主程序返回的状态字符串不在允许范围内。
            raise ValueError(f"state 非法：{result['state']}")  # 抛出异常提示状态字符串非法。
        result["fault_code"] = int(result.get("fault_code", FAULT_NONE))  # 若主程序未给故障码，则默认按无故障处理。
        validate_int_value(result["fault_code"], "fault_code", 0)  # 校验故障码必须为非负整数。
        result["remain_count"] = 0  # 当前异物数量字段已停用，这里固定写 0 占位。
        if result["state"] == STATE_NO_TARGET:  # 如果主程序明确返回当前视野无异物。
            result["pick_retry_count"] = 0  # 无异物时当前目标挑取次数固定写 0。
            result["result_status"] = RESULT_NO_OBJECT  # 无异物时结果状态写 2。
            result["x"] = 0.0  # 无异物时 X 写初始化值 0。
            result["y"] = 0.0  # 无异物时 Y 写初始化值 0。
            result["z"] = 0.0  # 无异物时 Z 写初始化值 0。
            result["u"] = 0.0  # 无异物时 U 写初始化值 0。
            return result  # 直接返回标准化后的无异物结果。
        for key in ("x", "y", "u"):  # 有目标时逐个检查主程序返回的坐标字段。
            if key not in result:  # 如果缺少必要坐标字段。
                raise ValueError(f"有目标时算法返回结果缺少字段：{key}")  # 抛出异常提示字段缺失。
        validate_coord_value(result["x"], "x")  # 校验 X 坐标合法性。
        validate_coord_value(result["y"], "y")  # 校验 Y 坐标合法性。
        validate_coord_value(result["u"], "u")  # 校验 U 坐标合法性。
        if result["state"] == STATE_NEW_TARGET:  # 如果当前是新异物坐标。
            result["pick_retry_count"] = 0  # 当前目标挑取次数写 0。
        elif result["state"] == STATE_RETRY_1:  # 如果当前是第一次复抓。
            result["pick_retry_count"] = 1  # 当前目标挑取次数写 1。
        elif result["state"] == STATE_RETRY_2:  # 如果当前是第二次复抓。
            result["pick_retry_count"] = 2  # 当前目标挑取次数写 2。
        result["result_status"] = RESULT_READY  # 只要有目标就给 PLC 写结果状态 1。
        result["z"] = FIXED_TARGET_Z  # 有目标时 Z 固定写 10.7。
        return result  # 返回校验和标准化后的结果对象。

    def _is_rising_edge(self, last_value: int, current_value: int) -> bool:  # 定义上升沿检测函数。
        return last_value == 0 and current_value == 1  # 只有从 0 跳到 1 才算有效边沿触发。

    def _write_int32(self, md_no: int, value: int) -> None:  # 定义带故障保护的 INT32 写入函数。
        try:  # 尝试写 INT32 到 PLC。
            self.mb.write_int32(md_no, value)  # 调用底层客户端执行写入。
        except Exception as exc:  # 如果写入失败。
            self._handle_fault(FAULT_WRITE, f"写入 INT32 失败：MD{md_no}，value={value}，error={exc}")  # 统一进入写入故障处理。
            raise  # 继续抛出异常让主循环停止当前流程。

    def _write_float32(self, md_no: int, value: float) -> None:  # 定义带故障保护的 FLOAT32 写入函数。
        try:  # 尝试写 FLOAT32 到 PLC。
            self.mb.write_float32(md_no, value)  # 调用底层客户端执行写入。
        except Exception as exc:  # 如果写入失败。
            self._handle_fault(FAULT_WRITE, f"写入 FLOAT32 失败：MD{md_no}，value={value}，error={exc}")  # 统一进入写入故障处理。
            raise  # 继续抛出异常让主循环停止当前流程。

    def _handle_plc_ack_error(self, phase: str) -> None:  # 定义 PLC 反馈异常时的统一处理函数。
        self._write_int32(MD_ALGO_FAULT, FAULT_PLC_ACK_ERROR)  # 先把 PLC 反馈异常故障码写给 PLC。
        self.last_fault_code = FAULT_PLC_ACK_ERROR  # 更新内部最近一次故障码缓存。
        self.state = STATE_PAUSED_ON_PLC_ACK_ERROR  # 把状态切换到 PLC 反馈异常暂停状态。
        self._emit_event("plc_ack_error", {"phase": phase})  # 向上层发出 PLC 反馈异常事件。
        log(f"PLC 反馈当前轮数据异常，已暂停流程：phase={phase}")  # 输出 PLC 反馈异常日志。

    def _handle_fault(self, fault_code: int, message: str) -> None:  # 定义统一故障处理函数。
        self.last_fault_code = fault_code  # 记录最近一次故障码。
        self.state = STATE_FAULT  # 把当前状态切换到故障状态。
        log(message)  # 输出故障日志，便于终端查看问题。
        if self.connected:  # 如果当前仍与 PLC 保持连接。
            try:  # 尝试把故障码写入 PLC。
                self.mb.write_int32(MD_ALGO_FAULT, fault_code)  # 将故障码写到 MD543-544。
            except Exception:  # 如果写故障码也失败。
                pass  # 这里不再抛异常，避免故障处理本身再次引发连锁异常。
        self._emit_event("fault", {"fault_code": fault_code, "message": message})  # 向上层发出统一故障事件。

    def _emit_event(self, event_type: str, payload: dict[str, Any]) -> None:  # 定义统一事件回调函数。
        if self.event_callback is None:  # 如果上层没有传入事件回调函数。
            return  # 直接返回，不做额外事件通知。
        try:  # 尝试调用上层提供的事件回调函数。
            self.event_callback(event_type, payload)  # 调用事件回调，把事件类型和内容传给上层。
        except Exception as exc:  # 如果事件回调本身抛异常。
            log(f"事件回调执行失败：event_type={event_type}，error={exc}")  # 只记日志，不影响主流程。


# ============================== 第9块：便捷工厂函数区 ==============================  # 说明这是给上层快速创建运行器的工厂函数区。


def build_auto_runner_rpc(event_callback: Optional[Callable[[str, dict[str, Any]], None]] = None) -> AutoModbusCamRpcRunner:  # 定义创建自动通信运行器的便捷工厂函数。
    return AutoModbusCamRpcRunner(event_callback=event_callback)  # 返回一个按默认现场参数构造好的自动通信运行器对象。


# ============================== 第10块：直接运行入口区 ==============================  # 说明这是直接运行脚本时的入口区。


if __name__ == "__main__":  # 如果当前脚本是直接运行而不是被 import。
    def demo_event_callback(event_type: str, payload: dict[str, Any]) -> None:  # 定义演示用事件回调函数。
        log(f"事件：{event_type}，payload={payload}")  # 把事件直接打印到终端，便于本地观察流程。

    runner = build_auto_runner_rpc(event_callback=demo_event_callback)  # 创建自动通信运行器对象。
    log("当前脚本为独立 JSON-RPC 自动通信进程。")  # 提示当前脚本定位。
    log(f"将通过 JSON-RPC 调用算法主程序：{RPC_URL}")  # 提示 RPC 服务地址。
    runner.start()  # 启动自动通信后台线程。
    try:  # 尝试让主线程保持存活。
        while True:  # 持续循环，直到用户手动停止。
            time.sleep(1.0)  # 每秒轻量等待一次，避免主线程退出。
    except KeyboardInterrupt:  # 如果用户按下 Ctrl+C。
        log("检测到 Ctrl+C，准备停止自动通信。")  # 提示即将停止程序。
    finally:  # 无论正常退出还是异常退出都执行收尾。
        runner.stop()  # 停止自动通信后台线程。
