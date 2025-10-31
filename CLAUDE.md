# CLAUDE.md

1、用中文回复我
2、代码尽量精简，注释齐全
3、我使用windows11+vscode进行开发
4、所有数据库相关的变动，表新增、表修改都维护到database_schema.md文件中
5、给出修复方案意见时，尽量给我彻底解决问题的最好建议，而不是折中妥协的建议
6、每当架构演进导致某些代码或文件废弃时，及时清理

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Co-Sight** is an AI-powered research and analysis system designed to generate high-quality reports through intelligent task planning, execution, and verification. The system combines multiple AI agents with different roles (planning, execution, tools, vision) to perform comprehensive research tasks and generate structured reports.

## Architecture

### Core Components

- **CoSight.py**: Main entry point for the research engine that orchestrates the entire process
- **llm.py**: LLM model configuration and initialization (planning, execution, tools, vision models)
- **app/cosight/**: Core application logic containing:
  - **agent/**: AI agent implementations (planner, actor)
  - **task/**: Task management, planning, and execution logic
  - **tool/**: Integration with external tools and APIs
- **cosight_server/deep_research/**: FastAPI web server providing REST API and WebSocket interface
- **config/**: Configuration management and environment variable handling

### Key Architecture Patterns

- **Multi-Agent System**: Different specialized agents handle planning, execution, and tool usage
- **Task-Based Execution**: Research tasks are broken down into executable steps with dependency management
- **Concurrent Processing**: Multiple task steps can execute in parallel using threading
- **Modular LLM Configuration**: Different models can be configured for different roles (planning, execution, tools, vision)

## Development Commands

### Running the Application

```bash
# Start the web server (main interface)
python cosight_server/deep_research/main.py

# Or run the core engine directly
python CoSight.py
```

### Environment Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Alternative using uv (if preferred)
uv sync

# Copy environment configuration
cp .env_template .env
# Then edit .env with your API keys and model configurations
```

### Configuration

The system uses a layered configuration approach:

1. **Base Configuration** (`.env`): Default model settings
2. **Specialized Models**: Optional separate configurations for:
   - `PLAN_*` settings for planning model
   - `ACT_*` settings for execution model
   - `TOOL_*` settings for tool usage model
   - `VISION_*` settings for multimodal model
   - `CREDIBILITY_*` settings for credibility analysis
   - `BROWSER_*` settings for browser automation

### Key Files for Development

- **CoSight.py:167**: Main CoSight instantiation and execution
- **cosight_server/deep_research/main.py:223**: Server startup with port configuration
- **config/config.py**: All model configuration functions
- **app/cosight/task/task_manager.py**: Task execution management
- **app/cosight/agent/**: Agent implementations

## Working Directory Structure

- **work_space/**: Runtime workspace for task execution (auto-created with timestamps)
- **upload_files/**: User uploaded files storage
- **logs/**: Application logs
- **config/mcp_server_config.json**: MCP (Model Context Protocol) tool configurations

## Key Dependencies

- **FastAPI**: Web server framework
- **OpenAI**: LLM API client
- **lagent**: Agent framework
- **browser-use**: Web automation
- **tavily-python**: Search API integration
- **mcp**: Model Context Protocol support
- **plotly**: Visualization generation
- **minify-html**: HTML processing

## Important Notes

- The system requires Python 3.11+
- Minimum system requirements: 4GB RAM, 1GB disk space
- Default server runs on port 7788 (configurable via environment variables)
- The application creates timestamped workspace directories for each execution
- MCP tools can be configured in `config/mcp_server_config.json` for extending functionality
- All agent configurations support proxy settings for API access

## Testing and Quality

- No formal test suite currently exists in the repository
- Manual testing is done through the web interface at `http://localhost:7788/cosight/`
- Python syntax can be validated with: `python -m py_compile <module_name>.py`