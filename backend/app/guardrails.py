"""
安全护栏模块 —— Prompt 注入检测

这个模块的职责很简单：检测用户输入是否包含"Prompt 注入"攻击。

什么是 Prompt 注入？
  LLM 应用中，用户输入会被拼接到 prompt 里发给模型。
  攻击者可能在输入中嵌入"忽略之前的指令"之类的话，试图：
    - 让模型泄露系统 prompt
    - 让模型执行非预期行为
  前端类比：就像 XSS 注入，用户在输入框里写 <script>alert(1)</script>。

防御策略：
  用正则表达式匹配已知的注入模式。这不是万能的（没有万能方案），
  但能挡住最常见的攻击。真正的防御需要多层：输入过滤 + 输出校验 + 模型级防护。

Python 知识点 —— re 模块：
  re.compile()  预编译正则表达式，提高多次匹配的效率。
  re.IGNORECASE  标志位，忽略大小写。类似 JS 的 /pattern/i。
  pattern.search(text)  在 text 中搜索匹配。类似 JS 的 pattern.test(text)。

Python 知识点 —— 模块级常量：
  _INJECTION_PATTERNS 以 _ 开头，表示"模块内部使用"（约定，非强制）。
  定义在模块顶层，导入时就编译好，不会每次调用 check_prompt_injection 都重新编译。
"""

from __future__ import annotations  # 让类型标注延迟求值，Python 3.10+ 好习惯

import re  # Python 标准库的正则表达式模块，不需要 npm install

# 预编译的注入检测模式列表
# 每个 re.compile() 创建一个正则表达式对象，类似 JS 的 new RegExp()
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    # "ignore previous instructions" 及其变体
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?prior\s+instructions", re.IGNORECASE),

    # "disregard ... instructions"（"无视指令"的另一种说法）
    re.compile(r"disregard\s+(all\s+)?(previous|prior|earlier)\s+instructions", re.IGNORECASE),

    # "forget ... instructions/rules"（"忘记指令"）
    re.compile(r"forget\s+(all\s+)?(previous|prior|your)\s*(instructions|rules)", re.IGNORECASE),
    re.compile(r"forget\s+everything", re.IGNORECASE),

    # "you are now ..."（角色劫持：让模型扮演另一个角色）
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),

    # "new instructions:"（声称有新指令）
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),

    # "override ... instructions"（覆盖指令）
    re.compile(r"override\s+(all\s+)?(your\s+)?instructions", re.IGNORECASE),

    # ChatML 格式的 system 注入：只匹配行首的 "system:"，避免误报正常讨论
    # (?:^|\n) 表示"行首或换行后"，(?:...) 是非捕获组
    re.compile(r"(?:^|\n)\s*system\s*:\s", re.IGNORECASE),

    # ChatML 特殊标签注入：<|im_start|> 是 ChatML 格式的特殊标记
    re.compile(r"<\|im_start\|>\s*system", re.IGNORECASE),

    # Llama 指令格式注入：[INST]...[/INST] 是 Llama 模型的指令标记
    re.compile(r"\[INST\].*\[/INST\]", re.IGNORECASE),
]


def check_prompt_injection(text: str) -> bool:
    """
    检测文本是否包含可疑的 Prompt 注入模式。

    参数：
      text: 用户输入的文本

    返回：
      True = 检测到可疑模式，应该拒绝
      False = 未检测到，可以放行

    Python 知识点 —— 函数签名：
      def check_prompt_injection(text: str) -> bool:
        - def：定义函数（类似 JS 的 function 或 const fn = () => {}）
        - text: str：参数 text 的类型是 str（字符串）
        - -> bool：返回值类型是 bool（布尔值）
        - Python 的类型标注是可选的，不会影响运行，但能帮助 IDE 和类型检查器

    Python 知识点 —— for...in 循环：
      for pattern in _INJECTION_PATTERNS:
        类似 JS 的 for (const pattern of _INJECTION_PATTERNS)
        遍历列表中的每个元素。

    Python 知识点 —— 提前返回（early return）：
      一旦发现匹配就立刻 return True，不再检查剩余模式。
      这和 JS 的行为完全一样。
    """
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):  # search() 在任意位置查找匹配（类似 JS 的 .test()）
            return True
    return False
