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

CREATE TABLE IF NOT EXISTS raw_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id TEXT NOT NULL,
    url TEXT NOT NULL,
    is_premium INTEGER NOT NULL DEFAULT 0,
    title TEXT,
    price_raw TEXT,
    location TEXT,
    details TEXT,
    features TEXT,
    description TEXT,
    image_url TEXT,
    card_text TEXT,
    transaction_type TEXT,
    city TEXT,
    source_url TEXT,
    scraped_at TEXT DEFAULT (datetime('now')),
    detail_scraped INTEGER NOT NULL DEFAULT 0,
    UNIQUE (city, transaction_type, ad_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_listings_ad_id ON raw_listings(ad_id);
CREATE INDEX IF NOT EXISTS idx_raw_listings_transaction
    ON raw_listings(transaction_type);

CREATE TABLE IF NOT EXISTS raw_listing_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    title_full TEXT,
    description_full TEXT,
    property_type TEXT,
    land_surface_raw TEXT,
    condition_raw TEXT,
    age_raw TEXT,
    orientation_raw TEXT,
    floor_type_raw TEXT,
    num_floors_raw TEXT,
    latitude REAL,
    longitude REAL,
    location_id TEXT,
    waze_url TEXT,
    surface_raw TEXT,
    rooms_raw TEXT,
    bedrooms_raw TEXT,
    bathrooms_raw TEXT,
    price_detail_raw TEXT,
    features_full TEXT,
    images_json TEXT,
    image_count INTEGER NOT NULL DEFAULT 0,
    agency_name TEXT,
    agency_url TEXT,
    agency_logo TEXT,
    agency_ref TEXT,
    raw_json TEXT,
    scraped_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_listing_details_ad_id
    ON raw_listing_details(ad_id);