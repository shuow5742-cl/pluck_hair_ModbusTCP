#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # 指定源码编码为 UTF-8。

# ============================== 第1块：基础导入区 ==============================  # 说明这是基础导入区。

from __future__ import annotations  # 允许在类型注解中引用尚未定义的名称。

import json  # 导入 json，用于处理 JSON-RPC 请求和响应。
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # 导入内置 HTTP 服务类。
from typing import Any  # 导入 Any，用于类型标注。


# ============================== 第2块：统一配置区 ==============================  # 说明这是统一配置区。

HOST = "127.0.0.1"  # JSON-RPC 服务默认监听地址。
PORT = 18080  # JSON-RPC 服务默认监听端口。
RPC_PATH = "/jsonrpc"  # JSON-RPC 服务默认请求路径。

STATE_NEW_TARGET = "new_target"  # 主程序返回：当前是新异物坐标。
STATE_RETRY_1 = "retry_1"  # 主程序返回：当前是第一次复抓。
STATE_RETRY_2 = "retry_2"  # 主程序返回：当前是第二次复抓。
STATE_NO_TARGET = "no_target"  # 主程序返回：当前视野已经没有异物。
VALID_ALGO_STATES = [STATE_NEW_TARGET, STATE_RETRY_1, STATE_RETRY_2, STATE_NO_TARGET]  # 定义允许输入的状态字符串列表。

FAULT_NONE = 0  # 无故障。


# ============================== 第3块：公共工具函数区 ==============================  # 说明这是公共工具函数区。

def log(message: str) -> None:  # 定义统一日志输出函数。
    print(f"[algo_rpc_server_demo] {message}")  # 打印带统一前缀的日志。


def ask_int(prompt: str, default: int | None = None, min_value: int | None = None) -> int:  # 定义读取整数输入的函数。
    while True:  # 持续循环直到用户输入合法整数。
        raw = input(prompt).strip()  # 读取用户输入并去掉首尾空白。
        if raw == "" and default is not None:  # 如果用户直接回车且存在默认值。
            value = default  # 使用默认整数值。
        else:  # 如果用户输入了内容。
            try:  # 尝试把输入转换成整数。
                value = int(raw)  # 把输入文本转为 int。
            except ValueError:  # 如果转换失败。
                print("输入无效，请输入整数。")  # 提示用户重新输入。
                continue  # 继续下一轮循环。
        if min_value is not None and value < min_value:  # 如果设置了最小值且输入过小。
            print(f"输入不能小于 {min_value}。")  # 提示用户数值范围不合法。
            continue  # 继续下一轮循环。
        return value  # 返回校验通过的整数值。


def ask_float(prompt: str, default: float | None = None) -> float:  # 定义读取浮点数输入的函数。
    while True:  # 持续循环直到用户输入合法浮点数。
        raw = input(prompt).strip()  # 读取用户输入并去掉首尾空白。
        if raw == "" and default is not None:  # 如果用户直接回车且存在默认值。
            return float(default)  # 直接返回默认浮点值。
        try:  # 尝试把输入转换成浮点数。
            return float(raw)  # 返回用户输入的浮点数。
        except ValueError:  # 如果转换失败。
            print("输入无效，请输入数字。")  # 提示用户重新输入。


def ask_state() -> str:  # 定义读取状态字符串的函数。
    while True:  # 持续循环直到用户输入合法状态字符串。
        raw = input("请输入 state（new_target / retry_1 / retry_2 / no_target，默认 new_target）：").strip()  # 读取状态字符串输入。
        value = raw if raw else STATE_NEW_TARGET  # 如果用户直接回车，则使用默认状态 new_target。
        if value in VALID_ALGO_STATES:  # 如果输入状态属于允许范围。
            return value  # 返回合法状态字符串。
        print("state 只允许输入：new_target、retry_1、retry_2、no_target。")  # 提示用户状态字符串范围错误。


def make_jsonrpc_result(result: Any, rpc_id: Any) -> bytes:  # 定义构造 JSON-RPC 成功响应体的函数。
    payload = {"jsonrpc": "2.0", "result": result, "id": rpc_id}  # 组织 JSON-RPC 成功响应字典。
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")  # 把响应字典编码成 UTF-8 字节串。


