from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import create_pool, close_pool
from .routers.analytics import router as analytics_router
from .routers.playlists import router as playlists_router
from .routers.recommendations import router as recommendations_router
from .routers.settings import router as settings_router
from .routers.auth import router as auth_router
from .routers.chat import router as chat_router
from .routers.matcher import router as matcher_router
from .routers.search import router as search_router
from .routers.srs import router as srs_router
from .routers.videos import router as videos_router
from .routers.words import router as words_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()
    yield
    await close_pool()


app = FastAPI(title="YouGlish Clone", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(search_router,  prefix="/api")        # existing: /api/search, /api/suggest, etc.
app.include_router(auth_router,    prefix="/api/v1")     # /api/v1/auth/register, /api/v1/auth/login
app.include_router(words_router,   prefix="/api/v1")     # /api/v1/words/knowledge, /api/v1/words/{type}/{id}/status
app.include_router(videos_router,  prefix="/api/v1")     # /api/v1/videos/{video_id}/reading-stats
app.include_router(matcher_router, prefix="/api/v1")     # /api/v1/sentences/match
app.include_router(srs_router,     prefix="/api/v1")     # /api/v1/srs/check-answer, /magic-sentences, /cloze-questions
app.include_router(chat_router,    prefix="/api/v1")     # /api/v1/chat/sessions, /api/v1/chat/sessions/{id}/messages
app.include_router(analytics_router,  prefix="/api/v1")  # /api/v1/analytics/...
app.include_router(playlists_router,      prefix="/api/v1")  # /api/v1/playlists/generate
app.include_router(recommendations_router, prefix="/api/v1")  # /api/v1/recommendations/sentences, /videos
app.include_router(settings_router,        prefix="/api/v1")  # /api/v1/settings/preferences

frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
