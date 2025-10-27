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

import os
import re
from typing import Dict

from app.agent_dispatcher.infrastructure.entity.AgentInstance import AgentInstance
from app.cosight.agent.actor.prompt.actor_prompt import actor_system_prompt, actor_system_prompt_zh, actor_execute_task_prompt, actor_execute_task_prompt_zh
from app.cosight.agent.base.base_agent import BaseAgent
from app.cosight.llm.chat_llm import ChatLLM
from app.cosight.task.plan_report_manager import plan_report_event_manager
from app.cosight.task.task_manager import TaskManager
from app.cosight.task.time_record_util import time_record
from app.cosight.tool.act_toolkit import ActToolkit
from app.cosight.tool.code_toolkit import CodeToolkit
from app.cosight.tool.file_toolkit import FileToolkit
from app.cosight.tool.deep_search.deep_search import DeepSearchToolkit
from app.cosight.tool.terminate_toolkit import TerminateToolkit
from app.cosight.tool.web_util import WebToolkit
from app.cosight.tool.image_analysis_toolkit import VisionTool
from app.cosight.tool.document_processing_toolkit import DocumentProcessingToolkit
from app.cosight.tool.search_toolkit import SearchToolkit
from app.cosight.tool.search_util import search_baidu
from app.cosight.tool.scrape_website_toolkit import fetch_website_content, fetch_website_content_with_images, fetch_website_images_only
from app.cosight.tool.deep_search.searchers.tavily_search import TavilySearch
from app.cosight.tool.audio_toolkit import AudioTool
from app.cosight.tool.video_analysis_toolkit import VideoTool
from app.cosight.tool.html_visualization_toolkit import HtmlVisualizationToolkit
from config.config import get_tavily_config
from app.common.logger_util import logger


