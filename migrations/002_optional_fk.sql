-- migrations/002_optional_fk.sql
-- inquiry_id (reservations), reservation_id (order_confirmations) NULL 허용 패치

-- 1. reservations.inquiry_id → nullable
ALTER TABLE reservations
    ALTER COLUMN inquiry_id DROP NOT NULL;

-- 2. order_confirmations.reservation_id → nullable
ALTER TABLE order_confirmations
    ALTER COLUMN reservation_id DROP NOT NULL;

-- 3. order_allocations: order_type enum에 'direct' 추가 (예약 없이 바로 확정 시)
--    (기존 'reservation' | 'confirmation' 유지)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'allocation_type')
          AND enumlabel = 'direct'
    ) THEN
        ALTER TYPE allocation_type ADD VALUE 'direct';
    END IF;
END$$;
