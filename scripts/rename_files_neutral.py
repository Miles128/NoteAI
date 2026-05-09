import re
import pathlib

WORKSPACE = pathlib.Path('/Users/sihai/Documents/My Notes')

RENAMES = {
    'AI Agent 架构分析综述.md': 'AI Agent架构分析综述.md',
    'AI 提示词模板大全.md': 'AI提示词模板大全.md',
    'Claude Code 完整教程（特有普讲解版）.md': 'Claude Code完整教程.md',
    'Claude Code完整教程：从入门到精通.md': 'Claude Code入门到精通.md',
    'Function Call 与 MCP 原理综述.md': 'Function Call与MCP原理综述.md',
    'Harness Engineering 综述.md': 'Harness Engineering综述.md',
    'Hermes Agent 综述.md': 'Hermes Agent综述.md',
    'Hermes Agent 综述（特有普讲解版）.md': 'Hermes Agent使用与架构解析.md',
    'Multi-Agent 实现方式与 LangChain 实战.md': 'Multi-Agent实现与LangChain实战.md',
    'RAG 技术综述：从朴素检索到智能知识系统.md': 'RAG技术综述.md',
    'Skills/国内最流行的 Claude Code Skills 综述.md': 'Claude Code Skills综述.md',
    '特有普讲解 GitHub.md': 'GitHub入门指南.md',
    '特有普讲解 Vibe Coding 技术栈选型.md': 'Vibe Coding技术栈选型.md',
    'My Projects/186278754138983.md': '项目笔记186278754138983.md',
    'Notes/AI产品经理之路/AI 产品构建全流程与方法论.md': 'AI产品构建全流程与方法论.md',
    'Notes/AI产品经理之路/AI 测试、数据闭环与优化：构建可持续演进的大模型产品.md': 'AI产品测试与数据闭环.md',
    'Notes/AI产品经理之路/AI产品经理--WIKI.md': 'AI产品经理知识库.md',
    'Notes/AI产品经理之路/AI产品经理--面试题库.md': 'AI产品经理面试题库.md',
    'Notes/AI产品经理之路/传统产品管理核心技能：数据系统与指标规划深度解析.md': '产品管理核心技能与数据指标规划.md',
    'Notes/AI产品经理之路/商业模式与商业效率提升：实现可持续盈利的策略指南.md': '商业模式与效率提升策略.md',
    'Notes/AI产品经理之路/怎么写好一个AI提示词？10个场景与50个技巧+官方100个教程合集.md': 'AI提示词编写技巧与教程合集.md',
    'Notes/AI工具和平台评测/AI 开发工具与平台生态全景解析：从工作流到智能体.md': 'AI开发工具与平台生态全景.md',
    'Notes/AI工具和平台评测/Vibe coding MenuGen.md': 'Vibe Coding与MenuGen实践.md',
    'Notes/AI工具和平台评测/小米宣布上线PC版龙虾，Xiaomi miclaw正式开启PC、Mac、有屏音箱多终端封测.md': 'Xiaomi Miclaw多终端封测.md',
    'Notes/AI工具和平台评测/我用 LLM 生成的代码在 20 分钟内替换了一个每年 120 美元的微型 SaaS.md': 'LLM代码生成替代微型SaaS实践.md',
    'Notes/AI工具和平台评测/海内外AI 工作流平台横评 1.md': 'AI工作流平台横评.md',
    'Notes/AI工具和平台评测/海内外AI 工作流平台横评.md': '海内外AI工作流平台横评.md',
    'Notes/Agent架构与设计/22 _ AI Agent 架构必读：OpenClaw 和 Claude Code，其实在解决同一个问题 1.md': 'OpenClaw与Claude Code架构对比.md',
    'Notes/Agent架构与设计/Agent 的本质：用 Token 换架构_9f9f9c71.md': 'Agent本质与Token架构.md',
    'Notes/Agent架构与设计/【47】AI工程师面经整理与解读——20260424-Agent算法.md': 'AI工程师Agent算法面经.md',
    'Notes/Agent架构与设计/为什么顶尖AI Agent都有强大记忆？3个难度层级讲明白！.md': 'AI Agent记忆系统三层架构.md',
    'Notes/Agent架构与设计/带你实现一个Agent（上），从Tools、MCP到Skills_a9bf0a0f.md': 'Agent实现上篇：Tools与MCP.md',
    'Notes/Agent架构与设计/带你实现一个Agent（下），从记忆系统、ReAct到具体案例_ce6c064d.md': 'Agent实现下篇：记忆系统与ReAct.md',
    'Notes/Agent架构与设计/提示词工程与智能体 (Agent) 设计指南：从基础框架到自主应用.md': '提示词工程与Agent设计指南.md',
    'Notes/Harness和Agent前沿发展/71k Star 引爆关注！Karpathy 新作 autoresearch：让 AI 替你做研究，你只管睡觉.md': 'Karpathy autoresearch自动化研究工具.md',
    'Notes/Harness和Agent前沿发展/Anthropic Harness 发布！Harness 变成了产品.md': 'Anthropic Harness产品发布.md',
    'Notes/Harness和Agent前沿发展/一文讲透如何构建Harness——六大组件全解析.md': 'Harness六大组件构建指南.md',
    'Notes/Harness和Agent前沿发展/万字讲透Agent Harness的十二大模块.md': 'Agent Harness十二大模块详解.md',
    'Notes/Harness和Agent前沿发展/介绍 NVIDIA Nemotron 3 Nano Omni：面向文档、音频和视频智能体的长上下文多模态智能.md': 'NVIDIA Nemotron多模态智能体模型.md',
    'Notes/Harness和Agent前沿发展/从"野马"到"超级管家"：Harness Engineering 技术解读.md': 'Harness Engineering技术解读.md',
    'Notes/Harness和Agent前沿发展/最新！万字综述Harness革命！.md': 'Harness革命综述.md',
    'Notes/Hermes-Agent/Hermes Agent 使用指南：从安装到精通.md': 'Hermes Agent安装与使用指南.md',
    'Notes/Hermes-Agent/Hermes Agent 深度拆解：它和Openclaw 到底什么关系？.md': 'Hermes Agent与OpenClaw关系解析.md',
    'Notes/Hermes-Agent/Hermes 这个技能我一直没碰，跑完一遍后悔没早试.md': 'Hermes Agent技能实践体验.md',
    'Notes/Multi-Agent与LangGraph/LangGraph多Agent调度实操指南：4个最简案例帮你了解langGraph.md': 'LangGraph多Agent调度实操.md',
    'Notes/Multi-Agent与LangGraph/为什么复杂AI项目要用LangChain？_edd15053.md': '复杂AI项目与LangChain选型.md',
    'Notes/Multi-Agent与LangGraph/国产多 agent 平台介绍和横评.md': '国产多Agent平台横评.md',
    'Notes/Multi-Agent与LangGraph/建议收藏 _ 彻底告别上下文污染：Subagent 与 Skills 的协同套路！.md': 'Subagent与Skills协同模式.md',
    'Notes/Multi-Agent与LangGraph/我用FinRobot分析美团：8个Agent联合作战，输出了一份机构级研报 1.md': 'FinRobot多Agent分析美团实践.md',
    'Notes/RAG与知识库/RAG实践技巧：这次还做不好AI客服，那我也没办法了..._59d8f8fe.md': 'RAG实践技巧与AI客服优化.md',
    'Notes/RAG与知识库/RAG的切片策略.md': 'RAG切片策略.md',
    'Notes/RAG与知识库/半年人工喂出来的AI客服：从0到1打磨生产级RAG系统，越用越聪明_212f67b2.md': '生产级RAG系统搭建实践.md',
    'Notes/RAG与知识库/滴滴Agent岗二面：如何规避 RAG 系统中大模型的幻觉？.md': 'RAG系统幻觉规避方法.md',
    'Notes/RAG与知识库/生产级别的RAG系统是什么样的？_664c504e.md': '生产级RAG系统架构.md',
    'Notes/RAG与知识库/高级 AI 技术集成：RAG、Function Call 与 MCP 的深度融合指南.md': 'RAG与Function Call及MCP融合指南.md',
    'Notes/Skills系统/2026-04-29-如何把经验装到Skills.md': '经验封装为Skills的方法.md',
    'Notes/Skills系统/【OpenClaw】拆解一个真实的 Skill：微信文章阅读器（wechat-article-viewer）.md': '微信文章阅读器Skill拆解.md',
    'Notes/Skills系统/【概念篇】别再只写 Prompt 了，带你读懂Agent 的"技能"革命.md': 'Agent技能革命概念解读.md',
    'Notes/Skills系统/一文读懂Skills，给小白的零基础入门_046d9e41.md': 'Skills零基础入门指南.md',
    'Notes/Skills系统/如何编写顶级的 Agent Skill？这 8 条架构法则建议收藏！.md': 'Agent Skill架构八条法则.md',
    'Notes/Skills系统/打工人三世轮回摊煎饼，我把「同事.Skill」做成了 AI 短剧｜附手把手教程.md': 'Skill开发实战教程.md',
    'Notes/Skills系统/用 Claude Skills 一键发布微信公众号.md': 'Claude Skills发布微信公众号.md',
    'Notes/创意与工具/Seedance2.0 Prompt 圣经.md': 'Seedance视频生成提示词指南.md',
    'Notes/创意与工具/收藏贴：Seedream即梦5.0的100种绘画风格.md': 'Seedream绘画风格大全.md',
    'Notes/模型与微调/万字经验教训：重新审视微调，因为这事我被怼脸连骂2小时！_9484043c.md': '大模型微调经验与反思.md',
    'Notes/模型与微调/模型越强，微调越弱：到底什么时候该微调？_07344b86.md': '模型微调适用场景分析.md',
    'Notes/职业发展和个人提升/职业发展与个人软实力修炼：构建核心竞争力与自我成就之道.md': '职业发展与软实力修炼.md',
    'Notes/行业洞察与趋势/Sequoia Ascent 2026 摘要.md': 'Sequoia Ascent 2026峰会摘要.md',
    'Notes/行业洞察与趋势/Stripe 发布 288 项新功能，构建 AI 时代的经济基础设施.md': 'Stripe AI经济基础设施更新.md',
    'Notes/行业洞察与趋势/The Pulse：Token 支出打破预算——接下来怎么办？.md': 'Token支出预算管理分析.md',
    'Notes/行业洞察与趋势/Top 100 生成式 AI 消费应用 — 第 6 版 _ Andreessen Horowitz.md': '生成式AI消费应用Top100.md',
    'Notes/行业洞察与趋势/人工智能人才培养的挑战与对策--AI人才市场结构分析与未来供需趋势 - 中国日报网.md': 'AI人才市场供需趋势分析.md',
    'Notes/行业洞察与趋势/从恐惧到希望，一位经济学家对人工智能的认知转变.md': '经济学家对AI的认知转变.md',
    'Notes/行业洞察与趋势/企业实际在哪里采用 AI _ Andreessen Horowitz.md': '企业AI采用现状分析.md',
    'Notes/行业洞察与趋势/在华企业如何填补AI人才缺口 – McKinsey Greater China.md': '在华企业AI人才缺口与对策.md',
    'Notes/行业洞察与趋势/广泛认可的免费《AI学习路线图》2.0_155c4b97.md': 'AI学习路线图2.0.md',
    'Notes/行业洞察与趋势/物理世界的前沿系统 _ Andreessen Horowitz.md': '物理世界前沿AI系统.md',
    'Notes/金融与量化/FinceptTerminal：开源免费金融终端，支持 A 股基金分析.md': 'FinceptTerminal开源金融终端.md',
    'Notes/金融与量化/Quant-Skills 专栏 2 期  为Agent搭建行情+基本面数据SKill，告别二手轮子。它现在能自己拉行情、拉财报、自动落库了.md': 'Agent金融数据Skill搭建指南.md',
    'Notes/金融与量化/我用 TradingAgents 分析泡泡玛特：近年最强年报，为什么换来35%暴跌？.md': 'TradingAgents多Agent股票分析实践.md',
    'Notes/金融与量化/我用 Tushare + Claude Code，手搓了一套本地股票数据同步系统（已开源）.md': 'Tushare本地股票数据同步系统.md',
}


def main():
    updated = 0
    for old_rel, new_name in RENAMES.items():
        old_path = WORKSPACE / old_rel
        if not old_path.exists():
            print(f'SKIP (not found): {old_rel}')
            continue

        new_path = old_path.parent / new_name
        if old_path == new_path:
            print(f'SAME: {old_rel}')
            continue

        if new_path.exists():
            print(f'SKIP (target exists): {new_path}')
            continue

        try:
            text = old_path.read_text(encoding='utf-8')
            m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
            if m:
                body = text[m.end():]
                body = re.sub(r'^#\s+.*', '# ' + new_name.replace('.md', ''), body, count=1)
                new_text = text[:m.end()] + '\n' + body
            else:
                new_text = re.sub(r'^#\s+.*', '# ' + new_name.replace('.md', ''), text, count=1)
            old_path.write_text(new_text, encoding='utf-8')
            old_path.rename(new_path)
            print(f'OK: {old_rel} -> {new_name}')
            updated += 1
        except Exception as e:
            print(f'ERROR: {old_rel}: {e}')

    print(f'\nTotal renamed: {updated}')


if __name__ == '__main__':
    main()
