"""
Prompt 管理器 —— 把 prompt 模板从代码中独立出来

为什么要独立管理 prompt？
  1. 版本控制：prompt 改了可以单独 diff，不用在代码 diff 里大海捞针
  2. 可测试：可以单独测试 prompt 的输出质量
  3. 可回滚：prompt 改坏了可以单独回滚，不用回滚代码
  4. 可复用：同一个 prompt 模板可以被多个地方使用

前端类比：
  这就像前端的 i18n 国际化模块 —— 把文本从组件中抽离到独立的 JSON 文件。
  PromptManager.get("report_prompt") 就像 i18n.t("report.template")。

Python 知识点 —— Path 对象：
  Path 是 Python 标准库 pathlib 模块的核心类，用于处理文件路径。
  前端类比：类似 Node.js 的 path 模块，但 API 更优雅。
    Path("/base") / "sub" / "file.txt"  →  Path("/base/sub/file.txt")
    path.read_text()                    →  读取文件内容（类似 fs.readFileSync）
    path.glob("*.md")                   →  查找匹配的文件（类似 glob 库）
    path.stem                           →  不含扩展名的文件名（"report_prompt.md" → "report_prompt"）
"""

from __future__ import annotations

from pathlib import Path

# __file__ 是 Python 的内置变量，表示当前文件的路径。
# Path(__file__).parent 就是当前文件所在的目录。
# 这样无论项目被部署到哪里，都能正确定位 prompts 目录。
PROMPTS_DIR = Path(__file__).parent


class PromptManager:
    """
    Prompt 模板管理器。

    Python 知识点 —— 类（class）：
      类似 JS 的 class，但有一些区别：
        - __init__ 是构造函数（类似 JS 的 constructor()）
        - self 是"当前实例"，类似 JS 的 this，但 Python 要显式写出
        - 以 _ 开头的属性（如 _cache）是"私有的"（约定，非强制）
        - 以 __ 开头的属性（如 __init__）是"魔术方法"，Python 解释器会特殊处理

    Python 知识点 —— 类型标注：
      dict[str, str]  表示"键是字符串，值也是字符串"的字典（类似 JS 的 Record<string, string>）
      Path            表示文件路径对象
    """

    def __init__(self, prompts_dir: Path = PROMPTS_DIR) -> None:
        """
        构造函数。

        参数：
          prompts_dir: prompt 模板文件所在目录，默认是当前文件的同级目录。

        Python 知识点 —— 默认参数：
          prompts_dir: Path = PROMPTS_DIR
          如果调用时不传参数，就用 PROMPTS_DIR 作为默认值。
          类似 JS 的 function(promptsDir = defaultDir) {}
        """
        self._prompts_dir = prompts_dir  # 存储目录路径
        self._cache: dict[str, str] = {}  # 缓存已加载的 prompt 内容

    def get(self, name: str) -> str:
        """
        按名称加载 prompt 模板（不带 .md 扩展名）。

        Python 知识点 —— 缓存模式：
          if name not in self._cache:
              self._cache[name] = ...   # 首次加载，读文件并缓存
          return self._cache[name]      # 返回缓存内容
          这和前端常见的"内存缓存"模式一模一样。
        """
        if name not in self._cache:
            path = self._prompts_dir / f"{name}.md"
            # f"..." 是 f-string，类似 JS 的模板字符串 `...${expr}...`
            # 但用 {} 而不是 ${}。
            # path.read_text(encoding="utf-8") 读取文件全部内容为字符串。
            # .strip() 去掉首尾空白字符（类似 JS 的 .trim()）
            self._cache[name] = path.read_text(encoding="utf-8").strip()
        return self._cache[name]

    def render(self, name: str, **kwargs: object) -> str:
        """
        加载并渲染 prompt 模板（替换变量）。

        参数：
          name:    模板名称
          **kwargs: 要替换的变量，如 repo_url="https://..." summary="..."

        Python 知识点 —— **kwargs（关键字参数收集）：
          **kwargs 把所有"关键字参数"收集成一个字典。
          调用 render("report_prompt", repo_url="https://...", summary="{}")
          时，kwargs 就是 {"repo_url": "https://...", summary: "{}"}
          前端没有直接对应，但可以理解为 ...rest 参数收集对象。

        Python 知识点 —— str.format()：
          "Hello {name}".format(name="World")  →  "Hello World"
          类似 JS 的 `Hello ${name}`，但用 .format() 方法。
          模板中的 {repo_url} 和 {summary} 会被替换为实际值。
        """
        template = self.get(name)
        return template.format(**kwargs)

    def list_prompts(self) -> list[str]:
        """
        列出所有可用的 prompt 模板名称。

        Python 知识点 —— 生成器表达式 + sorted()：
          sorted(p.stem for p in self._prompts_dir.glob("*.md"))
          分解来看：
            self._prompts_dir.glob("*.md")  →  查找所有 .md 文件，返回一个"生成器"
            p.stem for p in ...             →  提取每个文件的不含扩展名的名字
            sorted(...)                     →  排序（字母顺序）
          生成器表达式 (expr for item in iterable) 类似 JS 的 .map()，但惰性求值。
        """
        return sorted(p.stem for p in self._prompts_dir.glob("*.md"))

    def clear_cache(self) -> None:
        """清空缓存，下次 get() 会重新从磁盘读取。"""
        self._cache.clear()
        # dict.clear() 清空字典所有内容，类似 JS 的 Map.clear()
