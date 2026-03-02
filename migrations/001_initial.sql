-- ============================================================
-- SD STOCK — Initial Database Migration
-- PostgreSQL 15 / Supabase
-- ============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- 1. species
-- ============================================================
CREATE TABLE IF NOT EXISTS species (
    id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL
);

-- ============================================================
-- 2. strains
-- ============================================================
CREATE TABLE IF NOT EXISTS strains (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    species_id UUID         NOT NULL REFERENCES species(id) ON DELETE RESTRICT,
    code       VARCHAR(50)  NOT NULL UNIQUE,
    full_name  VARCHAR(200) NOT NULL,
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE
);

-- ============================================================
-- 3. rooms
-- ============================================================
CREATE TABLE IF NOT EXISTS rooms (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_code   VARCHAR(20)  NOT NULL UNIQUE,   -- e.g. 'KP800','KP900','KP1000'
    description TEXT,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE
);

-- ============================================================
-- 4. weight_references
-- ============================================================
CREATE TABLE IF NOT EXISTS weight_references (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strain_id  UUID           NOT NULL REFERENCES strains(id) ON DELETE RESTRICT,
    age_week   SMALLINT       NOT NULL CHECK (age_week BETWEEN 3 AND 10),
    age_half   VARCHAR(3)     CHECK (age_half IN ('1st','2nd') OR age_half IS NULL),
    sex        CHAR(1)        NOT NULL CHECK (sex IN ('M','F')),
    weight_min NUMERIC(6,2)   NOT NULL,
    weight_avg NUMERIC(6,2)   NOT NULL,
    weight_max NUMERIC(6,2)   NOT NULL
);

-- ============================================================
-- 5. size_weight_mapping
-- ============================================================
CREATE TABLE IF NOT EXISTS size_weight_mapping (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strain_id  UUID           NOT NULL REFERENCES strains(id) ON DELETE RESTRICT,
    age_week   SMALLINT       NOT NULL CHECK (age_week BETWEEN 3 AND 10),
    age_half   VARCHAR(3)     CHECK (age_half IN ('1st','2nd') OR age_half IS NULL),
    sex        CHAR(1)        NOT NULL CHECK (sex IN ('M','F')),
    size_code  CHAR(1)        NOT NULL CHECK (size_code IN ('S','M','L')),
    weight_min NUMERIC(6,2)   NOT NULL,
    weight_max NUMERIC(6,2)   NOT NULL,
    UNIQUE (strain_id, age_week, age_half, sex, size_code)
);

-- ============================================================
-- 6. price_tables  (defined before customers for FK)
-- ============================================================
CREATE TABLE IF NOT EXISTS price_tables (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name     VARCHAR(100) NOT NULL,
    strain_id      UUID         NOT NULL REFERENCES strains(id) ON DELETE RESTRICT,
    age_week       SMALLINT     NOT NULL CHECK (age_week BETWEEN 3 AND 10),
    unit_price     INT          NOT NULL CHECK (unit_price >= 0),
    effective_date DATE         NOT NULL,
    is_special     BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ============================================================
-- 7. customers
-- ============================================================
CREATE TABLE IF NOT EXISTS customers (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_code  VARCHAR(50)  NOT NULL UNIQUE,
    company_name   VARCHAR(200) NOT NULL,
    customer_group VARCHAR(100),
    price_table_id UUID         REFERENCES price_tables(id) ON DELETE SET NULL,
    discount_rate  NUMERIC(5,2) NOT NULL DEFAULT 0.00,
    trade_type     VARCHAR(50),
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE
);

-- ============================================================
-- 8. professors
-- ============================================================
CREATE TABLE IF NOT EXISTS professors (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID         NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    phone       VARCHAR(30),
    email       VARCHAR(200),
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE
);

-- ============================================================
-- 9. daily_inventory
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_inventory (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_date         DATE         NOT NULL,
    room_id             UUID         NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
    strain_id           UUID         NOT NULL REFERENCES strains(id) ON DELETE RESTRICT,
    responsible_person  VARCHAR(100),
    age_week            SMALLINT     NOT NULL CHECK (age_week BETWEEN 3 AND 10),
    age_half            VARCHAR(3)   CHECK (age_half IN ('1st','2nd') OR age_half IS NULL),
    sex                 CHAR(1)      NOT NULL CHECK (sex IN ('M','F')),
    dob_start           DATE,
    dob_end             DATE,
    total_count         INT          NOT NULL DEFAULT 0,
    reserved_count      INT          NOT NULL DEFAULT 0,
    adjust_cut_count    INT          NOT NULL DEFAULT 0,
    -- rest_count은 total - reserved - adjust_cut로 자동 계산
    rest_count          INT GENERATED ALWAYS AS
                            (total_count - reserved_count - adjust_cut_count) STORED,
    cage_count          INT,
    cage_size_breakdown JSONB,   -- e.g. {"S":10,"M":20,"L":71}
    animal_type         VARCHAR(30)  NOT NULL DEFAULT 'standard'
                            CHECK (animal_type IN ('standard','TP','DOB_specific','retire')),
    remark              TEXT,
    UNIQUE (record_date, room_id, strain_id, age_week, age_half, sex)
);

-- ============================================================
-- 10. cut_events
-- ============================================================
CREATE TABLE IF NOT EXISTS cut_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inventory_id UUID    NOT NULL REFERENCES daily_inventory(id) ON DELETE CASCADE,
    cut_date     DATE    NOT NULL,
    cut_count    INT     NOT NULL CHECK (cut_count > 0),
    is_same_day  BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE = CUT:(52) notation
    noted_by     UUID,   -- Supabase Auth user ID
    notes        TEXT
);

