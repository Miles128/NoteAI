# NOTE: 运行时由 prompts/yaml/profile.yaml 优先加载，本文件中的常量仅作备用参考
PROFILE_EXTRACT_PROMPT = """从用户消息中提取结构化的个人信息。输出 JSON 格式，没有相关信息时对应字段为 null 或空数组。

```json
{
  "profession": "提取到的职业，没有则为null",
  "expertise_areas": ["领域1", "领域2"],
  "interests": ["兴趣1"],
  "learning_goals": ["目标1"],
  "facts": ["关于用户的事实1", "事实2"]
}
```

用户消息：{message}

输出："""

PROFILE_INFERENCE_PROMPT = """你是一个用户画像分析专家。根据以下信号，推理用户画像的增量更新。

## 当前画像
{current_profile}

## 新信号
{signals}

## 要求
1. 只输出需要更新或新增的字段，不需要更新的字段不要输出
2. 对于列表字段（expertise_areas, interests, learning_goals），输出完整的新列表（合并旧值和新值，去重）
3. 对于 facts，只输出新增的事实
4. 严格输出 JSON，不要加任何解释

输出 JSON："""

PROFILE_SUMMARY_PROMPT = """请将以下用户画像信息压缩为一段简洁的文字描述（200字以内），用于注入到 AI 助手的提示词中，让助手了解用户特征。

用户画像：
{profile_json}

简洁描述："""
