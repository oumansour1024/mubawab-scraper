CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id TEXT UNIQUE,
    title TEXT,
    price INTEGER,
    price_per_sqm REAL,
    area_sqm REAL,
    rooms INTEGER,
    bedrooms INTEGER,
    bathrooms INTEGER,
    property_type TEXT,
    transaction_type TEXT,
    city TEXT,
    neighbourhood TEXT,
    latitude REAL,
    longitude REAL,
    agency_name TEXT,
    description TEXT,
    amenities TEXT,
    image_url TEXT,
    url TEXT UNIQUE,
    is_promoted INTEGER DEFAULT 0,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scraping_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT,
    transaction_type TEXT,
    last_scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_pages INTEGER,
    total_results INTEGER,
    page_size INTEGER,
    pages_scraped INTEGER
);

CREATE TABLE IF NOT EXISTS villes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    link TEXT NOT NULL,
    attrNameurl TEXT
);