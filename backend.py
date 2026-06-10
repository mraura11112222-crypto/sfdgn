import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncpg

app = FastAPI(title="Leaderboard & Nickname API")

# --- CORS SOZLAMALARI (CORS port xatolarini oldini olish) ---
# Front-end loyihangiz ishlaydigan barcha lokal portlarni va "*" (barcha) manzillarni qamrab olamiz
origins = [
    "http://localhost",
    "http://localhost:5500",  # Live Server standart porti
    "http://127.0.0.1:5500",  # Live Server muqobil IP manzili
    "http://localhost:3000",  # React / Next.js porti
    "http://localhost:5173",  # Vite (React/Vue) porti
    "*",                      # Barcha tashqi manzillar uchun universal ruxsat
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST, OPTIONS, PUT, DELETE barchasiga ruxsat
    allow_headers=["*"],  # Content-Type, Authorization kabi barcha sarlavhalarga ruxsat
)

DATABASE_URL = "postgresql://neondb_owner:npg_VDSncpbaeN16@ep-noisy-dream-aqm9uc86-pooler.c-8.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

db_pool: Optional[asyncpg.Pool] = None

class NicknameSchema(BaseModel):
    nickname: str

class ResultSchema(BaseModel):
    nickname: str
    score: int
    gamesPlayed: int


@app.on_event("startup")
async def startup():
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    nickname TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS leaderboard (
                    id SERIAL PRIMARY KEY,
                    nickname TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    games_played INTEGER NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        print("Bazaga ulanish muvaffaqiyatli bajarildi va jadvallar tekshirildi.")
    except Exception as e:
        print(f"Bazaga ulanishda xatolik: {e}")


@app.on_event("shutdown")
async def shutdown():
    global db_pool
    if db_pool:
        await db_pool.close()


# --- API Yo'nalishlari ---

@app.post("/namepost", status_code=status.HTTP_201_CREATED)
async def save_nickname(data: NicknameSchema):
    query = """
        INSERT INTO users (nickname) VALUES ($1)
        ON CONFLICT (nickname) DO NOTHING
        RETURNING id;
    """
    async with db_pool.acquire() as conn:
        await conn.fetchval(query, data.nickname)
        return {"status": "success", "message": f"Nickname '{data.nickname}' muvaffaqiyatli saqlandi."}


@app.get("/name")
async def get_current_nickname():
    query = "SELECT nickname FROM users ORDER BY id DESC LIMIT 1;"
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(query)
        if not row:
            raise HTTPException(status_code=404, detail="Hozircha hech qanday nickname saqlanmagan.")
        return {"nickname": row["nickname"]}


@app.post("/natijapost")
async def save_result(data: ResultSchema):
    insert_query = """
        INSERT INTO leaderboard (nickname, score, games_played) 
        VALUES ($1, $2, $3);
    """
    async with db_pool.acquire() as conn:
        await conn.execute(insert_query, data.nickname, data.score, data.gamesPlayed)
        return {"status": "success", "message": "Natija muvaffaqiyatli saqlandi."}


@app.get("/natija")
async def get_leaderboard():
    query = """
        SELECT nickname, score, games_played as "gamesPlayed" 
        FROM leaderboard 
        ORDER BY score DESC 
        LIMIT 100;
    """
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query)
        results = [dict(row) for row in rows]
        return {"results": results}