def make_jsonrpc_error(code: int, message: str, rpc_id: Any) -> bytes:  # 定义构造 JSON-RPC 失败响应体的函数。
    payload = {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": rpc_id}  # 组织 JSON-RPC 错误响应字典。
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")  # 把响应字典编码成 UTF-8 字节串。


# ============================== 第4块：演示算法服务区 ==============================  # 说明这是演示算法服务区。

class DemoAlgoService:  # 定义演示算法服务类。
    def health(self) -> dict[str, Any]:  # 定义健康检查接口。
        return {  # 返回服务健康信息。
            "ok": True,  # 表示当前服务可用。
            "name": "algo_rpc_server_demo",  # 返回服务名。
            "version": "1.0",  # 返回当前版本号。
        }

    def detect_once(self, params: dict[str, Any]) -> dict[str, Any]:  # 定义单次检测接口。
        task_id = int(params.get("task_id", 0))  # 从参数中读取任务编号。
        task_type = str(params.get("task_type", ""))  # 从参数中读取任务类型。
        trigger_source = str(params.get("trigger_source", ""))  # 从参数中读取触发来源。
        log(f"收到 detect_once 调用：task_id={task_id}，task_type={task_type}，trigger_source={trigger_source}")  # 输出收到任务日志。

        print("\n================ JSON-RPC 手动填写检测结果 ================")  # 打印输入结果标题。
        print(f"当前任务编号：{task_id}")  # 显示当前任务编号。
        print(f"当前任务类型：{task_type}")  # 显示当前任务类型。
        print(f"触发来源：{trigger_source}")  # 显示当前触发来源。

        print("本版本主程序只返回 x / y / u / state，其他 PLC 通信字段由自动通信脚本自行翻译。")  # 提示当前版本的返回边界。
        state = ask_state()  # 读取主程序返回的状态字符串。
        result = {  # 先构造返回给自动通信进程的最小结果字典。
            "task_id": task_id,  # 回传当前任务编号。
            "task_type": task_type,  # 回传当前任务类型。
            "state": state,  # 回传当前状态字符串。
        }
        if state != STATE_NO_TARGET:  # 如果当前并不是“无异物”状态。
            x = ask_float("请输入 X（默认 100.0）：", default=100.0)  # 读取 X 坐标。
            y = ask_float("请输入 Y（默认 200.0）：", default=200.0)  # 读取 Y 坐标。
            u = ask_float("请输入 U（默认 0.0）：", default=0.0)  # 读取 U 姿态。
            result["x"] = x  # 回传 X 坐标。
            result["y"] = y  # 回传 Y 坐标。
            result["u"] = u  # 回传 U 姿态。
        else:  # 如果当前状态明确表示无异物。
            print("state=no_target 时不需要输入坐标，自动通信脚本会给 PLC 发送初始化坐标 0。")  # 提示当前无异物时无需输入坐标。
        fault_code = ask_int("请输入故障码 fault_code（默认 0）：", default=FAULT_NONE, min_value=0)  # 读取故障码。
        message = input("请输入备注 message（可留空）：").strip()  # 读取备注信息。
        result["fault_code"] = fault_code  # 回传故障码。
        result["message"] = message  # 回传备注信息。
        log(f"已返回检测结果：task_id={task_id}，task_type={task_type}，state={state}")  # 输出结果返回日志。
        return result  # 返回当前检测结果字典。


SERVICE = DemoAlgoService()  # 创建全局演示算法服务对象。


# ============================== 第5块：HTTP 处理器区 ==============================  # 说明这是 HTTP 请求处理器区。

class JsonRpcHandler(BaseHTTPRequestHandler):  # 定义 JSON-RPC HTTP 请求处理器类。
    server_version = "AlgoRpcDemo/1.0"  # 设置服务端版本号。

    def log_message(self, format: str, *args: Any) -> None:  # 覆盖默认 HTTP 访问日志函数。
        return  # 关闭默认 http.server 访问日志输出，避免终端噪声过多。

    def do_POST(self) -> None:  # 定义处理 POST 请求的函数。
        if self.path != RPC_PATH:  # 如果请求路径不是约定的 JSON-RPC 路径。
            self._send_response(404, b"Not Found", "text/plain; charset=utf-8")  # 返回 404。
            return  # 结束当前请求处理。

        content_length = int(self.headers.get("Content-Length", "0"))  # 读取请求体长度。
        raw_body = self.rfile.read(content_length)  # 读取原始请求体字节串。
        try:  # 尝试把请求体解析为 JSON。
            request_obj = json.loads(raw_body.decode("utf-8"))  # 把 UTF-8 请求体转成字典。
        except Exception as exc:  # 如果 JSON 解析失败。
            body = make_jsonrpc_error(-32700, f"Parse error: {exc}", None)  # 生成 JSON-RPC 解析错误响应。
            self._send_response(200, body, "application/json; charset=utf-8")  # 按 JSON-RPC 规范返回 200。
            return  # 结束当前请求处理。

        rpc_id = request_obj.get("id")  # 读取请求 id，便于响应时回传。
        method = request_obj.get("method")  # 读取请求方法名。
        params = request_obj.get("params", {})  # 读取请求参数，默认空字典。

        try:  # 尝试分发并执行具体 RPC 方法。
            if method == "health":  # 如果当前请求是健康检查方法。
                result = SERVICE.health()  # 调用健康检查接口。
            elif method == "detect_once":  # 如果当前请求是单次检测方法。
                if not isinstance(params, dict):  # 如果参数不是字典类型。
                    raise ValueError("detect_once 的 params 必须是对象字典")  # 抛出异常提示参数格式错误。
                result = SERVICE.detect_once(params)  # 调用单次检测接口。
            else:  # 如果方法名不在支持范围内。
                body = make_jsonrpc_error(-32601, f"Method not found: {method}", rpc_id)  # 生成方法不存在响应。
                self._send_response(200, body, "application/json; charset=utf-8")  # 返回 JSON-RPC 错误响应。
                return  # 结束当前请求处理。
            body = make_jsonrpc_result(result, rpc_id)  # 把方法返回结果包装成 JSON-RPC 成功响应。
            self._send_response(200, body, "application/json; charset=utf-8")  # 返回 JSON-RPC 成功响应。
        except Exception as exc:  # 如果 RPC 方法执行期间发生异常。
            body = make_jsonrpc_error(-32000, f"Server error: {exc}", rpc_id)  # 生成服务端错误响应。
            self._send_response(200, body, "application/json; charset=utf-8")  # 返回 JSON-RPC 错误响应。

    def do_GET(self) -> None:  # 定义处理 GET 请求的函数。
        if self.path == "/":  # 如果访问的是根路径。
            text = (  # 组织简单帮助文本。
                "algo_rpc_server_demo 正在运行。\n"
                f"JSON-RPC 地址：http://{HOST}:{PORT}{RPC_PATH}\n"
                "可用方法：health、detect_once\n"
            )
            self._send_response(200, text.encode("utf-8"), "text/plain; charset=utf-8")  # 返回帮助文本。
            return  # 结束当前请求处理。
        self._send_response(404, b"Not Found", "text/plain; charset=utf-8")  # 其他 GET 请求统一返回 404。

    def _send_response(self, status_code: int, body: bytes, content_type: str) -> None:  # 定义统一发送 HTTP 响应的函数。
        self.send_response(status_code)  # 发送 HTTP 状态码。
        self.send_header("Content-Type", content_type)  # 发送内容类型响应头。
        self.send_header("Content-Length", str(len(body)))  # 发送内容长度响应头。
        self.end_headers()  # 结束 HTTP 响应头。
        self.wfile.write(body)  # 把响应体字节串写回客户端。


# ============================== 第6块：启动入口区 ==============================  # 说明这是服务启动入口区。

def main() -> None:  # 定义主函数。
    server = ThreadingHTTPServer((HOST, PORT), JsonRpcHandler)  # 创建一个支持多线程的 HTTP 服务实例。
    log(f"JSON-RPC 演示服务已启动：http://{HOST}:{PORT}{RPC_PATH}")  # 输出服务启动地址。
    log("可用方法：health、detect_once")  # 输出当前支持的方法列表。
    log("收到 detect_once 后，会在终端里让你手动输入 x / y / u / state。")  # 提示当前演示服务的工作方式。
    try:  # 尝试持续运行 HTTP 服务。
        server.serve_forever()  # 启动服务主循环并持续监听请求。
    except KeyboardInterrupt:  # 如果用户按下 Ctrl+C。
        log("检测到 Ctrl+C，准备停止 JSON-RPC 服务。")  # 提示即将停止服务。
    finally:  # 无论正常退出还是异常退出都执行收尾。
        server.server_close()  # 关闭 HTTP 服务监听套接字。
        log("JSON-RPC 演示服务已停止。")  # 输出服务已停止日志。


if __name__ == "__main__":  # 如果当前脚本是直接运行而不是被 import。
    main()  # 执行服务启动入口。
