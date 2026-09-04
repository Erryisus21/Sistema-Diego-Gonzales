from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.routers import busqueda, wishlist, categorias, push, producto_detalle, ofertas, auth
from app.jobs.detectar_ofertas import detectar_ofertas
from app.jobs.detectar_bajadas_wishlist import detectar_bajadas


scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Job 1: Scraping de ofertas cada 6 horas
    scheduler.add_job(
        detectar_ofertas,
        trigger=IntervalTrigger(hours=6),
        id="detectar_ofertas",
        replace_existing=True,
    )

    # Job 2: Revisar bajadas en wishlist cada 2 horas
    scheduler.add_job(
        detectar_bajadas,
        trigger=IntervalTrigger(hours=2),
        id="detectar_bajadas_wishlist",
        replace_existing=True,
    )

    scheduler.start()
    print("Scheduler iniciado: scraping cada 6h, notificaciones cada 2h")

    yield

    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(busqueda.router)
app.include_router(wishlist.router)
app.include_router(categorias.router)
app.include_router(push.router)
app.include_router(producto_detalle.router)
app.include_router(ofertas.router)
app.include_router(auth.router)


@app.get("/")
def root():
    return {"mensaje": "SAVVR API activa"}