class TaskActorAgent(BaseAgent):
    def __init__(self, agent_instance: AgentInstance, llm: ChatLLM,
                 vision_llm: ChatLLM,
                 tool_llm: ChatLLM, plan_id,
                 functions: Dict = None,
                 work_space_path: str = None):
        # Set up TaskActorAgent specific properties first
        self.work_space_path = work_space_path if work_space_path else os.environ.get("WORKSPACE_PATH") or os.getcwd()
        
        # Debug: Check if plan_id exists in TaskManager
        logger.info(f"TaskActorAgent: Looking for plan_id: {plan_id}")
        logger.info(f"TaskActorAgent: Available plans in TaskManager: {list(TaskManager.plans.keys())}")
        
        try:
            self.plan = TaskManager.get_plan(plan_id)
            logger.info(f"TaskActorAgent: Successfully retrieved plan for plan_id: {plan_id}")
        except KeyError as e:
            logger.error(f"TaskActorAgent: Plan not found for plan_id: {plan_id}, error: {e}")
            raise ValueError(f"Plan with id '{plan_id}' not found in TaskManager. Available plans: {list(TaskManager.plans.keys())}")
        
        self.question = None  # Store the question for later use
        act_toolkit = ActToolkit(self.plan)
        terminate_toolkit = TerminateToolkit()
        file_toolkit = FileToolkit(work_space_path)
        web_toolkit = WebToolkit({"base_url": tool_llm.base_url,
                                  "model": tool_llm.model,
                                  "api_key": tool_llm.api_key})
        image_toolkit = VisionTool({"base_url": vision_llm.base_url,
                                    "model": vision_llm.model,
                                    "api_key": vision_llm.api_key})
        audio_toolkit = AudioTool({"base_url": vision_llm.base_url,
                                   "model": vision_llm.model,
                                   "api_key": vision_llm.api_key})
        video_toolkit = VideoTool({"base_url": vision_llm.base_url,
                                   "model": vision_llm.model,
                                   "api_key": vision_llm.api_key})
        doc_toolkit = DocumentProcessingToolkit()
        search_toolkit = SearchToolkit()
        deep_search_toolkit = DeepSearchToolkit({
            "base_url": tool_llm.base_url,
            "api_key": tool_llm.api_key,
            "model_name": tool_llm.model,

        }, {

            # 配置tavily
            "api_key": get_tavily_config()
        })
        code_toolkit = CodeToolkit(sandbox="subprocess")
        tavily_search = TavilySearch()
        html_toolkit = HtmlVisualizationToolkit(workspace_path=work_space_path, tool_llm=tool_llm)
        code_toolkit = CodeToolkit(sandbox="subprocess")
        all_functions = {"mark_step": act_toolkit.mark_step,
                         # "deep_search": deep_search_toolkit.deep_search,
                         "search_baidu": search_baidu,
                         "search_google": search_toolkit.search_google,
                         "search_wiki": search_toolkit.search_wiki,
                         "tavily_search": search_toolkit.tavily_search,
                        #  "image_search": tavily_search.search,
                         "audio_recognition": audio_toolkit.speech_to_text,
                         # "search_duckgo": search_toolkit.search_duckduckgo,
                         "execute_code": code_toolkit.execute_code,
                         "file_saver": file_toolkit.file_saver,
                         "file_read": file_toolkit.file_read,
                         "file_str_replace": file_toolkit.file_str_replace,
                         "file_find_in_content": file_toolkit.file_find_in_content,
                        #  "browser_use": web_toolkit.browser_use,
                         "ask_question_about_image": image_toolkit.ask_question_about_image,
                         "ask_question_about_video": video_toolkit.ask_question_about_video,
                         "fetch_website_content": fetch_website_content,
                         "fetch_website_content_with_images": fetch_website_content_with_images,
                         "fetch_website_images_only": fetch_website_images_only,
                         "extract_document_content": doc_toolkit.extract_document_content,
                         "create_html_report": lambda title=None, include_charts=True, chart_types=['all'], output_filename=None: html_toolkit.create_html_report(
                             title=title,
                             include_charts=include_charts,
                             chart_types=chart_types,
                             output_filename=output_filename,
                             user_query=self.question
                         ),
                         }
        if functions:
            all_functions.update(functions)
        
        # Initialize BaseAgent with all functions and plan_id
        super().__init__(agent_instance, llm, all_functions, plan_id=plan_id)
        
        # Check if plan exists and has title before accessing it
        is_chinese = bool(re.search(r'[\u4e00-\u9fff]', self.plan.title)) if self.plan and self.plan.title else True
        if is_chinese:
            sys_prompt = actor_system_prompt_zh(self.work_space_path)
        else:
            sys_prompt = actor_system_prompt(self.work_space_path)
        self.history.append({"role": "system", "content": sys_prompt})

    @time_record
    def act(self, question, step_index):
        self.question = question  # Store the question for use in tools
        
        # Ensure plan is available
        if self.plan is None:
            logger.error(f"TaskActorAgent.act: self.plan is None for step_index {step_index}")
            raise ValueError(f"Plan is None. Cannot execute step {step_index}.")
        
        self.plan.mark_step(step_index, step_status="in_progress")
        plan_report_event_manager.publish("plan_process", self.plan)
        is_chinese = bool(re.search(r'[\u4e00-\u9fff]', self.question)) if self.question else True
        if is_chinese:
            task_prompt = actor_execute_task_prompt_zh(question, step_index, self.plan, self.work_space_path)
        else:
            task_prompt = actor_execute_task_prompt(question, step_index, self.plan, self.work_space_path)

        self.history.append(
            {"role": "user", "content": task_prompt})
        try:
            result = self.execute(self.history, step_index=step_index)
            if self.plan.step_statuses.get(self.plan.steps[step_index], "") == "in_progress":
                self.plan.mark_step(step_index, step_status="completed", step_notes=str(result))
                # 步骤完成后，主动上报一次计划进度，确保前端收到manus-step
                plan_report_event_manager.publish("plan_process", self.plan)
            return result
        except Exception as e:
            logger.error(f'act agent execute error: {str(e)}', exc_info=True)
            self.plan.mark_step(step_index, step_status="blocked", step_notes=str(e))
            # 步骤失败同样上报一次计划进度
            plan_report_event_manager.publish("plan_process", self.plan)
            return str(e)
