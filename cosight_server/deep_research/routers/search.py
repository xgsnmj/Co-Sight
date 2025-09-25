# Copyright 2025 ZTE Corporation.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import json
import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Body
from starlette.requests import Request
from fastapi.responses import StreamingResponse
from urllib.parse import quote
from app.cosight.task.task_manager import TaskManager
from llm import llm_for_plan, llm_for_act, llm_for_tool, llm_for_vision
from cosight_server.deep_research.services.i18n_service import i18n
from cosight_server.deep_research.services.credibility_analyzer import credibility_analyzer
from app.common.logger_util import logger

# 引入CoSight所需的依赖
from app.cosight.task.plan_report_manager import plan_report_event_manager
from app.cosight.task.todolist import Plan
from CoSight import CoSight

searchRouter = APIRouter()

# 使用从环境变量获取的WORKSPACE_PATH
work_space_path = os.environ.get('WORKSPACE_PATH')
work_space_path = os.path.join(work_space_path, "work_space") if work_space_path else os.path.join(os.getcwd(), "work_space")
logger.info(f"Using work_space_path: {work_space_path}")
if not os.path.exists(work_space_path):
    os.makedirs(work_space_path)

# 确保logs目录存在
LOGS_PATH = os.path.join(work_space_path, 'plans')
if not os.path.exists(LOGS_PATH):
    os.makedirs(LOGS_PATH)


# 将本地文件路径转换为可被前端访问的URL
def _file_path_to_url(path_value: str) -> str:
    try:
        if not isinstance(path_value, str) or len(path_value) == 0:
            return path_value

        # 标准化分隔符，便于查找
        normalized = path_value.replace("\\", "/")

        # 只关心 work_space 之后的相对路径
        marker = "work_space/"
        idx = normalized.find(marker)
        if idx == -1:
            return path_value

        relative = normalized[idx:]  # 形如 work_space/work_space_2025.../xxx.md

        # 读取后端配置中的基础 API 前缀
        try:
            from cosight_server.sdk.common.config import custom_config
            base_url = str(custom_config.get("base_api_url"))
        except Exception:
            base_url = ""

        # 不对文件名进行编码，保持原始文件名
        # parts = relative.split("/")
        # if len(parts) >= 2:
        #     # 对文件名进行 quote，目录不编码
        #     if parts[-1]:
        #         parts[-1] = quote(parts[-1])
        #     relative = "/".join(parts)

        return f"{base_url}/{relative}"
    except Exception:
        return path_value


def _rewrite_paths_in_payload(payload):
    """递归遍历对象，将包含 work_space 的本地路径替换为 URL。"""
    try:
        if isinstance(payload, dict):
            new_obj = {}
            for k, v in payload.items():
                # 针对文件操作事件结构进行特殊处理
                if k == "file_path" and isinstance(v, str):
                    new_obj[k] = _file_path_to_url(v)
                else:
                    new_obj[k] = _rewrite_paths_in_payload(v)
            return new_obj
        elif isinstance(payload, list):
            return [_rewrite_paths_in_payload(item) for item in payload]
        elif isinstance(payload, str):
            # 尝试把 JSON 字符串解出来再处理
            try:
                obj = json.loads(payload)
                return json.dumps(_rewrite_paths_in_payload(obj), ensure_ascii=False)
            except Exception:
                return _file_path_to_url(payload)
        else:
            return payload
    except Exception:
        return payload

