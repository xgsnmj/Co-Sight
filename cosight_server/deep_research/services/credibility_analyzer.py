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
import os
from typing import List, Dict, Any, Optional
from app.common.logger_util import logger
from app.cosight.llm.chat_llm import ChatLLM
from config.config import get_credibility_model_config
from llm import set_model


class CredibilityAnalyzer:
    """可信信息分析器，用于分析步骤结果并生成可信信息总结"""
    
    def __init__(self):
        """初始化可信信息分析器"""
        self.llm = None  # 延迟初始化
        self.credibility_types = {
            "truth": "常识或者真理",
            "verified_facts": "给定或者已验证的事实", 
            "searchable_facts": "需要查找的事实",
            "derived_facts": "需要推导的事实",
            "educated_guess": "有根据的猜测"
        }
    
    def _init_llm(self) -> Optional[ChatLLM]:
        """初始化LLM客户端"""
        try:
            if self.llm is not None:
                return self.llm
                
            # 获取可信信息分析专用配置
            model_config = get_credibility_model_config()
            logger.info(f"可信信息分析LLM配置: {model_config}")
            
            # 创建ChatLLM实例
            self.llm = set_model(model_config)
            logger.info("可信信息分析LLM初始化成功")
            return self.llm
            
        except Exception as e:
            logger.error(f"初始化可信信息分析LLM失败: {str(e)}", exc_info=True)
            return None
    
    def _get_credibility_prompt(self, step_content: str, all_steps_content: str, tool_events_summary: str, tool_events_json: str) -> str:
        """生成可信信息分析的prompt，包含工具摘要与工具原始结果（JSON 精简）。"""
        return f"""你是一个专业的信息可信度分析师。请分析以下步骤执行结果，并按照5种可信度类型进行总结。

**分析内容：**
当前步骤内容：{step_content}

所有已完成步骤内容：{all_steps_content}

相关工具调用与结果摘要：
{tool_events_summary}

相关工具调用的原始输出（JSON，已精简字段与长度）：
```json
{tool_events_json}
```

**可信度分类定义：**

1. **常识或者真理 (Truth/Common Sense)**
   - 定义：被广泛接受的基础事实和逻辑真理
   - 特征：无需验证、普遍认可、逻辑自洽
   - 示例：数学公式、物理定律、基本逻辑关系

2. **给定或者已验证的事实 (Given/Verified Facts)**
   - 定义：来自权威来源、已通过验证的明确事实
   - 特征：问题要求、PDF文件、官方文档、权威数据
   - 示例：官方统计数据、学术论文、政府报告

3. **需要查找的事实 (Searchable Facts)**
   - 定义：需要通过网络搜索或数据库查询获取的事实
   - 特征：百度、Wikipedia、Google搜索、网页内容
   - 示例：最新新闻、实时数据、网络信息

4. **需要推导的事实 (Derived Facts)**
   - 定义：基于已知事实通过逻辑推理得出的结论
   - 特征：基于搜索结果的推理、时间推理、逻辑分析
   - 示例：趋势分析、因果关系、预测结果

5. **有根据的猜测 (Educated Guess)**
   - 定义：基于有限信息做出的合理推测
   - 特征：网页评论、模糊信息、不确定来源
   - 示例：专家观点、市场预测、可能性分析

**任务要求：**
1) 面向结论输出，每类至少1条、至多2条，单句不超过50字；
2) 当证据不足也需给出最合理的结论性表述，并在句末注明依据（如：来自“给定资料/工具结果/逻辑推断”）。
3) 避免空泛与重复，确保对用户有直接价值。

**输出格式（严格按此JSON格式）：**
```json
{{
    "truth": ["常识或真理1", "常识或真理2"],
    "verified_facts": ["已验证事实1", "已验证事实2"],
    "searchable_facts": ["需查找事实1", "需查找事实2"],
    "derived_facts": ["需推导事实1", "需推导事实2"],
    "educated_guess": ["有根据猜测1", "有根据猜测2"]
}}
```

请开始分析："""

    async def analyze_step_credibility(self, current_step: Dict[str, Any], all_completed_steps: List[Dict[str, Any]], tool_events: List[Dict[str, Any]] | None = None) -> Optional[Dict[str, List[str]]]:
        """分析步骤的可信信息
        
        Args:
            current_step: 当前完成的步骤信息
            all_completed_steps: 所有已完成的步骤信息
            
        Returns:
            可信信息分析结果，格式为 {类型: [总结句子列表]}
        """
        logger.info(f"可信信息分析器开始工作")
        
        # 初始化LLM
        llm = self._init_llm()
        if not llm:
            logger.warning("LLM初始化失败，跳过可信信息分析")
            return None
            
        try:
            # 构建当前步骤内容
            current_content = self._format_step_content(current_step)
            
            # 仅构建当前步骤内容，取消拼接所有已完成步骤内容以降低长度
            all_content = ""
            
            # 工具事件摘要与原始结果（精简JSON）
            tool_events = tool_events or []
            tool_events_summary = self._format_tool_events_summary(tool_events)
            tool_events_json = self._format_tool_events_json(tool_events)

            # 生成prompt（仅使用当前步骤内容）
            prompt = self._get_credibility_prompt(current_content, all_content, tool_events_summary, tool_events_json)
            
            # 调用LLM分析
            messages = [{"role": "user", "content": prompt}]
            logger.info(f"开始调用LLM进行可信信息分析，prompt长度: {len(prompt)}")
            
            response = llm.chat_to_llm(messages)
            logger.info(f"LLM响应长度: {len(response) if response else 0}")
            
            # 解析响应并补全五类
            credibility_result = self._parse_llm_response(response)
            credibility_result = self._ensure_complete_result(
                credibility_result,
                current_step,
                all_completed_steps,
                tool_events
            )
            logger.info(f"解析结果: {credibility_result}")
            
            logger.info(f"可信信息分析完成，当前步骤: {current_step.get('title', 'Unknown')}")
            return credibility_result
            
        except Exception as e:
            logger.error(f"可信信息分析失败: {str(e)}", exc_info=True)
            return None

    def _format_tool_events_summary(self, tool_events: List[Dict[str, Any]]) -> str:
        if not tool_events:
            return "(无工具调用记录)"
        lines: List[str] = []
        max_items = 20
        for idx, evt in enumerate(tool_events[-max_items:]):
            summary = evt.get("summary") or ""
            # 补齐常见字段
            tool_name = evt.get("tool_name") or evt.get("name") or "tool"
            args = evt.get("tool_args") or evt.get("args")
            result = evt.get("tool_result") or evt.get("result") or evt.get("output")
            if isinstance(result, (dict, list)):
                try:
                    result = json.dumps(result, ensure_ascii=False)
                except Exception:
                    result = str(result)
            if not summary:
                # 从原始结构回退提取
                if isinstance(evt.get("raw"), dict):
                    try:
                        raw = evt["raw"]
                        content = raw.get("content") or {}
                        tool_name = content.get("toolName") or content.get("name") or tool_name
                        status = content.get("status") or content.get("resultStatus") or "ok"
                        result = content.get("output") or content.get("result") or result
                        if isinstance(result, (dict, list)):
                            result = json.dumps(result, ensure_ascii=False)
                        summary = f"[{tool_name}] {status} {str(result)[:300] if result else ''}"
                    except Exception:
                        summary = f"[{tool_name}] {str(result)[:300] if result else ''}"
                else:
                    summary = f"[{tool_name}] {str(result)[:300] if result else ''}"
            lines.append(f"- {summary}")
        if len(tool_events) > max_items:
            lines.append(f"(其余 {len(tool_events)-max_items} 条已省略)")
        return "\n".join(lines)

    def _format_tool_events_json(self, tool_events: List[Dict[str, Any]]) -> str:
        """将工具事件精简为适合放入 Prompt 的 JSON 字符串。

        仅保留关键信息，并限制每条输出的长度，避免提示词过长。
        """
        slim_events: List[Dict[str, Any]] = []
        max_items = 10
        for evt in tool_events[-max_items:]:
            tool_name = evt.get("tool_name") or evt.get("name") or "tool"
            args = evt.get("tool_args") or evt.get("args")
            result = evt.get("tool_result") or evt.get("result") or evt.get("output")
            if isinstance(result, (dict, list)):
                try:
                    result = json.dumps(result, ensure_ascii=False)
                except Exception:
                    result = str(result)
            if isinstance(args, (dict, list)):
                try:
                    args = json.dumps(args, ensure_ascii=False)
                except Exception:
                    args = str(args)
            slim_events.append({
                "tool": tool_name,
                "args": (str(args)[:300] if args else None),
                "result": (str(result)[:600] if result else None),
                "timestamp": evt.get("timestamp")
            })
        try:
            return json.dumps(slim_events, ensure_ascii=False, indent=2)
        except Exception:
            return "[]"
    
    def _format_step_content(self, step: Dict[str, Any]) -> str:
        """格式化步骤内容为可读文本"""
        title = step.get('title', '未知步骤')
        description = step.get('description', '')
        notes = step.get('notes', '')
        status = step.get('status', '')
        
        content_parts = [f"步骤标题: {title}"]
        if description:
            content_parts.append(f"步骤描述: {description}")
        if notes:
            content_parts.append(f"执行结果: {notes}")
        if status:
            content_parts.append(f"状态: {status}")
            
        return "\n".join(content_parts)
    
    def _parse_llm_response(self, response: str) -> Dict[str, List[str]]:
        """解析LLM响应，提取可信信息分析结果"""
        try:
            # 尝试提取JSON部分
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            else:
                # 尝试直接解析整个响应
                json_str = response.strip()
            
            result = json.loads(json_str)
            
            # 验证和清理结果
            cleaned_result = {}
            for key, value in result.items():
                if isinstance(value, list):
                    # 过滤掉"无"和空字符串
                    cleaned_value = [item for item in value if item and item.strip() != "无"]
                    cleaned_result[key] = cleaned_value
                else:
                    cleaned_result[key] = []
            
            return cleaned_result
            
        except json.JSONDecodeError as e:
            logger.error(f"解析LLM响应JSON失败: {str(e)}")
            logger.error(f"原始响应: {response}")
            return {}
        except Exception as e:
            logger.error(f"解析LLM响应失败: {str(e)}", exc_info=True)
            return {}
    
    def format_credibility_message(self, credibility_result: Dict[str, List[str]], step_title: str, step_index: int | None = None) -> Dict[str, Any]:
        """格式化可信信息为前端消息格式"""
        if not credibility_result:
            return None
            
        # 构建可信信息内容
        credibility_content = []
        
        for cred_type, items in credibility_result.items():
            if items:  # 只添加有内容的类型
                type_name = self.credibility_types.get(cred_type, cred_type)
                credibility_content.append({
                    "title": type_name,
                    "items": items
                })
        
        if not credibility_content:
            return None
            
        message: Dict[str, Any] = {
            "type": "lui-message-credibility-analysis",
            "title": f"步骤可信信息分析: {step_title}",
            "content": credibility_content,
            "stepTitle": step_title,
            "timestamp": self._get_timestamp()
        }
        if step_index is not None:
            message["stepIndex"] = step_index
        return message

    def _ensure_complete_result(self,
                                result: Dict[str, List[str]] | None,
                                current_step: Dict[str, Any],
                                all_completed_steps: List[Dict[str, Any]],
                                tool_events: List[Dict[str, Any]] | None) -> Dict[str, List[str]]:
        categories = [
            ("truth", "常识或真理"),
            ("verified_facts", "已验证事实"),
            ("searchable_facts", "需查找事实"),
            ("derived_facts", "需推导事实"),
            ("educated_guess", "有根据猜测"),
        ]
        safe_result: Dict[str, List[str]] = {k: (result.get(k) if result else []) or [] for k, _ in categories}

        step_title = current_step.get("title") or "当前步骤"
        step_notes = (current_step.get("notes") or "").strip()
        tools_lines = []
        for evt in (tool_events or [])[-10:]:
            s = evt.get("summary") or ""
            if s:
                tools_lines.append(s)
        tools_hint = ("；".join(tools_lines))[:200]

        def ensure_line(lst: List[str], fallback: str):
            if not lst:
                lst.append(fallback[:50])

        ensure_line(safe_result["truth"], f"与“{step_title}”相关常识：先满足依赖再执行（逻辑）")
        ensure_line(safe_result["verified_facts"], f"已确认：{(step_notes or '来源于步骤记录/工具结果')}（已验证）")
        ensure_line(safe_result["searchable_facts"], f"仍需检索：补充“{step_title}”的权威数据与最新动态（搜索）")
        ensure_line(safe_result["derived_facts"], f"推导：完成“{step_title}”降低后续不确定性（推理）")
        ensure_line(safe_result["educated_guess"], f"估计：{('工具显示' + tools_hint) if tools_hint else '依据上下文保守判断'}（猜测）")

        for k in safe_result:
            compact = []
            for item in safe_result[k][:2]:
                s = (item or "").strip()
                if len(s) > 50:
                    s = s[:50]
                if s and s not in compact:
                    compact.append(s)
            safe_result[k] = compact

        return safe_result
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from cosight_server.sdk.common.utils import get_timestamp
        return get_timestamp()


# 全局实例
credibility_analyzer = CredibilityAnalyzer()