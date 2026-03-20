# JSON-RPC 对接简版（明确数据类型）

## 目标

算法主程序与 `ModbusTCP_auto_runner_rpc_state.py` 对接。
 主程序只负责：

- 收到一次请求
- 返回 `x / y / u / state`

PLC 通信、首拍/复拍流程、寄存器写入、固定 Z、状态翻译，全部由自动通信脚本负责。

------

## 服务地址

- Host：`127.0.0.1`
- Port：`18080`
- Path：`/jsonrpc`

完整地址：

```
http://127.0.0.1:18080/jsonrpc
```

------

## 必须实现的方法

### 1. `health`

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

#### 返回字段类型要求

- `ok`：必须为 `bool`

------

### 2. `detect_once`

#### 请求

```
{
  "jsonrpc": "2.0",
  "method": "detect_once",
  "params": {},
  "id": 2
}
```

主程序不需要关心首拍还是复拍，只要收到请求就返回当前结果。

------

## 返回格式

### 有目标时返回

```
{
  "jsonrpc": "2.0",
  "result": {
    "x": 50.021,
    "y": 35.926,
    "u": 39.612,
    "state": "new_target"
  },
  "id": 2
}
```

### 无目标时返回

```
{
  "jsonrpc": "2.0",
  "result": {
    "state": "no_target"
  },
  "id": 2
}
```

------

## 返回字段及数据类型要求

### 外层字段

- `jsonrpc`：必须为 `string`，固定值 `"2.0"`
- `result`：必须为 `object`
- `id`：必须与请求中的 `id` 类型和值一致
  - 请求是 `int`，返回也必须是 `int`
  - 请求是 `string`，返回也必须是 `string`

### `result` 内字段

#### 1. `state`

- 类型：必须为 `string`
- 必填：是

只允许以下 4 个固定值：

- `"new_target"`
- `"retry_1"`
- `"retry_2"`
- `"no_target"`

#### 2. `x`

- 类型：必须为 `number`
- 具体要求：必须为 JSON 数字类型
- 必填条件：当 `state != "no_target"` 时必填

#### 3. `y`

- 类型：必须为 `number`
- 具体要求：必须为 JSON 数字类型
- 必填条件：当 `state != "no_target"` 时必填

#### 4. `u`

- 类型：必须为 `number`
- 具体要求：必须为 JSON 数字类型
- 必填条件：当 `state != "no_target"` 时必填

------

## 明确禁止

以下返回方式不允许：

### 1. 坐标返回为字符串

```
{
  "x": "50.021",
  "y": "35.926",
  "u": "39.612",
  "state": "new_target"
}
```

### 2. `state` 返回为数字

```
{
  "x": 50.021,
  "y": 35.926,
  "u": 39.612,
  "state": 0
}
```

### 3. 改字段名

不允许把字段名改成：

- `X`
- `Y`
- `U`
- `status`
- `pos_x`
- `angle_u`

必须固定为：

- `x`
- `y`
- `u`
- `state`

------

## `state` 含义

- `new_target`：新异物坐标
- `retry_1`：第一次复抓
- `retry_2`：第二次复抓（第三次抓）
- `no_target`：当前视野没有异物

------

## `no_target` 返回要求

当 `state = "no_target"` 时，主程序返回格式必须是：

```
{
  "jsonrpc": "2.0",
  "result": {
    "state": "no_target"
  },
  "id": 2
}
```

此时：

- 不返回 `x`
- 不返回 `y`
- 不返回 `u`

------

## 自动通信脚本会自动处理的内容

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

## 主程序实现要求

1. 方法名固定：
   - `health`
   - `detect_once`
2. 返回字段名固定：
   - `x`
   - `y`
   - `u`
   - `state`
3. 返回字段类型固定：
   - `x`：`number`
   - `y`：`number`
   - `u`：`number`
   - `state`：`string`
4. `state` 只能返回：
   - `"new_target"`
   - `"retry_1"`
   - `"retry_2"`
   - `"no_target"`
5. `no_target` 时只能返回：
   - `state`

------

## 一句话总结

**主程序只要实现 `detect_once`，收到请求后按固定数据类型返回 `x(number) / y(number) / u(number) / state(string)`；当没有异物时只返回 `state="no_target"`。其他 PLC 通信和流程控制全部由 `ModbusTCP_auto_runner_rpc_state.py` 负责。**