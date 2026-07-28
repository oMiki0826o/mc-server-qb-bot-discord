"""
core/qb/process.py

Modification():

- 新增本檔案：集中「呼叫 core/qb/scripts/ 底下的 shell script」這件
  事本身——組出完整路徑、用 asyncio 建立子行程、逾時控制、收集
  stdout／stderr／returncode、量測耗時，並把整個過程寫進 log。
  server.py 只管「什麼時候該呼叫哪支 script」，不管「怎麼呼叫」，
  以後不管是要調整逾時邏輯，還是想幫其他子系統加上一樣的「跑外部
  指令＋記錄」能力，都只需要動這一支檔案。
- 新增 Flow：把同一次操作（例如一次完整的備份流程）串起來的識別碼
  與時間軸紀錄器。同一個 Flow 底下不管跑了幾支 script、經過幾個
  純 Python 步驟，log 裡都看得出來它們屬於同一次操作、各自花了
  多久、結果是什麼，不用再自己土法煉鋼在訊息字串裡塞時間戳記。
- 呼叫 script 一律透過 `bash <path>` 執行，不依賴檔案本身的
  執行權限位元：專案用 git／zip 轉手時常常會遺失 +x，這樣可以少
  一種部署時才會發現的錯誤。

Description():

- resolve_script(name)：把 script 檔名轉成 QB_SCRIPT_DIR 底下的
  絕對路徑，並確認檔案存在。
- StepResult：單一步驟的執行結果（returncode／stdout／stderr／耗時）。
- Flow：一次操作的容器。
    - flow.step(name)：包住一個純 Python 步驟（例如壓縮），量時間、
      寫 log，不吞例外。
    - flow.run_script(name, *args)：包住一次 script 呼叫，多記錄
      stdout／stderr／returncode；預設非零結束碼會丟 TMUXError，
      傳入 check=False 可以自行判讀（例如 status.sh 用非零代表
      「沒有在跑」，那不算錯誤）。
    - flow.finish(success)：流程結束時寫一行總結（總耗時＋成功
      與否），方便在 log 裡快速掃描完整時間軸的起訖。
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import config
from core.logging.log import LogManager
from core.qb.exceptions import TMUXError

logger = LogManager().get_logger("core.qb.process")

# ── 單一 script 呼叫的逾時保護：script 自己也該有逾時邏輯，
#    這裡是最後一道防線，避免子行程真的卡死時拖垮整個 bot ──────────────────────
_DEFAULT_TIMEOUT = 300.0


@dataclass(frozen=True)
class StepResult:
    """單一步驟（通常是一次 script 呼叫）的結果。"""

    name: str
    returncode: int
    stdout: str
    stderr: str
    duration: float

    @property
    def success(self) -> bool:
        return self.returncode == 0


def resolve_script(name: str) -> Path:
    """把 script 檔名轉成實際路徑，檔案不存在就直接丟 TMUXError。"""
    path = config.QB_SCRIPT_DIR / name
    if not path.is_file():
        raise TMUXError(f"找不到 script：{path}")
    return path


async def _execute(path: Path, args: tuple[str, ...], timeout: float) -> tuple[int, str, str]:
    """實際執行一支 script，不記錄任何東西——記錄是 Flow 的責任。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", str(path), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise TMUXError(f"無法執行 {path.name}：{exc}") from exc

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TMUXError(f"{path.name} 執行逾時（超過 {timeout:.0f} 秒），已強制終止")

    stdout = stdout_b.decode("utf-8", "replace").strip()
    stderr = stderr_b.decode("utf-8", "replace").strip()
    return proc.returncode, stdout, stderr


@dataclass
class Flow:
    """一次操作（例如一次完整備份）的容器，串起同一個 Flow ID 底下的所有步驟。"""

    name: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    _started: float = field(default_factory=time.monotonic, repr=False, init=False)

    @property
    def tag(self) -> str:
        return f"{self.name}#{self.id}"

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._started

    @contextlib.contextmanager
    def step(self, name: str):
        """包住一個純 Python 步驟：量時間、寫 log，例外會照常往外丟。"""
        start = time.monotonic()
        logger.info("[%s] %s 開始", self.tag, name)
        try:
            yield
        except Exception as exc:
            duration = time.monotonic() - start
            logger.error("[%s] %s 失敗（耗時 %.1fs）：%s", self.tag, name, duration, exc)
            raise
        else:
            duration = time.monotonic() - start
            logger.info("[%s] %s 完成（耗時 %.1fs）", self.tag, name, duration)

    async def run_script(
        self,
        script: str,
        *args: str,
        timeout: float = _DEFAULT_TIMEOUT,
        check: bool = True,
    ) -> StepResult:
        """包住一次 script 呼叫，記錄 stdout／stderr／returncode／耗時。"""
        path = resolve_script(script)
        logger.info("[%s] 執行 %s %s", self.tag, script, " ".join(args))

        start = time.monotonic()
        returncode, stdout, stderr = await _execute(path, args, timeout)
        duration = time.monotonic() - start
        result = StepResult(script, returncode, stdout, stderr, duration)

        if result.success:
            extra = f"｜stdout: {stdout}" if stdout else ""
            logger.info(
                "[%s] %s 完成（耗時 %.1fs，returncode=0）%s",
                self.tag, script, duration, extra,
            )
        elif not check:
            # check=False 代表呼叫端會自己判讀 returncode（例如 status.sh
            # 用非零代表「沒有在跑」），這不算錯誤，用 INFO 等級記錄就好。
            logger.info(
                "[%s] %s 結束（耗時 %.1fs，returncode=%d，由呼叫端自行判讀）",
                self.tag, script, duration, result.returncode,
            )
        else:
            logger.error(
                "[%s] %s 失敗（耗時 %.1fs，returncode=%d）｜stderr: %s",
                self.tag, script, duration, result.returncode, stderr or "(無)",
            )
            raise TMUXError(
                f"{script} 執行失敗（returncode={result.returncode}）："
                f"{stderr or '無錯誤輸出'}"
            )

        return result

    def finish(self, *, success: bool = True) -> None:
        """記錄整個 Flow 結束，寫一行總結，方便在 log 裡快速掃描起訖。"""
        message = "[%s] Flow 結束，總耗時 %.1fs，結果：%s"
        args = (self.tag, self.elapsed, "成功" if success else "失敗")
        if success:
            logger.info(message, *args)
        else:
            logger.error(message, *args)
