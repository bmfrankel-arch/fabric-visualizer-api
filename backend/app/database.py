import sqlite3
from pathlib import Path
from .config import settings


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(str(settings.database_path))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS fabrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filename TEXT NOT NULL UNIQUE,
            category TEXT DEFAULT '',
            color_tags TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS furniture (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filename TEXT NOT NULL UNIQUE,
            source_url TEXT DEFAULT '',
            source_site TEXT DEFAULT '',
            category TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS visualizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fabric_id INTEGER NOT NULL,
            furniture_id INTEGER NOT NULL,
            result_filename TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (fabric_id) REFERENCES fabrics(id),
            FOREIGN KEY (furniture_id) REFERENCES furniture(id)
        );

        CREATE TABLE IF NOT EXISTS scraper_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_name TEXT NOT NULL UNIQUE,
            base_url TEXT NOT NULL,
            product_selector TEXT DEFAULT '',
            image_selector TEXT DEFAULT '',
            name_selector TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1
        );
    """)
    db.commit()
    db.close()
