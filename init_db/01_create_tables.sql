-- llm_db_test 데이터베이스용 테이블 생성 쿼리 (MariaDB)
-- 4개 이상의 테이블 조인 테스트를 위한 전자상거래 시스템

USE llm_db_test;

-- 1. 사용자 테이블
CREATE TABLE users (
    user_id INT PRIMARY KEY AUTO_INCREMENT COMMENT '사용자 고유 식별자',
    username VARCHAR(50) NOT NULL UNIQUE COMMENT '사용자명 (로그인 ID)',
    email VARCHAR(100) NOT NULL UNIQUE COMMENT '이메일 주소',
    full_name VARCHAR(100) NOT NULL COMMENT '사용자 실명',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '계정 생성일시',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '마지막 수정일시',
    status ENUM('active', 'inactive', 'suspended') DEFAULT 'active' COMMENT '계정 상태 (활성/비활성/정지)'
) COMMENT = '사용자 계정 정보를 저장하는 테이블';

-- 2. 카테고리 테이블
CREATE TABLE categories (
    category_id INT PRIMARY KEY AUTO_INCREMENT COMMENT '카테고리 고유 식별자',
    category_name VARCHAR(100) NOT NULL UNIQUE COMMENT '카테고리명',
    parent_category_id INT NULL COMMENT '상위 카테고리 ID (최상위는 NULL)',
    description TEXT COMMENT '카테고리 설명',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '카테고리 생성일시',
    FOREIGN KEY (parent_category_id) REFERENCES categories(category_id)
) COMMENT = '상품 카테고리 정보를 저장하는 테이블 (계층구조 지원)';

-- 3. 상품 테이블
CREATE TABLE products (
    product_id INT PRIMARY KEY AUTO_INCREMENT COMMENT '상품 고유 식별자',
    product_name VARCHAR(200) NOT NULL COMMENT '상품명',
    category_id INT NOT NULL COMMENT '소속 카테고리 ID',
    price DECIMAL(10, 2) NOT NULL COMMENT '상품 가격',
    stock_quantity INT NOT NULL DEFAULT 0 COMMENT '재고 수량',
    description TEXT COMMENT '상품 상세 설명',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '상품 등록일시',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '상품 정보 수정일시',
    status ENUM('active', 'inactive', 'discontinued') DEFAULT 'active' COMMENT '상품 판매 상태 (판매중/판매중지/단종)',
    FOREIGN KEY (category_id) REFERENCES categories(category_id)
) COMMENT = '판매 상품 정보를 저장하는 테이블';

-- 4. 주문 테이블
CREATE TABLE orders (
    order_id INT PRIMARY KEY AUTO_INCREMENT COMMENT '주문 고유 식별자',
    user_id INT NOT NULL COMMENT '주문한 사용자 ID',
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '주문 생성일시',
    total_amount DECIMAL(10, 2) NOT NULL COMMENT '주문 총 금액',
    status ENUM('pending', 'processing', 'shipped', 'delivered', 'cancelled') DEFAULT 'pending' COMMENT '주문 처리 상태',
    shipping_address TEXT NOT NULL COMMENT '배송 주소',
    FOREIGN KEY (user_id) REFERENCES users(user_id)
) COMMENT = '사용자 주문 정보를 저장하는 테이블';

-- 5. 주문 상세 테이블
CREATE TABLE order_items (
    order_item_id INT PRIMARY KEY AUTO_INCREMENT COMMENT '주문 상세 고유 식별자',
    order_id INT NOT NULL COMMENT '주문 ID',
    product_id INT NOT NULL COMMENT '주문된 상품 ID',
    quantity INT NOT NULL COMMENT '주문 수량',
    unit_price DECIMAL(10, 2) NOT NULL COMMENT '주문 당시 상품 단가',
    subtotal DECIMAL(10, 2) NOT NULL COMMENT '해당 상품의 주문 소계 (수량 × 단가)',
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
) COMMENT = '주문에 포함된 개별 상품 정보를 저장하는 테이블';

-- 6. 리뷰 테이블
CREATE TABLE reviews (
    review_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    product_id INT NOT NULL,
    order_id INT NOT NULL,
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    review_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
) COMMENT = '상품 리뷰 정보를 저장하는 테이블'; 