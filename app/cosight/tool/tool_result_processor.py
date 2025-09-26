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

import re
import json
from typing import Any, Dict, Optional
from app.common.logger_util import logger


class ToolResultProcessor:
    """工具结果处理器，针对不同工具类型处理结果"""
    
    @staticmethod
    def _to_frontend_url(path_value: str) -> str:
        """将包含 work_space 的本地绝对路径改写为前端可访问的 URL。

        规则：
        - 仅当路径中包含 "work_space/" 时改写
        - 使用配置项 base_api_url，缺省为 "/api/nae-deep-research/v1"
        - 仅对文件名进行 URL 编码，目录保持原样
        """
        try:
            if not isinstance(path_value, str) or len(path_value) == 0:
                return path_value

            normalized = path_value.replace("\\", "/")
            marker = "work_space/"
            idx = normalized.find(marker)
            if idx == -1:
                return path_value

            relative = normalized[idx:]

            # 读取配置前缀
            try:
                from cosight_server.sdk.common.config import custom_config
                base_url = str(custom_config.get("base_api_url"))
            except Exception:
                base_url = ""

            if not base_url:
                base_url = "/api/nae-deep-research/v1"
            base_url = base_url.rstrip("/")

            # 仅对文件名编码
            parts = relative.split("/")
            if len(parts) >= 2 and parts[-1]:
                parts[-1] = parts[-1]
                relative = "/".join(parts)

            return f"{base_url}/{relative}"
        except Exception:
            return path_value

    @staticmethod
    def process_tool_result(tool_name: str, tool_args: str, tool_result: str) -> Dict[str, Any]:
        """
        根据工具类型处理结果
        
        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            tool_result: 工具原始结果
            
        Returns:
            处理后的结果字典
        """
        try:
            # 根据工具名称精确匹配选择处理方式
            if tool_name in ['search_baidu', 'search_google', 'search_wiki', 'tavily_search', 'image_search']:
                return ToolResultProcessor._process_search_result(tool_name, tool_args, tool_result)
            elif tool_name == 'execute_code':
                return ToolResultProcessor._process_code_result(tool_name, tool_args, tool_result)
            elif tool_name in ['file_saver', 'file_read', 'file_str_replace', 'file_find_in_content','create_html_report']:
                return ToolResultProcessor._process_file_result(tool_name, tool_args, tool_result)
            elif tool_name == 'browser_use':
                return ToolResultProcessor._process_web_result(tool_name, tool_args, tool_result)
            elif tool_name == 'fetch_website_content':
                return ToolResultProcessor._process_website_content_result(tool_name, tool_args, tool_result)
            elif tool_name in ['ask_question_about_image', 'ask_question_about_video']:
                return ToolResultProcessor._process_image_result(tool_name, tool_args, tool_result)
            else:
                return ToolResultProcessor._process_default_result(tool_name, tool_args, tool_result)
        except Exception as e:
            logger.error(f"Error processing tool result for {tool_name}: {e}")
            return ToolResultProcessor._process_default_result(tool_name, tool_args, tool_result)
    
    @staticmethod
    def _process_search_result(tool_name: str, tool_args: str, tool_result: str) -> Dict[str, Any]:
        """处理搜索结果"""
        try:
            # 首先尝试解析为JSON（适用于tavily等结构化结果）
            parsed_result = None
            try:
                if isinstance(tool_result, str):
                    parsed_result = json.loads(tool_result)
                else:
                    parsed_result = tool_result
            except (json.JSONDecodeError, TypeError):
                parsed_result = None
            
            urls = []
            result_count = 0
            
            if parsed_result and isinstance(parsed_result, dict):
                # 处理结构化搜索结果（如tavily）
                if 'results' in parsed_result and isinstance(parsed_result['results'], list):
                    results = parsed_result['results']
                    result_count = len(results)
                    for result in results:
                        if isinstance(result, dict) and 'url' in result:
                            urls.append(result['url'])
                elif 'result_id' in parsed_result:
                    # 兼容其他格式
                    result_count = 1
                    if 'url' in parsed_result:
                        urls.append(parsed_result['url'])
            else:
                # 处理字符串格式的搜索结果（兼容旧格式）
                # 方法1: 从 'url': 'xxx' 格式中提取
                url_pattern1 = r"'url':\s*'([^']+)'"
                matches1 = re.findall(url_pattern1, tool_result)
                urls.extend(matches1)
                
                # 方法2: 从 "url": "xxx" 格式中提取
                url_pattern2 = r'"url":\s*"([^"]+)"'
                matches2 = re.findall(url_pattern2, tool_result)
                urls.extend(matches2)
                
                # 方法3: 从 href 属性中提取
                href_pattern = r'href=["\']([^"\']+)["\']'
                href_matches = re.findall(href_pattern, tool_result)
                urls.extend([url for url in href_matches if url.startswith('http')])
                
                # 方法4: 直接匹配HTTP/HTTPS链接
                http_pattern = r'https?://[^\s\'"<>]+'
                http_matches = re.findall(http_pattern, tool_result)
                urls.extend(http_matches)
                
                # 尝试提取结果数量
                result_count = len(re.findall(r"'result_id':\s*\d+", tool_result))
            
            # 去重并保持顺序
            seen = set()
            unique_urls = []
            for url in urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)
            
            # 限制URL数量，避免过多
            unique_urls = unique_urls[:20]
            
            # 如果之前没有找到result_id，使用去重后的URL数量
            if result_count == 0:
                result_count = len(unique_urls)
            
            return {
                "tool_type": "search",
                "summary": f"搜索完成，找到 {result_count} 个结果",
                "first_url": unique_urls[0] if unique_urls else None,
                "urls": unique_urls,  # 添加所有URL列表
                "result_count": result_count,
                "has_content": "Error fetching content" not in str(tool_result)
            }
        except Exception as e:
            logger.error(f"Error processing search result: {e}")
            return {
                "tool_type": "search",
                "summary": "搜索完成",
                "error": str(e)
            }
    
    @staticmethod
    def _process_code_result(tool_name: str, tool_args: str, tool_result: str) -> Dict[str, Any]:
        """处理代码执行结果"""
        try:
            # 提取代码内容
            code_content = tool_args if tool_args else "无代码内容"
            
            # 判断执行是否成功
            is_success = "error" not in tool_result.lower() and "exception" not in tool_result.lower()
            
            # 提取输出长度
            output_length = len(tool_result)
            
            return {
                "tool_type": "code_execution",
                "summary": f"代码执行{'成功' if is_success else '失败'}",
                "code_content": code_content[:200] + "..." if len(code_content) > 200 else code_content,
                "output_length": output_length,
                "is_success": is_success
            }
        except Exception as e:
            logger.error(f"Error processing code result: {e}")
            return {
                "tool_type": "code_execution",
                "summary": "代码执行完成",
                "error": str(e)
            }
    
    @staticmethod
    def _process_file_result(tool_name: str, tool_args: str, tool_result: str) -> Dict[str, Any]:
        """处理文件操作结果"""
        try:
            # 解析tool_args中的JSON数据
            file_path = "未知文件"
            parsed_args = {}
            
            if tool_args:
                try:
                    # 尝试解析JSON格式的tool_args
                    parsed_args = json.loads(tool_args)
                    if isinstance(parsed_args, dict):
                        # 尝试多种可能的文件名key
                        for key in ['file_path', 'file', 'filename']:
                            if key in parsed_args:
                                file_path = parsed_args[key]
                                break
                except json.JSONDecodeError:
                    # 如果不是JSON格式，直接使用tool_args作为文件路径
                    file_path = tool_args

            # 将本地路径改写为前端URL
            file_path = ToolResultProcessor._to_frontend_url(file_path)
            
            # 判断操作类型
            if 'read' in tool_name.lower():
                operation = "读取"
                content_length = len(tool_result)
                summary = f"文件读取完成，内容长度: {content_length} 字符"
            elif 'save' in tool_name.lower() or 'write' in tool_name.lower():
                operation = "保存"
                summary = "文件保存完成"
            else:
                operation = "文件操作"
                summary = "文件操作完成"
            
            return {
                "tool_type": "file_operation",
                "summary": summary,
                "operation": operation,
                "file_path": file_path,
                "content_length": len(tool_result) if 'read' in tool_name.lower() else None
            }
        except Exception as e:
            logger.error(f"Error processing file result: {e}")
            return {
                "tool_type": "file_operation",
                "summary": "文件操作完成",
                "error": str(e)
            }
    
    @staticmethod
    def _process_web_result(tool_name: str, tool_args: str, tool_result: str) -> Dict[str, Any]:
        """处理网页操作结果"""
        try:
            # 提取URL
            url_pattern = r"https?://[^\s]+"
            url_match = re.search(url_pattern, tool_args)
            url = url_match.group(0) if url_match else "未知URL"
            
            # 判断操作类型
            if 'fetch' in tool_name.lower():
                operation = "网页抓取"
                content_length = len(tool_result)
                summary = f"网页抓取完成，内容长度: {content_length} 字符"
            else:
                operation = "网页操作"
                summary = "网页操作完成"
            
            return {
                "tool_type": "web_operation",
                "summary": summary,
                "operation": operation,
                "url": url,
                "content_length": len(tool_result)
            }
        except Exception as e:
            logger.error(f"Error processing web result: {e}")
            return {
                "tool_type": "web_operation",
                "summary": "网页操作完成",
                "error": str(e)
            }
    
    @staticmethod
    def _process_website_content_result(tool_name: str, tool_args: str, tool_result: str) -> Dict[str, Any]:
        """处理网站内容抓取结果"""
        try:
            # 提取URL
            url = "未知URL"
            if tool_args:
                try:
                    # 尝试解析JSON格式的tool_args
                    parsed_args = json.loads(tool_args)
                    if isinstance(parsed_args, dict) and 'website_url' in parsed_args:
                        url = parsed_args['website_url']
                except json.JSONDecodeError:
                    # 如果不是JSON格式，直接使用tool_args作为URL
                    url = tool_args
            
            # # 检查是否有错误
            is_error =  "fetch_website_content error" in tool_result
            
            # 计算内容长度
            content_length = len(tool_result)
            
            # 提取内容摘要（前200个字符）
            content_preview = tool_result[:200] + "..." if len(tool_result) > 200 else tool_result
            
            # 统计行数和段落数
            lines = tool_result.split('\n')
            line_count = len([line for line in lines if line.strip()])
            paragraph_count = len([p for p in tool_result.split('\n\n') if p.strip()])
            
            # 提取可能的标题（以大写字母开头且长度适中的行）
            potential_titles = []
            for line in lines[:10]:  # 只检查前10行
                line = line.strip()
                if (len(line) > 10 and len(line) < 100 and 
                    line[0].isupper() and not line.endswith('.') and 
                    not line.startswith('http')):
                    potential_titles.append(line)
            
            summary = f"网站内容抓取{'成功' if not is_error else '失败'}，内容长度: {content_length} 字符"
            if is_error:
                summary += f"，错误信息: {tool_result}"
            
            return {
                "tool_type": "website_content",
                "summary": summary,
                "operation": "网站内容抓取",
                "url": url,
                "content_length": content_length,
                "line_count": line_count,
                "paragraph_count": paragraph_count,
                "content_preview": content_preview,
                "potential_titles": potential_titles[:3],  # 最多返回3个可能的标题
                "is_success": not is_error,
                "has_content": content_length > 0 and not is_error
            }
        except Exception as e:
            logger.error(f"Error processing website content result: {e}")
            return {
                "tool_type": "website_content",
                "summary": "网站内容抓取完成",
                "operation": "网站内容抓取",
                "error": str(e),
                "is_success": False
            }

    @staticmethod
    def _process_image_result(tool_name: str, tool_args: str, tool_result: str) -> Dict[str, Any]:
        """处理图像分析结果"""
        try:
            # 判断操作类型
            if 'question' in tool_name.lower():
                operation = "图像问答"
                summary = "图像分析完成"
            else:
                operation = "图像处理"
                summary = "图像处理完成"
            
            return {
                "tool_type": "image_analysis",
                "summary": summary,
                "operation": operation,
                "result_length": len(tool_result)
            }
        except Exception as e:
            logger.error(f"Error processing image result: {e}")
            return {
                "tool_type": "image_analysis",
                "summary": "图像处理完成",
                "error": str(e)
            }
    
    @staticmethod
    def _process_default_result(tool_name: str, tool_args: str, tool_result: str) -> Dict[str, Any]:
        """处理默认结果"""
        return {
            "tool_type": "other",
            "summary": f"{tool_name} 执行完成",
            "result_length": len(tool_result),
            "has_result": bool(tool_result.strip())
        }