-- 샘플 데이터 삽입

USE llm_db_test;

-- 카테고리 데이터
INSERT INTO categories (category_name, parent_category_id, description) VALUES
('전자제품', NULL, '모든 전자제품'),
('의류', NULL, '의류 및 패션'),
('도서', NULL, '책 및 교육자료'),
('스마트폰', 1, '휴대폰 및 액세서리'),
('노트북', 1, '노트북 및 컴퓨터'),
('남성의류', 2, '남성용 의류'),
('여성의류', 2, '여성용 의류'),
('IT도서', 3, 'IT 관련 도서');

-- 사용자 데이터
INSERT INTO users (username, email, full_name, status) VALUES
('john_doe', 'john@example.com', '홍길동', 'active'),
('jane_smith', 'jane@example.com', '김영희', 'active'),
('bob_wilson', 'bob@example.com', '박철수', 'active'),
('alice_brown', 'alice@example.com', '이순신', 'inactive'),
('charlie_davis', 'charlie@example.com', '정약용', 'active');

-- 상품 데이터
INSERT INTO products (product_name, category_id, price, stock_quantity, description, status) VALUES
('아이폰 15 Pro', 4, 1200000.00, 50, '최신 아이폰 모델', 'active'),
('갤럭시 S24', 4, 1100000.00, 30, '삼성 최신 스마트폰', 'active'),
('맥북 프로 M3', 5, 2500000.00, 20, '애플 노트북', 'active'),
('델 XPS 13', 5, 1800000.00, 25, '델 프리미엄 노트북', 'active'),
('남성 정장', 6, 250000.00, 40, '고급 정장', 'active'),
('여성 원피스', 7, 120000.00, 60, '우아한 원피스', 'active'),
('클린 코드', 8, 35000.00, 100, '로버트 마틴의 클린 코드', 'active'),
('리팩터링', 8, 40000.00, 80, '마틴 파울러의 리팩터링', 'active');

-- 주문 데이터
INSERT INTO orders (user_id, total_amount, status, shipping_address) VALUES
(1, 1235000.00, 'delivered', '서울시 강남구 테헤란로 123'),
(2, 1140000.00, 'shipped', '부산시 해운대구 센텀로 456'),
(3, 370000.00, 'processing', '대구시 수성구 동대구로 789'),
(1, 2540000.00, 'pending', '서울시 강남구 테헤란로 123'),
(4, 75000.00, 'cancelled', '인천시 연수구 송도대로 321');

-- 주문 상세 데이터
INSERT INTO order_items (order_id, product_id, quantity, unit_price, subtotal) VALUES
(1, 1, 1, 1200000.00, 1200000.00),
(1, 7, 1, 35000.00, 35000.00),
(2, 2, 1, 1100000.00, 1100000.00),
(2, 8, 1, 40000.00, 40000.00),
(3, 5, 1, 250000.00, 250000.00),
(3, 6, 1, 120000.00, 120000.00),
(4, 3, 1, 2500000.00, 2500000.00),
(4, 8, 1, 40000.00, 40000.00),
(5, 7, 1, 35000.00, 35000.00),
(5, 8, 1, 40000.00, 40000.00);

-- 리뷰 데이터
INSERT INTO reviews (user_id, product_id, order_id, rating, review_text) VALUES
(1, 1, 1, 5, '정말 훌륭한 스마트폰입니다!'),
(1, 7, 1, 4, '개발자에게 필수 도서네요'),
(2, 2, 2, 4, '성능이 우수합니다'),
(2, 8, 2, 5, '리팩터링 기법을 잘 설명한 책'),
(3, 5, 3, 3, '가격 대비 괜찮습니다'),
(3, 6, 3, 5, '디자인이 아름답습니다'); 