async def _trigger_credibility_analysis(plan_queue, plan_data: Plan, completed_step: str):
    """触发可信分析"""
    try:
        logger.info(f"开始可信分析: {completed_step}")
        
        # 获取当前步骤信息
        current_step = {
            "title": completed_step,
            "content": plan_data.step_details.get(completed_step, ""),
            "status": "completed"
        }
        
        # 获取所有已完成的步骤
        all_completed_steps = []
        for step, status in plan_data.step_statuses.items():
            if status == 'completed':
                all_completed_steps.append({
                    "title": step,
                    "content": plan_data.step_details.get(step, ""),
                    "status": status
                })
        
        # 获取工具事件（从step_tool_calls中提取）
        tool_events = []
        if hasattr(plan_data, 'step_tool_calls'):
            for step, tool_calls in plan_data.step_tool_calls.items():
                if step == completed_step:  # 只分析当前步骤的工具调用
                    for tool_call in tool_calls:
                        tool_events.append({
                            "tool_name": tool_call.get("tool_name", ""),
                            "tool_args": tool_call.get("tool_args", ""),
                            "timestamp": tool_call.get("timestamp", "")
                        })
        
        # 调用可信分析器
        credibility_result = await credibility_analyzer.analyze_step_credibility(
            current_step, all_completed_steps, tool_events
        )
        
        if credibility_result:
            # 格式化可信分析消息
            # 计算步骤索引
            try:
                step_index = list(plan_data.steps).index(completed_step) if hasattr(plan_data, 'steps') else None
            except ValueError:
                step_index = None
            credibility_message = credibility_analyzer.format_credibility_message(
                credibility_result, completed_step, step_index
            )
            
            # 将可信分析消息放入队列
            if plan_queue is not None:
                await plan_queue.put(credibility_message)
                try:
                    import json as _json
                    payload_len = len(_json.dumps(credibility_message, ensure_ascii=False))
                except Exception:
                    payload_len = -1
                logger.info(f"可信分析完成，已推送到队列 step={completed_step}, bytes~={payload_len}")
                
                # 可信分析完成后，主动检查并继续执行下一步骤
                await _check_and_continue_next_step(plan_queue, plan_data)
        else:
            logger.info(f"可信分析无结果: {completed_step}")
            # 即使没有可信分析结果，也要检查下一步骤
            await _check_and_continue_next_step(plan_queue, plan_data)
        
    except Exception as e:
        logger.error(f"可信分析失败: {e}", exc_info=True)
        # 可信分析失败时，也要检查下一步骤
        await _check_and_continue_next_step(plan_queue, plan_data)

async def _check_and_continue_next_step(plan_queue, plan_data: Plan):
    """检查并继续执行下一个步骤"""
    try:
        logger.info(f"检查下一步骤，当前计划状态: {plan_data.step_statuses}")
        
        # 获取所有可执行的步骤
        ready_steps = plan_data.get_ready_steps()
        logger.info(f"找到可执行的步骤: {ready_steps}")
        
        if ready_steps:
            logger.info(f"发现 {len(ready_steps)} 个可执行步骤，但等待主循环自然处理")
            # 不立即标记步骤为进行中，让主循环自然处理
            # 这样可以避免并发执行时的状态冲突
        else:
            logger.info("没有找到可执行的步骤，计划可能已完成或阻塞")
            
    except Exception as e:
        logger.error(f"检查下一步骤失败: {e}", exc_info=True)

