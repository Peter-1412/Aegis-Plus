import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.server import app as api_app
from app.api.feishu_ws_client import main as feishu_ws_main
from app.db.session import init_db
from config.config import settings
import langchain.globals


# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 开启 LangChain 的全局调试和详细日志，以便在终端中显示中间执行过程
langchain.globals.set_verbose(True)
langchain.globals.set_debug(True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化数据库
    logger.info("Initializing database...")
    init_db()

    # 启动时：在一个后台任务中运行飞书长连接客户端
    ws_task = None
    if settings.feishu_app_id and settings.feishu_app_secret:
        logger.info("Detected Feishu config, starting WebSocket client in background...")
        # 修复飞书 SDK 异步循环冲突问题
        # lark_oapi 的 ws client 在启动时会尝试操作 asyncio 事件循环
        # 如果在 FastAPI 已经运行的循环中再开线程跑，可能会遇到 "this event loop is already running"
        # 解决方案：在子线程中创建一个全新的事件循环给飞书客户端用
        def run_feishu_ws():
            # 为当前子线程创建一个新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                feishu_ws_main()
            except Exception as e:
                logger.error(f"Feishu WS client error: {e}")
            finally:
                loop.close()
                
        import threading
        ws_thread = threading.Thread(target=run_feishu_ws, daemon=True)
        ws_thread.start()
        logger.info("Feishu WebSocket client thread started.")
    else:
        logger.warning("Feishu config missing, skipping WebSocket client.")
    
    yield
    
    # 关闭时：线程设为 daemon 会自动随主进程退出
    logger.info("Shutting down...")


# 重新包装 app 以挂载 lifespan
app = FastAPI(title=api_app.title, version=api_app.version, lifespan=lifespan)
app.mount("/", api_app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

