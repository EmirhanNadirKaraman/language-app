from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import create_pool, close_pool, get_pool
from .routers.analytics import router as analytics_router
from .routers.books import router as books_router
from .routers.reading import router as reading_router
from .routers.reminders import router as reminders_router
from .routers.insights import router as insights_router
from .routers.phrases import router as phrases_router
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
from .routers.content_requests import router as content_requests_router
from .routers.notifications import router as notifications_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()

    # Seed phrase_table from the verb dict already loaded by matcher_service.
    # ON CONFLICT DO NOTHING makes this safe on every restart.
    try:
        from .services import matcher_service, phrase_service
        pool = get_pool()
        await phrase_service.seed_from_blueprint_map(
            pool, matcher_service.get_blueprint_map(), language="de"
        )
    except Exception:
        # Seed failure is non-fatal — app still starts; seed manually via POST /api/v1/phrases/seed
        import logging
        logging.getLogger(__name__).warning("Phrase table seed failed at startup", exc_info=True)

    # Seed grammar_rule_table with the curated German rule set.
    # ON CONFLICT (slug, language) DO NOTHING makes this idempotent.
    try:
        from .services import grammar_service
        pool = get_pool()
        await grammar_service.seed_rules(pool, language="de")
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Grammar rule seed failed at startup", exc_info=True)

    yield
    await close_pool()


app = FastAPI(title="YouGlish Clone", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(search_router,          prefix="/api")       # /api/search, /api/suggest, etc.
app.include_router(auth_router,            prefix="/api/v1")    # /api/v1/auth/register, /api/v1/auth/login
app.include_router(words_router,           prefix="/api/v1")    # /api/v1/words/knowledge, /api/v1/words/{type}/{id}/status
app.include_router(videos_router,          prefix="/api/v1")    # /api/v1/videos/{video_id}/reading-stats
app.include_router(matcher_router,         prefix="/api/v1")    # /api/v1/sentences/match
app.include_router(phrases_router,         prefix="/api/v1")    # /api/v1/phrases, /api/v1/phrases/match, /api/v1/phrases/seed
app.include_router(srs_router,             prefix="/api/v1")    # /api/v1/srs/check-answer, /magic-sentences, /cloze-questions
app.include_router(chat_router,            prefix="/api/v1")    # /api/v1/chat/sessions, /api/v1/chat/sessions/{id}/messages
app.include_router(analytics_router,       prefix="/api/v1")    # /api/v1/analytics/...
app.include_router(insights_router,        prefix="/api/v1")    # /api/v1/insights/cards, /prep, /prep/generate-examples
app.include_router(playlists_router,       prefix="/api/v1")    # /api/v1/playlists/generate
app.include_router(recommendations_router, prefix="/api/v1")    # /api/v1/recommendations/sentences, /videos, /items
app.include_router(settings_router,        prefix="/api/v1")    # /api/v1/settings/preferences
app.include_router(books_router,           prefix="/api/v1")    # /api/v1/books/upload, /books, /books/{id}/...
app.include_router(reading_router,         prefix="/api/v1")    # /api/v1/books/{id}/selections, /reading/translate, /reading/explain
app.include_router(reminders_router,       prefix="/api/v1")    # /api/v1/reminders/summary
app.include_router(content_requests_router, prefix="/api/v1")  # /api/v1/content-requests
app.include_router(notifications_router,    prefix="/api/v1")  # /api/v1/notifications/stream

frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