def append_create_plan(data: Any):
    """
    将数据追加写入LOGS_PATH下的plan.log文件，并将数据放入队列以发送给客户端

    Args:
        data: 要写入的数据（支持字典、列表等可JSON序列化的类型）
    """
    try:
        # 使用LOGS_PATH构建文件路径
        file_path = Path(LOGS_PATH) / "plan.log"

        # 处理Plan对象转换为可序列化的dict
        if isinstance(data, Plan):
            plan_dict = {
                "title": data.title if hasattr(data, 'title') else "",
                "steps": data.steps if hasattr(data, 'steps') else [],
                "step_files": data.step_files if hasattr(data, 'step_files') else {},
                "step_statuses": data.step_statuses if hasattr(data, 'step_statuses') else {},
                "step_notes": data.step_notes if hasattr(data, 'step_notes') else {},
                "step_details": data.step_details if hasattr(data, 'step_details') else {},
                "step_tool_calls": data.step_tool_calls if hasattr(data, 'step_tool_calls') else {},
                "dependencies": {str(k): v for k, v in data.dependencies.items()} if hasattr(data,
                                                                                             'dependencies') else {},
                "progress": data.get_progress() if hasattr(data, 'get_progress') and callable(
                    data.get_progress) else {},
                "result": data.get_plan_result() if hasattr(data, 'get_plan_result') and callable(
                    data.get_plan_result) else ""
            }
            logger.info(f"step_files:{data.step_files}")

            # logger.info(f"Plan对象已转换为字典: {plan_dict}")
            data = plan_dict
        # 处理工具事件数据
        elif isinstance(data, dict) and data.get("event_type") in ["tool_start", "tool_complete", "tool_error"]:
            # 在推送前，将事件中的文件系统路径改写为可访问的 URL
            data = _rewrite_paths_in_payload(data)
            logger.info(f"Tool event: {data.get('event_type')} for {data.get('tool_name')}")

        # 准备写入内容（自动处理不同类型）
        if isinstance(data, (dict, list)):
            try:
                content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            except TypeError as e:
                logger.error(f"JSON序列化失败，尝试转换对象: {e}", exc_info=True)
                # 尝试将复杂对象转换为字符串
                if isinstance(data, dict):
                    serializable_data = {k: str(v) for k, v in data.items()}
                elif isinstance(data, list):
                    serializable_data = [
                        str(item) if not isinstance(item, (dict, list, str, int, float, bool, type(None))) else item for
                        item in data]
                content = json.dumps(serializable_data, ensure_ascii=False, indent=2) + "\n"
        else:
            content = str(data) + "\n"

        # 记录序列化后的内容到日志
        # logger.info(f"序列化后的Plan数据: {content.strip()}")

        # 追加写入文件（自动创建文件）
        with open(file_path, mode='a', encoding='utf-8') as f:
            f.write(content)

        # 将数据放入队列以便流式发送 - 使用run_coroutine_threadsafe
        global plan_queue, main_loop, analyzed_steps
        if plan_queue is not None and main_loop is not None:
            # 确保队列中的数据是可JSON序列化的
            if isinstance(data, Plan):
                # 已经在上面转换过了
                asyncio.run_coroutine_threadsafe(plan_queue.put(plan_dict), main_loop)
                
                # 检查是否有新完成的步骤，触发可信分析
                if hasattr(data, 'step_statuses'):
                    logger.info(f"Plan步骤状态: {data.step_statuses}")
                    for step, status in data.step_statuses.items():
                        logger.info(f"检查步骤: {step}, 状态: {status}, 已分析: {step in analyzed_steps}")
                        if status == 'completed' and step not in analyzed_steps:
                            # 标记为已分析
                            analyzed_steps.add(step)
                            # 异步触发可信分析
                            asyncio.run_coroutine_threadsafe(
                                _trigger_credibility_analysis(plan_queue, data, step), 
                                main_loop
                            )
                            logger.info(f"触发可信分析: {step}")
            else:
                asyncio.run_coroutine_threadsafe(plan_queue.put(data), main_loop)

    except json.JSONDecodeError as e:
        logger.error(f"JSON序列化失败: {e}", exc_info=True)
    except IOError as e:
        logger.error(f"文件写入失败: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"未知错误: {e}", exc_info=True)


def validate_search_input(params: dict) -> dict | None:
    """
    验证搜索输入参数
    Args:
        params: 输入参数字典
    Returns:
        如果验证失败返回错误响应，验证通过返回None
    """
    if not (content := params.get('content')) or len(content) == 0:
        return {
            "contentType": "multi-modal",
            "content": [{"type": "text", "value": i18n.t('invalid_command')}],
            "promptSentences": []
        }
    return None


@searchRouter.post("/deep-research/search")
async def search(request: Request, params: Any = Body(None)):
    logger.info(f"=====params:{params}")

    # if not await session_manager.authority(request):
    #     raise HTTPException(status_code=403, detail="Forbidden")

    if result := validate_search_input(params):
        return result

    session_info = params.get("sessionInfo", {})
    plan_id = session_info.get("messageSerialNumber", "")
    if not plan_id:
        # 退化方案：使用时间戳，建议前端传稳定ID
        plan_id = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    # 获取查询内容
    content_array = params.get('content', [])
    query_content = content_array[0]['value'] if content_array and isinstance(
        content_array, list) and len(content_array) > 0 and 'value' in content_array[0] else ""

    # 规划每个 plan 的持久化文件
    plan_log_path = os.path.join(LOGS_PATH, f"{plan_id}.log")
    plan_final_path = os.path.join(LOGS_PATH, f"{plan_id}.final.json")

    async def generator_func():
        # 清空之前可能存在的队列数据并保存当前事件循环
        plan_queue = asyncio.Queue()
        main_loop = asyncio.get_running_loop()

        # 保存最新的plan数据（仅非工具事件）
        latest_plan = None
        # 本次会话内已触发可信分析的步骤集合，避免重复分析
        analyzed_steps_local = set()

        def append_create_plan_local(data: Any):
            """
            将数据追加写入LOGS_PATH下按 plan_id 的文件，并将数据放入队列以发送给客户端

            Args:
                data: 要写入的数据（支持字典、列表等可JSON序列化的类型）
            """
            try:
                # 针对当前 plan 的日志文件
                file_path = Path(plan_log_path)

                # 处理Plan对象转换为可序列化的dict
                if isinstance(data, Plan):
                    plan_obj = data
                    plan_dict = {
                        "title": plan_obj.title if hasattr(plan_obj, 'title') else "",
                        "steps": plan_obj.steps if hasattr(plan_obj, 'steps') else [],
                        "step_files": plan_obj.step_files if hasattr(plan_obj, 'step_files') else {},
                        "step_statuses": plan_obj.step_statuses if hasattr(plan_obj, 'step_statuses') else {},
                        "step_notes": plan_obj.step_notes if hasattr(plan_obj, 'step_notes') else {},
                        "step_details": plan_obj.step_details if hasattr(plan_obj, 'step_details') else {},
                        "step_tool_calls": plan_obj.step_tool_calls if hasattr(plan_obj, 'step_tool_calls') else {},
                        "dependencies": {str(k): v for k, v in plan_obj.dependencies.items()} if hasattr(plan_obj,
                                                                                                     'dependencies') else {},
                        "progress": plan_obj.get_progress() if hasattr(plan_obj, 'get_progress') and callable(
                            data.get_progress) else {},
                        "result": plan_obj.get_plan_result() if hasattr(plan_obj, 'get_plan_result') and callable(
                            data.get_plan_result) else ""
                    }
                    logger.info(f"step_files:{plan_obj.step_files}")

                    # logger.info(f"Plan对象已转换为字典: {plan_dict}")
                    data = plan_dict

                    # 检查是否有新完成的步骤，触发可信分析（仅对当前会话内未分析的步骤触发一次）
                    try:
                        if hasattr(plan_obj, 'step_statuses'):
                            for step, status in plan_obj.step_statuses.items():
                                if status == 'completed' and step not in analyzed_steps_local:
                                    analyzed_steps_local.add(step)
                                    asyncio.run_coroutine_threadsafe(
                                        _trigger_credibility_analysis(plan_queue, plan_obj, step),
                                        main_loop
                                    )
                                    logger.info(f"触发可信分析(本地队列): {step}")
                    except Exception as _e:
                        logger.error(f"触发可信分析失败: {_e}", exc_info=True)
                # 处理工具事件数据
                elif isinstance(data, dict) and data.get("event_type") in ["tool_start", "tool_complete", "tool_error"]:
                    # 对工具事件进行路径改写（包括嵌套 plan.processed_result.file_path 等）
                    try:
                        data = _rewrite_paths_in_payload(data)
                    except Exception:
                        pass
                    logger.info(f"Tool event: {data.get('event_type')} for {data.get('tool_name')}")

                # 准备写入内容（自动处理不同类型）
                if isinstance(data, (dict, list)):
                    try:
                        content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
                    except TypeError as e:
                        logger.error(f"JSON序列化失败，尝试转换对象: {e}", exc_info=True)
                        # 尝试将复杂对象转换为字符串
                        if isinstance(data, dict):
                            serializable_data = {k: str(v) for k, v in data.items()}
                        elif isinstance(data, list):
                            serializable_data = [str(item) if not isinstance(item, (
                            dict, list, str, int, float, bool, type(None))) else item for item in data]
                        content = json.dumps(serializable_data, ensure_ascii=False, indent=2) + "\n"
                else:
                    content = str(data) + "\n"

                # 追加写入当前 plan 的日志
                with open(file_path, mode='a', encoding='utf-8') as f:
                    f.write(content)

                # 如果包含最终结果，单独落盘 final 文件
                try:
                    if isinstance(data, dict) and data.get("result"):
                        with open(plan_final_path, mode='w', encoding='utf-8') as ff:
                            ff.write(json.dumps(data, ensure_ascii=False, indent=2))
                except Exception as _:
                    pass

                # 将数据放入队列以便流式发送
                if plan_queue is not None and main_loop is not None:
                    if isinstance(data, Plan):
                        asyncio.run_coroutine_threadsafe(plan_queue.put(plan_dict), main_loop)
                    else:
                        # 非Plan（包括工具事件）在入队前再做一次路径改写兜底
                        safe_data = _rewrite_paths_in_payload(data)
                        asyncio.run_coroutine_threadsafe(plan_queue.put(safe_data), main_loop)

            except json.JSONDecodeError as e:
                logger.error(f"JSON序列化失败: {e}", exc_info=True)
            except IOError as e:
                logger.error(f"文件写入失败: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"未知错误: {e}", exc_info=True)

        # 如果已存在最终结果，且当前不在运行，直接回放并结束
        try:
            if not TaskManager.is_running(plan_id) and os.path.exists(plan_final_path):
                with open(plan_final_path, 'r', encoding='utf-8') as rf:
                    final_obj = json.load(rf)
                final_obj = dict(final_obj)
                final_obj["status_text"] = "执行完成"
                yield {"plan": final_obj}
                return
            # 若存在历史日志且不在运行，回放日志后结束
            if not TaskManager.is_running(plan_id) and os.path.exists(plan_log_path):
                with open(plan_log_path, 'r', encoding='utf-8') as lf:
                    for line in lf:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        # 工具事件透传
                        if isinstance(obj, dict) and obj.get("event_type") in ["tool_start", "tool_complete", "tool_error"]:
                            yield {"plan": obj}
                        else:
                            yield {"plan": obj}
                return
        except Exception as _:
            # 回放失败时忽略，继续后续逻辑
            pass

        # 在子线程中执行CoSight任务（若未在运行）
        def run_manus():
            try:
                # 订阅事件，关联plan_id
                plan_report_event_manager.subscribe("plan_created", plan_id, append_create_plan_local)
                plan_report_event_manager.subscribe("plan_updated", plan_id, append_create_plan_local)
                plan_report_event_manager.subscribe("plan_process", plan_id, append_create_plan_local)
                plan_report_event_manager.subscribe("plan_result", plan_id, append_create_plan_local)
                plan_report_event_manager.subscribe("tool_event",plan_id, append_create_plan_local)

                # 构造路径：/xxx/xxx/work_space/work_space_时间戳
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                work_space_path_time = os.path.join(work_space_path, f'work_space_{timestamp}')
                print(f"work_space_path_time:{work_space_path_time}")
                os.makedirs(work_space_path_time, exist_ok=True)
                # 避免进程级环境变量被并发覆盖，优先通过参数传递
                os.environ['WORKSPACE_PATH'] = work_space_path_time

                # 初始化CoSight并传入plan_id
                logger.info(f"llm is {llm_for_plan.model}, {llm_for_plan.base_url}, {llm_for_plan.api_key}")
                cosight = CoSight(
                    llm_for_plan,
                    llm_for_act,
                    llm_for_tool,
                    llm_for_vision,
                    work_space_path=work_space_path_time,
                    message_uuid = plan_id
                )
                result = cosight.execute(query_content)
                logger.info(f"final result is {result}")

            except Exception as e:
                logger.error(f"CoSight执行错误: {e}", exc_info=True)
            finally:
                # 执行完成后取消订阅
                plan_report_event_manager.unsubscribe("plan_created", plan_id, append_create_plan_local)
                plan_report_event_manager.unsubscribe("plan_updated", plan_id, append_create_plan_local)
                plan_report_event_manager.unsubscribe("plan_process", plan_id, append_create_plan_local)
                plan_report_event_manager.unsubscribe("plan_result", plan_id, append_create_plan_local)
                plan_report_event_manager.unsubscribe("tool_event", plan_id, append_create_plan_local)
                # 清理TaskManager中的映射与运行态
                TaskManager.mark_completed(plan_id)
                TaskManager.remove_plan(plan_id)

        # 幂等：若已在运行，仅订阅并复用已有执行；否则启动新执行
        if TaskManager.is_running(plan_id):
            # 仅订阅，将当前请求的队列作为新的监听者
            plan_report_event_manager.subscribe("plan_created", plan_id, append_create_plan_local)
            plan_report_event_manager.subscribe("plan_updated", plan_id, append_create_plan_local)
            plan_report_event_manager.subscribe("plan_process", plan_id, append_create_plan_local)
            plan_report_event_manager.subscribe("plan_result", plan_id, append_create_plan_local)
            plan_report_event_manager.subscribe("tool_event", plan_id, append_create_plan_local)
        else:
            TaskManager.mark_running(plan_id)
            import threading
            thread = threading.Thread(target=run_manus)
            thread.daemon = True
            thread.start()

        # 持续从队列获取数据并产生响应
        last_plan_fingerprint = None  # 避免相同计划重复发送
        emitted_credibility_keys = set()  # 避免同一步骤的可信分析重复发送
        while True:
            try:
                # 等待队列中的数据，设置超时防止无限等待
                data = await asyncio.wait_for(plan_queue.get(), timeout=60.0)
                # logger.info(f"queue_data:{data}")

                # 若为可信分析事件，直接透传，避免被包装为 plan
                if isinstance(data, dict) and data.get("type") in ("credibility-analysis", "lui-message-credibility-analysis"):
                    try:
                        cred_key = f"{data.get('type')}|{data.get('stepTitle')}|{data.get('stepIndex')}"
                    except Exception:
                        cred_key = None
                    if cred_key is None or cred_key not in emitted_credibility_keys:
                        if cred_key is not None:
                            emitted_credibility_keys.add(cred_key)
                        yield data
                    continue

                # 兼容：可信分析被包裹在 plan 中
                if (
                    isinstance(data, dict)
                    and isinstance(data.get("plan"), dict)
                    and data["plan"].get("type") in ("credibility-analysis", "lui-message-credibility-analysis")
                ):
                    yield data["plan"]
                    continue

                # 工具事件（裸 dict），直接透传且不更新latest_plan（避免保活重复发送工具事件）
                if isinstance(data, dict) and data.get("event_type") in ["tool_start", "tool_complete", "tool_error"]:
                    yield {"plan": data}
                    continue

                # 计划结果完成
                if isinstance(data, dict) and "result" in data and data['result']:
                    latest_plan = data
                    completed_plan = dict(latest_plan)
                    completed_plan["statusText"] = "执行完成"
                    yield {"plan": completed_plan}
                    break

                # 更新最新plan数据（非工具事件）
                latest_plan = data
                running_plan = dict(latest_plan) if isinstance(latest_plan, dict) else latest_plan
                if isinstance(running_plan, dict):
                    running_plan["statusText"] = "正在执行中"
                # 发送完整的plan（去重）
                try:
                    import hashlib as _hashlib
                    plan_fp = _hashlib.md5(json.dumps(running_plan, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest() if isinstance(running_plan, dict) else None
                except Exception:
                    plan_fp = None
                if plan_fp is None or plan_fp != last_plan_fingerprint:
                    last_plan_fingerprint = plan_fp
                    yield {"plan": running_plan}

            except asyncio.TimeoutError:
                # 超时，仅发送保活状态。若有最新非工具计划，则基于其发送；否则发送默认等待计划
                if latest_plan and isinstance(latest_plan, dict):
                    waiting_plan = dict(latest_plan)
                    waiting_plan["statusText"] = "等待计划更新..."
                    try:
                        import hashlib as _hashlib
                        plan_fp = _hashlib.md5(json.dumps(waiting_plan, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
                    except Exception:
                        plan_fp = None
                    if plan_fp is None or plan_fp != last_plan_fingerprint:
                        last_plan_fingerprint = plan_fp
                        yield {"plan": waiting_plan}
                else:
                    contains_chinese = any('\u4e00' <= c <= '\u9fff' for c in query_content)
                    title = "等待任务执行" if contains_chinese else "Waiting for task execution"
                    default_plan = {"title": title, "statusText": "等待计划更新...", "steps": []}
                    try:
                        import hashlib as _hashlib
                        plan_fp = _hashlib.md5(json.dumps(default_plan, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
                    except Exception:
                        plan_fp = None
                    if plan_fp is None or plan_fp != last_plan_fingerprint:
                        last_plan_fingerprint = plan_fp
                        yield {"plan": default_plan}
            except Exception as e:
                logger.error(f"生成响应错误: {e}", exc_info=True)
                # 发送错误状态，但保留最新plan
                if latest_plan and isinstance(latest_plan, dict):
                    error_plan = dict(latest_plan)
                    error_plan["statusText"] = f"生成响应出错: {str(e)}"
                    yield {"plan": error_plan}
                else:
                    yield {"plan": {"title": "任务出错", "statusText": f"生成响应出错: {str(e)}", "steps": []}}
                break

    async def generate_stream_response(generator_func, params):
        try:
            async for response_data in generator_func():
                # 可信分析事件优先匹配
                if isinstance(response_data, dict) and response_data.get("type") in ("credibility-analysis", "lui-message-credibility-analysis"):
                    try:
                        logger.info("发送可信分析消息到前端")
                    except Exception:
                        pass
                    response_json = {
                        "contentType": "lui-message-credibility-analysis",
                        "sessionInfo": params.get("sessionInfo", {}),
                        "code": 0,
                        "message": "ok",
                        "task": "credibility_analysis",
                        "changeType": "append",
                        "content": response_data
                    }
                # 工具事件（被包裹在plan中），注意空值判断
                elif (
                    isinstance(response_data, dict)
                    and isinstance(response_data.get("plan"), dict)
                    and response_data.get("plan", {}).get("event_type") in ["tool_start", "tool_complete", "tool_error"]
                ):
                    try:
                        logger.info("发送工具事件到前端")
                    except Exception:
                        pass
                    response_json = {
                        "contentType": "lui-message-tool-event",
                        "sessionInfo": params.get("sessionInfo", {}),
                        "code": 0,
                        "message": "ok",
                        "task": "tool_event",
                        "changeType": "append",
                        "content": response_data
                    }
                # 兼容：若包裹在 plan 中的也是可信分析，则拆包成可信分析消息
                elif (
                    isinstance(response_data, dict)
                    and isinstance(response_data.get("plan"), dict)
                    and response_data["plan"].get("type") in ("credibility-analysis", "lui-message-credibility-analysis")
                ):
                    try:
                        logger.info("发送plan内可信分析消息到前端")
                    except Exception:
                        pass
                    response_json = {
                        "contentType": "lui-message-credibility-analysis",
                        "sessionInfo": params.get("sessionInfo", {}),
                        "code": 0,
                        "message": "ok",
                        "task": "credibility_analysis",
                        "changeType": "append",
                        "content": response_data["plan"]
                    }
                elif isinstance(response_data, dict) and "plan" in response_data:
                    # 计划事件使用原有的contentType
                    try:
                        logger.info("发送计划进度到前端")
                    except Exception:
                        pass
                    response_json = {
                        "contentType": "lui-message-manus-step",
                        "sessionInfo": params.get("sessionInfo", {}),
                        "code": 0,
                        "message": "ok",
                        "task": "chat",
                        "changeType": "replace",
                        "content": response_data["plan"]  # 直接使用plan数据作为content
                    }
                else:
                    # 其他类型的数据，可能是直接的Plan对象或其他格式
                    try:
                        logger.info("发送兜底消息到前端")
                    except Exception:
                        pass
                    response_json = {
                        "contentType": "lui-message-manus-step",
                        "sessionInfo": params.get("sessionInfo", {}),
                        "code": 0,
                        "message": "ok",
                        "task": "chat",
                        "changeType": "replace",
                        "content": response_data  # 直接使用数据作为content
                    }

                yield json.dumps(response_json, ensure_ascii=False).encode('utf-8') + b'\n'
                await asyncio.sleep(0)

        except Exception as exc:
            error_msg = "生成回复时发生错误。"
            logger.exception(error_msg)
            error_response = json.dumps({
                "contentType": "lui-message-manus-step",
                "content": {"intro": error_msg, "steps": []},
                "sessionInfo": params.get("sessionInfo", {}),
                "code": 1,
                "message": "error",
                "task": "chat",
                "changeType": "replace"
            }, ensure_ascii=False).encode('utf-8') + b'\n'
            yield error_response

    return StreamingResponse(
        generate_stream_response(generator_func, params),
        media_type="application/json"
    )
