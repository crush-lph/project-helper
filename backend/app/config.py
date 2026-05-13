"""
配置管理模块 —— 项目的"环境变量 + 配置中心"

前端类比：
  这个文件相当于前端的 .env + vite.config.js 中的 defineConfig 部分。
  pydantic-settings 就像 dotenv + zod 的组合：
    - 从 .env 文件读取环境变量（像 dotenv）
    - 自动校验类型和默认值（像 zod schema）

Python 知识点：
  - from __future__ import annotations：让类型标注用字符串形式求值，
    而不是立即求值。Python 3.10+ 的好习惯，避免循环导入问题。
  - Field()：Pydantic 的字段描述，可以设置默认值、别名（alias）、
    校验规则。alias 的作用是让环境变量名和 Python 属性名可以不同。
  - @property：把方法伪装成属性访问。类似 JS 的 get xxx() {}。
  - @lru_cache：函数级别的缓存装饰器。第一次调用后结果被缓存，
    后续调用直接返回缓存值。类似 React 的 useMemo，但作用于函数。
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# pydantic-settings 是 Pydantic 的扩展，专门用于管理配置。
# BaseSettings 是基类，它会自动从环境变量和 .env 文件中读取值。
# SettingsConfigDict 用于配置这个 Settings 类自身的行为（比如 .env 文件路径）。


def _detect_ssl_cert() -> str | None:
    """Auto-detect a valid SSL CA bundle path.

    Python.org macOS builds ship with their own OpenSSL that cannot find
    the system certificate store.  This function tries certifi first,
    then falls back to common system paths.
    """
    env_path = os.environ.get("SSL_CERT_FILE")
    if env_path and Path(env_path).exists():
        return env_path
    try:
        import certifi
        return certifi.where()
    except ImportError:
        pass
    for p in ("/etc/ssl/cert.pem", "/etc/pki/tls/certs/ca-bundle.crt"):
        if Path(p).exists():
            return p
    return None


class Settings(BaseSettings):
    """
    应用配置类。

    前端类比：相当于一个 TypeScript interface + 校验逻辑的合体。
    每个属性都声明了类型和默认值，Pydantic 会自动：
      1. 从环境变量中读取值（比如 DEEPSEEK_API_KEY 会自动映射到 deepseek_api_key）
      2. 类型转换（字符串 "90" 会自动转成 int 90）
      3. 校验（如果类型不对会报错）

    Python 知识点 —— 类型标注：
      name: str = ""       表示 name 是字符串类型，默认值是空串
      llm_timeout: int = 90  表示 llm_timeout 是整数类型，默认值 90
      data_dir: Path = ...   表示 data_dir 是 Path 对象（不是字符串！）

    Python 知识点 —— Field(alias=...)：
      alias 指定环境变量名。比如 data_dir 的 alias 是 "PROJECT_HELPER_DATA_DIR"，
      所以设置环境变量 PROJECT_HELPER_DATA_DIR=/some/path 就会映射到 data_dir 属性。
      这样做的好处是：Python 代码里用简洁的 data_dir，环境变量用全大写带前缀的命名。
    """

    # LLM 相关配置
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # 存储配置
    data_dir: Path = Path(".project-helper-data")
    allowed_hosts: str = "github.com,www.github.com"

    # LLM 调用配置 —— 超时和重试
    llm_timeout: int = Field(default=90, ge=5, le=300)
    llm_max_retries: int = Field(default=3, ge=0, le=10)

    # Agent 配置
    agent_max_iterations: int = Field(default=8, ge=1, le=50)
    agent_max_execution_time: int = Field(default=60, ge=10, le=300)

    # 环境配置
    environment: str = Field(default="development", pattern="^(development|staging|production)$")
    allowed_origins: str = "http://localhost,http://localhost:5173,http://127.0.0.1"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def allowed_origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    # model_config 告诉 Pydantic 如何读取配置
    model_config = SettingsConfigDict(
        env_file=".env",          # 从 .env 文件读取（类似 dotenv）
        extra="ignore",           # 忽略未声明的环境变量，不会报错
        populate_by_name=True,    # 允许用属性名（如 data_dir）或别名（如 PROJECT_HELPER_DATA_DIR）赋值
    )

    # ---- 以下是"计算属性"（@property），不是从环境变量读取的 ----

    @property
    def clone_dir(self) -> Path:
        """
        仓库克隆目录 = data_dir / "repos"

        Python 知识点 —— Path 的 / 运算符：
          Path("/base") / "sub"  结果是 Path("/base/sub")
          这就像 path.join()，但用 / 运算符更直观。
          前端类比：类似 Node.js 的 path.join(base, 'repos')
        """
        return self.data_dir / "repos"

    @property
    def db_path(self) -> Path:
        """SQLite 数据库文件路径"""
        return self.data_dir / "project_helper.sqlite3"

    @property
    def allowed_host_set(self) -> set[str]:
        """
        把逗号分隔的字符串转成集合（set）。

        Python 知识点 —— 集合推导式：
          {host.strip().lower() for host in self.allowed_hosts.split(",") if host.strip()}
          等价于 JS: [...new Set(allowed_hosts.split(",").map(h => h.trim().toLowerCase()).filter(Boolean))]
          但 Python 的集合推导式更简洁。

        Python 知识点 —— set vs list：
          set 是无序不重复集合，查找效率 O(1)，类似 JS 的 Set。
          list 是有序可重复数组，查找效率 O(n)，类似 JS 的 Array。
          这里用 set 是因为只需要判断"某个 host 是否在允许列表中"。
        """
        return {host.strip().lower() for host in self.allowed_hosts.split(",") if host.strip()}

    @property
    def ssl_cert_file(self) -> str | None:
        return _detect_ssl_cert()

    @property
    def ssl_cert_configured(self) -> bool:
        return self.ssl_cert_file is not None


@lru_cache  # 缓存装饰器：第一次调用创建 Settings 实例，后续调用直接返回缓存
def get_settings() -> Settings:
    """
    获取全局配置单例。

    前端类比：类似 React Context 中的 Provider，整个应用共享同一个配置实例。
    @lru_cache 保证这个函数只执行一次，之后调用直接返回缓存结果。

    Python 知识点 —— lru_cache：
      @lru_cache 会记住函数的输入参数和对应的输出结果。
      如果用相同参数再次调用，直接返回缓存值，不再执行函数体。
      这里没有参数，所以永远返回同一个 Settings 实例 —— 相当于单例模式。
    """
    settings = Settings()                              # 创建配置实例，自动从 .env 读取
    settings.data_dir.mkdir(parents=True, exist_ok=True)  # 确保数据目录存在
    settings.clone_dir.mkdir(parents=True, exist_ok=True) # 确保克隆目录存在
    # parents=True：如果父目录不存在也一起创建（类似 mkdir -p）
    # exist_ok=True：如果目录已存在不报错（类似 mkdir -p 的行为）
    return settings
