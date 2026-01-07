#!/bin/bash

# =======================================================
# 1. 全局配置
# =======================================================

# 基础 URL
API_BASE_URL="http://192.168.8.110:3002"

AUTH_TOKEN="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI" 

AUTH_HEADER="Authorization: $AUTH_TOKEN"

#清空数据
if [ "$1" = "all" ] ;then
    curl -X GET  "${API_BASE_URL}/api/v1/history/empty/transfer"  -H "$AUTH_HEADER"
    exit
fi

#默认清除50条 成功的数据
COUNT=${1:-50}
STATUS=${2:-true}  #true false
# 2. 函数定义：获取所有成功的ID
# =======================================================
function get_successful_ids() {
    echo "--- 正在执行: 获取成功的传输记录ID (最多 30 条) ---" >&2

    local GET_URL="${API_BASE_URL}/api/v1/history/transfer?page=1&count=${COUNT}&status=${STATUS}"
    local RESPONSE=$(curl -s -X GET "$GET_URL" -H "$AUTH_HEADER")
    local CURL_STATUS=$?

    if [ $CURL_STATUS -ne 0 ]; then
        echo "致命错误: GET 请求失败，请检查网络或 URL。Curl 状态码: $CURL_STATUS" >&2
        return 1
    fi

    # 1. 检查授权失败错误 (token校验不通过)
    # 假设授权失败的JSON总是包含 "detail" 字段
    local DETAIL_MSG=$(echo "$RESPONSE" | jq -r '.detail // empty')
    if [ -n "$DETAIL_MSG" ]; then
        echo "致命错误: API 授权失败！" >&2
        echo "服务器响应: $DETAIL_MSG" >&2
        echo "请检查脚本开头的 AUTH_TOKEN 是否正确且未过期。" >&2
        return 1
    fi

    # 2. 检查数据结构错误
    if ! echo "$RESPONSE" | jq -e '.data.list' >/dev/null 2>&1; then
        echo "错误: API 响应结构异常或不是有效 JSON。" >&2
        echo "原始响应 (用于调试): $RESPONSE" >&2
        return 1
    fi

    # 3. 正常解析并提取 ID 列表
    local SUCCESSFUL_IDS=$(echo "$RESPONSE" | jq -r '.data.list[] | select(.status == true) | .id')

    if [ -z "$SUCCESSFUL_IDS" ]; then
        echo "提示: 没有找到状态为 true 的记录ID。" >&2
    else
        echo "成功获取到以下 ID: $SUCCESSFUL_IDS" >&2
    fi

    echo "$SUCCESSFUL_IDS"
    return 0
}
# =======================================================
# 3. 函数定义：执行删除操作 (针对单个ID)
# =======================================================

# 功能: 对指定的单个 ID 执行删除 POST 请求
# 参数: $1 = 要删除的记录 ID
function delete_transfer_history() {
    local ID_TO_DELETE="$1"
    
    if [ -z "$ID_TO_DELETE" ]; then
        echo "错误: delete_transfer_history 函数缺少 ID 参数。" >&2
        return 1
    fi

    echo " -> 正在删除 ID: $ID_TO_DELETE"

    local DELETE_URL="${API_BASE_URL}/api/v1/history/transfer?deletesrc=false&deletedest=false"
    local JSON_BODY="{\"id\": $ID_TO_DELETE}"

    # 执行 POST 请求
    local DELETE_RESPONSE=$(curl -s -X DELETE \
        "$DELETE_URL" \
        -H "$AUTH_HEADER" \
        -H 'accept: application/json' \
        -H 'Content-Type: application/json' \
        -d "$JSON_BODY")
    
    if [ $? -ne 0 ]; then
        echo "错误: 删除 ID $ID_TO_DELETE 的请求失败。" >&2
        return 1
    fi
    
    # 注意：如果 API 返回成功的 JSON 消息，您可以在这里进行解析和打印。
    # 例如：echo "    API 响应: $DELETE_RESPONSE" 
    
#    echo " <- ID: $ID_TO_DELETE 删除请求已发送。"
    return 0
}

# =======================================================
# 4. 主执行逻辑
# =======================================================

# 检查依赖 (jq)
if ! command -v jq &> /dev/null; then
    echo "错误: 缺少依赖 'jq'。请先安装 jq。"
    exit 1
fi

# 调用函数获取 ID 列表
IDS_TO_DELETE=$(get_successful_ids)

# 检查是否获取到 ID
if [ -z "$IDS_TO_DELETE" ]; then
    echo "脚本结束，没有记录需要删除。"
    exit 0
fi

echo ""
echo "--- 正在循环执行删除操作 ---"

# 遍历 ID 列表，并逐一执行删除函数
for ID in $IDS_TO_DELETE; do
  delete_transfer_history "$ID"
done

echo ""
echo "--- 所有操作完成 ---"
