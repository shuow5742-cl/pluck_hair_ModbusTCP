# JSON-RPC 对接简版（与当前代码一致）

## 1. 目标

算法主程序与 `ModbusTCP_auto_runner_rpc_state.py` 对接。
 主程序只负责：

- 接收一次 `detect_once` 请求
- 返回当前结果

PLC 通信、首拍/复拍流程、寄存器写入、固定 Z、状态翻译，全部由自动通信脚本负责。

------

## 2. 服务地址

- Host：`127.0.0.1`
- Port：`18080`
- Path：`/jsonrpc`

完整地址：

```
http://127.0.0.1:18080/jsonrpc
```

------

## 3. 必须实现的方法

### 3.1 `health`

#### 请求

```
{
  "jsonrpc": "2.0",
  "method": "health",
  "params": {},
  "id": 1
}
```

#### 返回

```
{
  "jsonrpc": "2.0",
  "result": {
    "ok": true
  },
  "id": 1
}
```

字段类型：

- `ok`：`bool`

------

### 3.2 `detect_once`

#### 请求（与当前代码一致）

```
{
  "jsonrpc": "2.0",
  "method": "detect_once",
  "params": {
    "task_id": 12,
    "task_type": "first_detect",
    "trigger_source": "MD500-501"
  },
  "id": 12
}
```

#### 请求字段类型

- `task_id`：`int`
- `task_type`：`string`
- `trigger_source`：`string`

说明：

- 自动通信脚本当前代码会实际发送这 3 个字段
- 主程序可以不依赖这些字段做业务判断
- 但需要能正常接收这个请求格式

------

## 4. 返回格式

### 4.1 最小必需返回

#### 有目标时

```
{
  "jsonrpc": "2.0",
  "result": {
    "x": 50.021,
    "y": 35.926,
    "u": 39.612,
    "state": "new_target"
  },
  "id": 12
}
```

#### 无目标时

```
{
  "jsonrpc": "2.0",
  "result": {
    "state": "no_target"
  },
  "id": 12
}
```

------

### 4.2 当前代码允许的扩展返回

主程序也可以额外返回这些字段：

- `task_id`
- `task_type`
- `fault_code`
- `message`

例如：

```
{
  "jsonrpc": "2.0",
  "result": {
    "task_id": 12,
    "task_type": "first_detect",
    "x": 50.021,
    "y": 35.926,
    "u": 39.612,
    "state": "new_target",
    "fault_code": 0,
    "message": ""
  },
  "id": 12
}
```

说明：

- **最小必需返回**：`x / y / u / state`
- **允许扩展返回**：`task_id / task_type / fault_code / message`
- 不返回 `fault_code / message` 也可以正常通信

------

## 5. 返回字段及数据类型

### 外层字段

- `jsonrpc`：`string`，固定值 `"2.0"`
- `result`：`object`
- `id`：必须与请求中的 `id` 一致

### `result` 内字段

#### 必填字段

- `state`：`string`

#### 有目标时必填

- `x`：`number`
- `y`：`number`
- `u`：`number`

#### 可选字段

- `task_id`：`int`
- `task_type`：`string`
- `fault_code`：`int`
- `message`：`string`

------

## 6. `state` 只允许 4 个值

- `new_target`：新异物坐标
- `retry_1`：第一次复抓
- `retry_2`：第二次复抓（第三次抓）
- `no_target`：当前视野没有异物

------

## 7. `no_target` 的返回要求

当 `state = "no_target"` 时，最小返回格式是：

```
{
  "jsonrpc": "2.0",
  "result": {
    "state": "no_target"
  },
  "id": 12
}
```

此时：

- 可以不返回 `x`
- 可以不返回 `y`
- 可以不返回 `u`

也允许额外返回：

- `task_id`
- `task_type`
- `fault_code`
- `message`

------

## 8. 自动通信脚本会自动处理的内容

主程序无需关心这些，自动通信脚本会自己处理：

- 首拍 / 复拍区分
- PLC 寄存器写入
- 结果状态翻译
- 挑取次数翻译
- 固定 `Z = 50.16`
- `no_target` 时 `X / Y / Z / U = 0`

对应关系：

- `new_target` → 结果状态 `1`，挑取次数 `0`
- `retry_1` → 结果状态 `1`，挑取次数 `1`
- `retry_2` → 结果状态 `1`，挑取次数 `2`
- `no_target` → 结果状态 `2`，`X/Y/Z/U` 全部发 `0`

------

## 9. 主程序实现要求

1. 方法名固定：
   - `health`
   - `detect_once`
2. 返回字段名固定使用：
   - `x`
   - `y`
   - `u`
   - `state`
3. `state` 只能返回：
   - `"new_target"`
   - `"retry_1"`
   - `"retry_2"`
   - `"no_target"`
4. `x / y / u` 必须返回数字类型，不要返回字符串
5. 主程序必须能接收 `detect_once` 的 `params` 中出现：
   - `task_id`
   - `task_type`
   - `trigger_source`
6. 主程序可以只返回最小字段，也可以额外返回：
   - `task_id`
   - `task_type`
   - `fault_code`
   - `message`

------

## 10. 一句话总结

**当前代码真实接口口径是：自动通信脚本调用 `detect_once` 时会带 `task_id / task_type / trigger_source`；主程序最少只需合法返回 `x / y / u / state`，也允许额外返回 `task_id / task_type / fault_code / message`。只要 `state` 合法，且有目标时 `x / y / u` 合法，自动通信流程即可正常完成。**