-- ============================================================
-- 11. inquiries
-- ============================================================
CREATE TABLE IF NOT EXISTS inquiries (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inquiry_no       VARCHAR(50)  NOT NULL UNIQUE,
    inquiry_date     DATE         NOT NULL DEFAULT CURRENT_DATE,
    customer_id      UUID         NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    professor_id     UUID         REFERENCES professors(id) ON DELETE SET NULL,
    delivery_date    DATE,
    strain_id        UUID         NOT NULL REFERENCES strains(id) ON DELETE RESTRICT,
    age_week         SMALLINT     NOT NULL CHECK (age_week BETWEEN 3 AND 10),
    age_half         VARCHAR(3)   CHECK (age_half IN ('1st','2nd') OR age_half IS NULL),
    sex              CHAR(1)      NOT NULL CHECK (sex IN ('M','F')),
    weight_specified BOOLEAN      NOT NULL DEFAULT FALSE,
    weight_min       NUMERIC(6,2),
    weight_max       NUMERIC(6,2),
    quantity         INT          NOT NULL CHECK (quantity > 0),
    extra_quantity   INT          NOT NULL DEFAULT 0,
    stock_status     VARCHAR(30)  NOT NULL DEFAULT 'pending'
                         CHECK (stock_status IN (
                             'pending',
                             'in_stock_auto',
                             'in_stock_manual',
                             'out_of_stock_auto',
                             'out_of_stock_manual',
                             'adjusting',
                             'farm_check_requested',
                             'farm_check_in_progress',
                             'farm_available',
                             'farm_unavailable'
                         )),
    stage            VARCHAR(20)  NOT NULL DEFAULT 'inquiry'
                         CHECK (stage IN ('inquiry','reservation','closed','auto_closed')),
    farm_note        TEXT,
    sales_memo       TEXT
);

-- ============================================================
-- 12. inquiry_history
-- ============================================================
CREATE TABLE IF NOT EXISTS inquiry_history (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inquiry_id  UUID           NOT NULL REFERENCES inquiries(id) ON DELETE CASCADE,
    changed_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    changed_by  UUID,          -- Supabase Auth user ID
    field_name  VARCHAR(100)   NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    action      VARCHAR(50)    NOT NULL  -- 'create','update','delete'
);

