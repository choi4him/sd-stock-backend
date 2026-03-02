-- migrations/003_inquiry_customer_optional.sql
-- inquiries.customer_id를 nullable로 변경 (가평확인요청 시 거래처 없이도 가능)

ALTER TABLE inquiries
    ALTER COLUMN customer_id DROP NOT NULL;