-- ============================================================
-- 13. reservations
-- ============================================================
CREATE TABLE IF NOT EXISTS reservations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_no   VARCHAR(50)  NOT NULL UNIQUE,
    inquiry_id       UUID         NOT NULL REFERENCES inquiries(id) ON DELETE RESTRICT,
    delivery_date    DATE         NOT NULL,
    customer_id      UUID         NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    professor_id     UUID         REFERENCES professors(id) ON DELETE SET NULL,
    strain_id        UUID         NOT NULL REFERENCES strains(id) ON DELETE RESTRICT,
    age_week         SMALLINT     NOT NULL CHECK (age_week BETWEEN 3 AND 10),
    age_half         VARCHAR(3)   CHECK (age_half IN ('1st','2nd') OR age_half IS NULL),
    sex              CHAR(1)      NOT NULL CHECK (sex IN ('M','F')),
    quantity         INT          NOT NULL CHECK (quantity > 0),
    price_table_id   UUID         REFERENCES price_tables(id) ON DELETE SET NULL,
    is_special_price BOOLEAN      NOT NULL DEFAULT FALSE,
    stage            VARCHAR(30)  NOT NULL DEFAULT 'pending'
);

-- ============================================================
-- 14. order_confirmations
-- ============================================================
CREATE TABLE IF NOT EXISTS order_confirmations (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    confirmation_no   VARCHAR(50)  NOT NULL UNIQUE,
    reservation_id    UUID         NOT NULL REFERENCES reservations(id) ON DELETE RESTRICT,
    delivery_date     DATE         NOT NULL,
    customer_id       UUID         NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    strain_id         UUID         NOT NULL REFERENCES strains(id) ON DELETE RESTRICT,
    age_week          SMALLINT     NOT NULL CHECK (age_week BETWEEN 3 AND 10),
    age_half          VARCHAR(3)   CHECK (age_half IN ('1st','2nd') OR age_half IS NULL),
    sex               CHAR(1)      NOT NULL CHECK (sex IN ('M','F')),
    confirmed_quantity INT         NOT NULL CHECK (confirmed_quantity > 0),
    unit_price        INT          NOT NULL CHECK (unit_price >= 0),
    total_price       INT GENERATED ALWAYS AS (confirmed_quantity * unit_price) STORED,
    stage             VARCHAR(20)  NOT NULL DEFAULT 'confirmed'
                          CHECK (stage IN ('confirmed','dispatched','cancelled'))
);

-- ============================================================
-- 15. order_allocations
-- ============================================================
CREATE TABLE IF NOT EXISTS order_allocations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID        NOT NULL,
    order_type      VARCHAR(30) NOT NULL,  -- 'reservation' | 'confirmation'
    inventory_id    UUID        NOT NULL REFERENCES daily_inventory(id) ON DELETE RESTRICT,
    allocated_count INT         NOT NULL CHECK (allocated_count > 0),
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','released','cancelled'))
);

-- ============================================================
-- 16. delivery_notes
-- ============================================================
CREATE TABLE IF NOT EXISTS delivery_notes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    delivery_no     VARCHAR(50)  NOT NULL UNIQUE,
    confirmation_id UUID         NOT NULL REFERENCES order_confirmations(id) ON DELETE RESTRICT,
    customer_id     UUID         NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    delivery_date   DATE         NOT NULL,
    actual_quantity INT          NOT NULL CHECK (actual_quantity > 0),
    room_id         UUID         NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
    is_dispatched   BOOLEAN      NOT NULL DEFAULT FALSE,
    printed_at      TIMESTAMPTZ
);

-- ============================================================
-- Indexes for common query patterns
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_daily_inventory_date       ON daily_inventory(record_date);
CREATE INDEX IF NOT EXISTS idx_daily_inventory_strain     ON daily_inventory(strain_id);
CREATE INDEX IF NOT EXISTS idx_daily_inventory_room       ON daily_inventory(room_id);
CREATE INDEX IF NOT EXISTS idx_inquiries_customer         ON inquiries(customer_id);
CREATE INDEX IF NOT EXISTS idx_inquiries_stage            ON inquiries(stage);
CREATE INDEX IF NOT EXISTS idx_inquiries_stock_status     ON inquiries(stock_status);
CREATE INDEX IF NOT EXISTS idx_reservations_delivery_date ON reservations(delivery_date);
CREATE INDEX IF NOT EXISTS idx_order_confirmations_stage  ON order_confirmations(stage);
CREATE INDEX IF NOT EXISTS idx_inquiry_history_inquiry_id ON inquiry_history(inquiry_id);
