"""
Code LLM을 이용한 SELECT QUERY 생성 (Hybrid: OLLAMA + Claude API 지원)

LLM 모델 선택 방법:
1. OLLAMA 사용: __init__ 함수에서 self.llm_type = "ollama" (기본값)
2. Claude API 사용: __init__ 함수에서 주석을 해제하여 self.llm_type = "claude" 설정

Claude API 사용 시 필요사항:
- pip install anthropic
- 환경변수 설정: export ANTHROPIC_API_KEY='your-api-key'
"""
"""
DB ADDRESS
222.239.231.95 : 32000
db : llm_db_test
user : genai
password : Zx82qm730!
"""

"""
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
);

-- 샘플 데이터 삽입

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

-- 조인 테스트를 위한 예제 쿼리들

-- 4개 테이블 조인 예제 1: 사용자별 주문 상품 정보
/*
SELECT 
    u.username,
    u.full_name,
    o.order_id,
    p.product_name,
    oi.quantity,
    oi.unit_price
FROM users u
JOIN orders o ON u.user_id = o.user_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE u.status = 'active';
*/

-- 5개 테이블 조인 예제: 카테고리별 주문 통계
/*
SELECT 
    c.category_name,
    u.username,
    COUNT(oi.order_item_id) as total_items_ordered,
    SUM(oi.subtotal) as total_amount
FROM categories c
JOIN products p ON c.category_id = p.category_id
JOIN order_items oi ON p.product_id = oi.product_id
JOIN orders o ON oi.order_id = o.order_id
JOIN users u ON o.user_id = u.user_id
GROUP BY c.category_id, u.user_id;
*/

-- 6개 테이블 조인 예제: 리뷰가 있는 주문 정보
/*
SELECT 
    u.username,
    o.order_id,
    p.product_name,
    c.category_name,
    oi.quantity,
    r.rating,
    r.review_text
FROM users u
JOIN orders o ON u.user_id = o.user_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN categories c ON p.category_id = c.category_id
JOIN reviews r ON (u.user_id = r.user_id AND p.product_id = r.product_id AND o.order_id = r.order_id)
ORDER BY r.rating DESC;
*/
"""

import pymysql
import requests
import json
import sys
import re
import os
from typing import List, Dict, Any, Optional, Tuple
from neo4j import GraphDatabase
from dataclasses import dataclass

# Claude API 사용을 위한 import (설치 필요: pip install anthropic)
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

@dataclass
class TableRelation:
    """테이블 간 관계 정보"""
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    relation_type: str  # 'foreign_key', 'semantic', 'naming_pattern'
    confidence: float   # 관계의 확신도 (0.0 ~ 1.0)

@dataclass
class TableSchema:
    """테이블 스키마 정보"""
    table_name: str
    columns: List[Dict[str, Any]]
    primary_keys: List[str]
    foreign_keys: List[Dict[str, str]]
    comment: str

class HybridQueryGenerator:
    def __init__(self):
        # MariaDB 연결 정보 (Docker 컨테이너 사용시)
        self.db_config = {
            'host': 'localhost',  # Docker: localhost, 외부서버: 222.239.231.95
            'port': 32000,
            'user': 'genai',
            'password': 'genai1234',
            'database': 'llm_db_test',
            'charset': 'utf8mb4'
        }
        
        # Neo4j 연결 정보
        self.neo4j_config = {
            'uri': 'bolt://localhost:7687',
            'username': 'neo4j',
            'password': 'password123'
        }
        
        # LLM 모델 설정 - 원하는 모델의 주석을 해제하세요
        # =================================================================
        
        on_local = True
        if on_local:
            self.llm_type = "ollama"
            self.ollama_url = "http://localhost:11434"
            self.model_name = "codellama:7b"  # 4GB 메모리에 적합하고 한글 지원 우수 (빠름)
        else:
            self.llm_type = "claude"
            self.claude_model = "claude-3-5-sonnet-20241022"  # 최신 Claude 모델
            self.claude_api_key = os.getenv('ANTHROPIC_API_KEY', "")  # 환경변수에서 API 키 읽기

        
        self.connection = None
        self.neo4j_driver = None
        self.tables_info = {}
        self.table_schemas = {}
        self.table_relations = []
        
        # Claude 클라이언트 초기화
        if self.llm_type == "claude":
            if not ANTHROPIC_AVAILABLE:
                print("❌ anthropic 라이브러리가 설치되지 않았습니다.")
                print("💡 설치 명령: pip install anthropic")
                self.llm_type = "ollama"  # 폴백
            elif not hasattr(self, 'claude_api_key') or not self.claude_api_key:
                print("⚠️  ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
                print("💡 다음 중 하나를 선택하세요:")
                print("   1. 환경변수 설정: export ANTHROPIC_API_KEY='your-key'")
                print("   2. 코드에서 직접 설정: self.claude_api_key = 'your-key'")
                print("   3. OLLAMA 모델 사용으로 변경")
                self.llm_type = "ollama"  # 폴백
            else:
                try:
                    self.claude_client = anthropic.Anthropic(api_key=self.claude_api_key)
                    print(f"✅ Claude API 클라이언트 초기화 완료: {self.claude_model}")
                except Exception as e:
                    print(f"❌ Claude API 클라이언트 초기화 실패: {e}")
                    self.llm_type = "ollama"  # 폴백
    
    def connect_to_database(self) -> bool:
        """MariaDB에 연결"""
        try:
            self.connection = pymysql.connect(**self.db_config)
            print("✅ MariaDB 연결 성공!")
            return True
        except Exception as e:
            print(f"❌ MariaDB 연결 실패: {e}")
            return False
    
    def disconnect_from_database(self):
        """데이터베이스 연결 종료"""
        if self.connection:
            self.connection.close()
            print("🔌 MariaDB 연결 종료")
        
        if self.neo4j_driver:
            self.neo4j_driver.close()
            print("🔌 Neo4j 연결 종료")
    
    def connect_to_neo4j(self) -> bool:
        """Neo4j에 연결"""
        try:
            self.neo4j_driver = GraphDatabase.driver(
                self.neo4j_config['uri'],
                auth=(self.neo4j_config['username'], self.neo4j_config['password'])
            )
            # 연결 테스트
            with self.neo4j_driver.session() as session:
                result = session.run("RETURN 1 as test")
                result.single()
            print("✅ Neo4j 연결 성공!")
            return True
        except Exception as e:
            print(f"❌ Neo4j 연결 실패: {e}")
            print("💡 Neo4j가 실행 중인지 확인하세요: docker-compose up -d neo4j")
            return False
    
    def check_ollama_connection(self) -> bool:
        """OLLAMA 서버 연결 확인"""
        if self.llm_type != "ollama":
            return True  # OLLAMA 사용하지 않는 경우 스킵
            
        try:
            response = requests.get(f"{self.ollama_url}/api/tags")
            if response.status_code == 200:
                print("✅ OLLAMA 서버 연결 성공!")
                return True
            else:
                print("❌ OLLAMA 서버 응답 오류")
                return False
        except Exception as e:
            print(f"❌ OLLAMA 서버 연결 실패: {e}")
            print("💡 OLLAMA가 실행 중인지 확인하세요: ollama serve")
            return False
    
    def check_model_availability(self) -> bool:
        """모델 사용 가능성 확인"""
        if self.llm_type == "claude":
            # Claude API의 경우 API 키만 확인
            return hasattr(self, 'claude_client')
        
        # OLLAMA 모델 확인
        try:
            response = requests.get(f"{self.ollama_url}/api/tags")
            if response.status_code == 200:
                models = response.json().get('models', [])
                available_models = [model['name'] for model in models]
                
                if self.model_name in available_models:
                    print(f"✅ 모델 '{self.model_name}' 사용 가능!")
                    return True
                else:
                    print(f"❌ 모델 '{self.model_name}'이 설치되지 않았습니다.")
                    print("📋 사용 가능한 모델들:")
                    for model in available_models:
                        print(f"  - {model}")
                    
                    # 4GB 메모리에 적합한 다른 모델 추천 (한글 지원 순서)
                    recommended_models = [
                        ("deepseek-coder:1.3b", "한글 지원 우수, 메모리 절약"),
                        ("deepseek-coder:6.7b", "한글 지원 우수, 성능 최고"),
                        ("codellama:7b-code", "다국어 지원, 메모리 많이 사용"),
                        ("starcoder:3b", "영어 특화, 한글 제한적"),
                        ("sqlcoder:7b", "SQL 특화, 영어 위주")
                    ]
                    
                    print("\n💡 4GB 메모리에 추천되는 모델들 (한글 지원 순서):")
                    for model, desc in recommended_models:
                        print(f"  ollama pull {model}  # {desc}")
                    
                    return False
            return False
        except Exception as e:
            print(f"❌ 모델 확인 실패: {e}")
            return False
    
    def call_claude_api(self, prompt: str) -> Optional[str]:
        """Claude API 호출"""
        try:
            print(f"🤖 Claude API 호출: {self.claude_model}")
            
            message = self.claude_client.messages.create(
                model=self.claude_model,
                max_tokens=1000,
                temperature=0.1,  # 정확한 SQL 생성을 위해 낮은 온도
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            return message.content[0].text.strip()
            
        except Exception as e:
            print(f"❌ Claude API 호출 실패: {e}")
            return None
    
    def call_ollama_api(self, prompt: str) -> Optional[str]:
        """OLLAMA API 호출"""
        try:
            print(f"🤖 OLLAMA 호출: {self.model_name}")
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # 정확한 SQL 생성을 위해 낮은 온도
                    "top_p": 0.9,
                    "num_predict": 500
                }
            }
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=120  # 타임아웃을 120초로 증가 (큰 모델용)
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '').strip()
            else:
                print(f"❌ OLLAMA 호출 실패: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ OLLAMA 호출 중 오류: {e}")
            return None
    
    def call_llm(self, prompt: str) -> Optional[str]:
        """LLM 호출 - 설정된 모델 타입에 따라 분기"""
        if self.llm_type == "claude":
            return self.call_claude_api(prompt)
        elif self.llm_type == "ollama":
            return self.call_ollama_api(prompt)
        else:
            print(f"❌ 지원하지 않는 LLM 타입: {self.llm_type}")
            return None
    
    def get_all_tables(self) -> List[str]:
        """데이터베이스의 모든 테이블 조회"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                tables = [table[0] for table in cursor.fetchall()]
                print(f"📊 발견된 테이블: {len(tables)}개")
                for table in tables:
                    print(f"  - {table}")
                return tables
        except Exception as e:
            print(f"❌ 테이블 조회 실패: {e}")
            return []
    
    def get_table_structure(self, table_name: str) -> Dict[str, Any]:
        """특정 테이블의 구조 정보 조회"""
        try:
            with self.connection.cursor() as cursor:
                # 테이블 구조 조회
                cursor.execute(f"DESCRIBE {table_name}")
                columns = cursor.fetchall()
                
                # 샘플 데이터 조회 (최대 3개)
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
                sample_data = cursor.fetchall()
                
                structure = {
                    'columns': columns,
                    'sample_data': sample_data
                }
                
                return structure
        except Exception as e:
            print(f"❌ 테이블 '{table_name}' 구조 조회 실패: {e}")
            return {}
    
    def analyze_all_tables(self) -> Dict[str, Dict]:
        """모든 테이블 분석"""
        tables = self.get_all_tables()
        
        print("\n🔍 테이블 구조 분석 중...")
        for table in tables:
            print(f"\n📋 테이블: {table}")
            structure = self.get_table_structure(table)
            
            if structure:
                self.tables_info[table] = structure
                
                print("  컬럼 정보:")
                for col in structure['columns']:
                    print(f"    - {col[0]} ({col[1]})")
                
                if structure['sample_data']:
                    print("  샘플 데이터:")
                    for i, row in enumerate(structure['sample_data'], 1):
                        print(f"    {i}: {row}")
        
        return self.tables_info
    
    def extract_schema_from_ddl(self) -> Dict[str, TableSchema]:
        """DDL 주석에서 스키마 정보 추출"""
        # 파일의 DDL 주석에서 스키마 정보 추출
        ddl_content = '''
        -- 1. 사용자 테이블
        CREATE TABLE users (
            user_id INT PRIMARY KEY AUTO_INCREMENT COMMENT '사용자 고유 식별자',
            username VARCHAR(50) NOT NULL UNIQUE COMMENT '사용자명 (로그인 ID)',
            email VARCHAR(100) NOT NULL UNIQUE COMMENT '이메일 주소',
            full_name VARCHAR(100) NOT NULL COMMENT '사용자 실명',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '계정 생성일시',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '마지막 수정일시',
            status ENUM('active', 'inactive', 'suspended') DEFAULT 'active' COMMENT '계정 상태'
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
            status ENUM('active', 'inactive', 'discontinued') DEFAULT 'active' COMMENT '상품 판매 상태',
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
            subtotal DECIMAL(10, 2) NOT NULL COMMENT '해당 상품의 주문 소계',
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
        );
        '''
        
        schemas = {}
        
        # 간단한 DDL 파싱 (실제 프로덕션에서는 더 정교한 파서 필요)
        table_patterns = re.findall(
            r'CREATE TABLE (\w+) \((.*?)\) COMMENT = \'(.*?)\';',
            ddl_content,
            re.DOTALL | re.IGNORECASE
        )
        
        for table_name, columns_str, comment in table_patterns:
            # 컬럼 정보 추출
            columns = []
            primary_keys = []
            foreign_keys = []
            
            lines = columns_str.strip().split('\n')
            for line in lines:
                line = line.strip().strip(',')
                
                if 'PRIMARY KEY' in line and not line.startswith('FOREIGN KEY'):
                    # PRIMARY KEY 추출
                    if 'AUTO_INCREMENT' in line:
                        col_name = line.split()[0]
                        primary_keys.append(col_name)
                        columns.append({
                            'name': col_name,
                            'type': 'INT',
                            'nullable': False,
                            'auto_increment': True
                        })
                elif line.startswith('FOREIGN KEY'):
                    # FOREIGN KEY 추출
                    fk_match = re.search(r'FOREIGN KEY \((\w+)\) REFERENCES (\w+)\((\w+)\)', line)
                    if fk_match:
                        from_col, to_table, to_col = fk_match.groups()
                        foreign_keys.append({
                            'from_column': from_col,
                            'to_table': to_table,
                            'to_column': to_col
                        })
                elif line and not line.startswith('FOREIGN KEY') and not line.startswith('CONSTRAINT'):
                    # 일반 컬럼
                    parts = line.split()
                    if len(parts) >= 2:
                        col_name = parts[0]
                        col_type = parts[1]
                        nullable = 'NOT NULL' not in line
                        
                        if col_name not in [pk for pk in primary_keys]:
                            columns.append({
                                'name': col_name,
                                'type': col_type,
                                'nullable': nullable,
                                'auto_increment': False
                            })
            
            schemas[table_name] = TableSchema(
                table_name=table_name,
                columns=columns,
                primary_keys=primary_keys,
                foreign_keys=foreign_keys,
                comment=comment
            )
        
        self.table_schemas = schemas
        print(f"📊 스키마 분석 완료: {len(schemas)}개 테이블")
        return schemas
    
    def extract_table_relations(self) -> List[TableRelation]:
        """테이블 간 관계 추출"""
        relations = []
        
        # 1. Foreign Key 관계 추출
        for table_name, schema in self.table_schemas.items():
            for fk in schema.foreign_keys:
                relations.append(TableRelation(
                    from_table=table_name,
                    from_column=fk['from_column'],
                    to_table=fk['to_table'],
                    to_column=fk['to_column'],
                    relation_type='foreign_key',
                    confidence=1.0
                ))
        
        # 2. 의미적 관계 추출 (컬럼명 기반)
        for table1_name, schema1 in self.table_schemas.items():
            for table2_name, schema2 in self.table_schemas.items():
                if table1_name != table2_name:
                    for col1 in schema1.columns:
                        for col2 in schema2.columns:
                            # ID 컬럼 매칭 (예: user_id → user_id)
                            if (col1['name'] == col2['name'] and 
                                'id' in col1['name'].lower() and 
                                col1['name'] not in [fk['from_column'] for fk in schema1.foreign_keys]):
                                
                                # 이미 FK 관계가 있는지 확인
                                existing = any(
                                    r.from_table == table1_name and 
                                    r.from_column == col1['name'] and
                                    r.to_table == table2_name and
                                    r.to_column == col2['name']
                                    for r in relations
                                )
                                
                                if not existing:
                                    relations.append(TableRelation(
                                        from_table=table1_name,
                                        from_column=col1['name'],
                                        to_table=table2_name,
                                        to_column=col2['name'],
                                        relation_type='semantic',
                                        confidence=0.8
                                    ))
        
        # 3. 네이밍 패턴 기반 관계 (예: user_id → users.user_id)
        for table1_name, schema1 in self.table_schemas.items():
            for col in schema1.columns:
                if col['name'].endswith('_id') and col['name'] != f"{table1_name}_id":
                    # 테이블명 추정
                    potential_table = col['name'][:-3]  # _id 제거
                    potential_table_plural = potential_table + 's'
                    
                    for table2_name, schema2 in self.table_schemas.items():
                        if table2_name in [potential_table, potential_table_plural]:
                            primary_key = next((pk for pk in schema2.primary_keys), None)
                            if primary_key == col['name']:
                                # 이미 관계가 있는지 확인
                                existing = any(
                                    r.from_table == table1_name and 
                                    r.from_column == col['name'] and
                                    r.to_table == table2_name
                                    for r in relations
                                )
                                
                                if not existing:
                                    relations.append(TableRelation(
                                        from_table=table1_name,
                                        from_column=col['name'],
                                        to_table=table2_name,
                                        to_column=primary_key,
                                        relation_type='naming_pattern',
                                        confidence=0.7
                                    ))
        
        self.table_relations = relations
        print(f"🔗 관계 추출 완료: {len(relations)}개 관계")
        
        for rel in relations:
            print(f"  {rel.from_table}.{rel.from_column} → {rel.to_table}.{rel.to_column} ({rel.relation_type}, {rel.confidence})")
        
        return relations
    
    def create_schema_graph_in_neo4j(self):
        """Neo4j에 스키마 그래프 생성"""
        if not self.neo4j_driver:
            print("❌ Neo4j 연결이 필요합니다.")
            return
        
        print("🔄 Neo4j에 스키마 그래프 생성 중...")
        
        with self.neo4j_driver.session() as session:
            # 기존 스키마 그래프 삭제
            session.run("MATCH (n:Table)-[r]-(m) DELETE r")
            session.run("MATCH (n:Table) DELETE n")
            session.run("MATCH (n:Column) DELETE n")
            
            # 테이블 노드 생성
            for table_name, schema in self.table_schemas.items():
                session.run("""
                    CREATE (t:Table {
                        name: $table_name,
                        comment: $comment,
                        primary_keys: $primary_keys,
                        table_type: 'main'
                    })
                """, table_name=table_name, comment=schema.comment, 
                primary_keys=schema.primary_keys)
                
                # 컬럼 노드 생성 및 테이블과 연결
                for col in schema.columns:
                    session.run("""
                        MATCH (t:Table {name: $table_name})
                        CREATE (c:Column {
                            name: $col_name,
                            type: $col_type,
                            nullable: $nullable,
                            auto_increment: $auto_increment
                        })
                        CREATE (t)-[:HAS_COLUMN]->(c)
                    """, table_name=table_name, col_name=col['name'], 
                    col_type=col['type'], nullable=col['nullable'],
                    auto_increment=col.get('auto_increment', False))
            
            # 관계 생성
            for rel in self.table_relations:
                session.run("""
                    MATCH (from_table:Table {name: $from_table})
                    MATCH (to_table:Table {name: $to_table})
                    CREATE (from_table)-[:REFERENCES {
                        from_column: $from_column,
                        to_column: $to_column,
                        relation_type: $relation_type,
                        confidence: $confidence
                    }]->(to_table)
                """, from_table=rel.from_table, to_table=rel.to_table,
                from_column=rel.from_column, to_column=rel.to_column,
                relation_type=rel.relation_type, confidence=rel.confidence)
        
        print("✅ Neo4j 스키마 그래프 생성 완료!")
    
    def query_relationship_paths(self, start_table: str, end_table: str = None, max_depth: int = 3) -> List[Dict]:
        """Neo4j에서 테이블 간 관계 경로 조회"""
        if not self.neo4j_driver:
            print("❌ Neo4j 연결이 필요합니다.")
            return []
        
        with self.neo4j_driver.session() as session:
            if end_table:
                # 특정 테이블 간 경로 찾기
                query = """
                MATCH path = (start:Table {name: $start_table})-[:REFERENCES*1..{max_depth}]-(end:Table {name: $end_table})
                RETURN path, length(path) as path_length
                ORDER BY path_length
                LIMIT 10
                """.format(max_depth=max_depth)
                
                result = session.run(query, start_table=start_table, end_table=end_table)
            else:
                # 시작 테이블에서 접근 가능한 모든 테이블
                query = """
                MATCH path = (start:Table {name: $start_table})-[:REFERENCES*1..{max_depth}]-(other:Table)
                WHERE start <> other
                RETURN path, other.name as connected_table, length(path) as path_length
                ORDER BY path_length, other.name
                """.format(max_depth=max_depth)
                
                result = session.run(query, start_table=start_table)
            
            paths = []
            for record in result:
                path_info = {
                    'path': record['path'],
                    'length': record['path_length']
                }
                if end_table:
                    path_info['target'] = end_table
                else:
                    path_info['target'] = record['connected_table']
                
                paths.append(path_info)
            
            return paths
    
    def find_optimal_join_sequence(self, required_tables: List[str]) -> List[Dict]:
        """필요한 테이블들을 조인하는 최적 순서 찾기"""
        if not self.neo4j_driver or len(required_tables) < 2:
            return []
        
        print(f"🔍 테이블 조인 순서 분석: {required_tables}")
        
        with self.neo4j_driver.session() as session:
            # 모든 테이블 쌍에 대한 최단 경로 찾기
            join_sequences = []
            
            query = """
            MATCH (t1:Table), (t2:Table)
            WHERE t1.name IN $tables AND t2.name IN $tables AND t1 <> t2
            MATCH path = shortestPath((t1)-[:REFERENCES*1..3]-(t2))
            RETURN t1.name as table1, t2.name as table2, path, length(path) as distance
            ORDER BY distance
            """
            
            result = session.run(query, tables=required_tables)
            
            connections = {}
            for record in result:
                table1 = record['table1']
                table2 = record['table2']
                distance = record['distance']
                path = record['path']
                
                # 경로에서 관계 정보 추출
                relationships = []
                for i in range(len(path.relationships)):
                    rel = path.relationships[i]
                    relationships.append({
                        'from_table': path.nodes[i]['name'],
                        'to_table': path.nodes[i+1]['name'],
                        'from_column': rel['from_column'],
                        'to_column': rel['to_column'],
                        'confidence': rel['confidence']
                    })
                
                key = tuple(sorted([table1, table2]))
                if key not in connections or distance < connections[key]['distance']:
                    connections[key] = {
                        'distance': distance,
                        'relationships': relationships
                    }
            
            # 최적 조인 순서 생성
            if connections:
                # 가장 연결이 밀집된 테이블부터 시작
                start_table = max(required_tables, key=lambda t: 
                    sum(1 for k in connections.keys() if t in k))
                
                remaining_tables = set(required_tables) - {start_table}
                join_sequence = [{'table': start_table, 'joins': []}]
                
                while remaining_tables:
                    # 현재 연결된 테이블들과 가장 가까운 다음 테이블 찾기
                    connected_tables = {start_table} | {j['to_table'] for seq in join_sequence for j in seq['joins']}
                    
                    best_next = None
                    best_distance = float('inf')
                    best_join_info = None
                    
                    for remaining in remaining_tables:
                        for connected in connected_tables:
                            key = tuple(sorted([connected, remaining]))
                            if key in connections and connections[key]['distance'] < best_distance:
                                best_distance = connections[key]['distance']
                                best_next = remaining
                                best_join_info = connections[key]['relationships']
                    
                    if best_next:
                        join_sequence.append({
                            'table': best_next,
                            'joins': best_join_info
                        })
                        remaining_tables.remove(best_next)
                    else:
                        # 연결할 수 없는 테이블들 (강제로 추가)
                        for remaining in remaining_tables:
                            join_sequence.append({
                                'table': remaining,
                                'joins': []
                            })
                        break
                
                return join_sequence
            
            return []
    
    def generate_schema_prompt(self) -> str:
        """테이블 스키마 정보를 LLM 프롬프트용으로 변환"""
        prompt = "다음은 데이터베이스의 테이블 스키마 정보입니다:\n\n"
        
        for table_name, info in self.tables_info.items():
            prompt += f"테이블: {table_name}\n"
            prompt += "컬럼:\n"
            
            for col in info['columns']:
                col_name, col_type = col[0], col[1]
                prompt += f"  - {col_name}: {col_type}\n"
            
            if info['sample_data']:
                prompt += "샘플 데이터:\n"
                for i, row in enumerate(info['sample_data'][:2], 1):
                    prompt += f"  {i}: {row}\n"
            
            prompt += "\n"
        
        return prompt
    
    def generate_hybrid_sql_query(self, user_request: str) -> Optional[str]:
        """Neo4j 그래프 정보를 활용한 하이브리드 SQL 쿼리 생성"""
        # 1. 사용자 요청에서 관련 테이블 추출
        relevant_tables = self.extract_relevant_tables(user_request)
        
        if not relevant_tables:
            print("❌ 관련 테이블을 찾을 수 없습니다.")
            return None
        
        print(f"📊 관련 테이블: {relevant_tables}")
        
        # 2. Neo4j에서 최적 조인 순서 찾기
        join_sequence = self.find_optimal_join_sequence(relevant_tables)
        
        # 3. 그래프 정보와 스키마를 활용한 프롬프트 생성
        enhanced_prompt = self.generate_enhanced_prompt(user_request, relevant_tables, join_sequence)
        
        # 4. LLM으로 쿼리 생성
        print("🤖 Neo4j 그래프 정보를 활용하여 SQL 쿼리 생성 중...")
        response = self.call_llm(enhanced_prompt)
        
        if response:
            # SQL 쿼리 추출
            lines = response.split('\n')
            sql_lines = []
            in_sql = False
            
            for line in lines:
                line = line.strip()
                if line.upper().startswith('SELECT'):
                    in_sql = True
                if in_sql:
                    sql_lines.append(line)
                    if line.endswith(';'):
                        break
            
            if sql_lines:
                sql_query = ' '.join(sql_lines)
                if not sql_query.endswith(';'):
                    sql_query += ';'
                return sql_query
        
        return None
    
    def extract_relevant_tables_with_llm(self, user_request: str) -> List[str]:
        """LLM을 활용한 지능적 테이블 추출"""
        # 스키마 정보를 간결하게 정리
        table_descriptions = {}
        for table_name, schema in self.table_schemas.items():
            table_descriptions[table_name] = {
                'description': schema.comment,
                'key_columns': [col['name'] for col in schema.columns]  # 주요 컬럼 4개만
            }
        
        # LLM용 프롬프트 생성
        schema_summary = "데이터베이스 테이블 정보:\n"
        for table, info in table_descriptions.items():
            schema_summary += f"- {table}: {info['description']}\n"
            schema_summary += f"  주요 컬럼: {', '.join(info['key_columns'])}\n"
        
        # LLM 타입과 모델별 최적화된 프롬프트
        if self.llm_type == "claude":
            # Claude는 한글을 매우 잘 지원하므로 상세한 한글 프롬프트 사용
            prompt = f"""{schema_summary}

사용자 요청: {user_request}

위의 데이터베이스 스키마를 분석하여 사용자 요청을 처리하는데 필요한 테이블들을 선택해주세요.

분석 기준:
1. 사용자가 조회하려는 주요 데이터는 무엇인가?
2. 그 데이터를 얻기 위해 어떤 테이블들이 필요한가?
3. 테이블 간 관계를 고려하여 연결에 필요한 중간 테이블도 포함해야 하는가?

응답은 반드시 다음 JSON 형식으로만 반환해주세요:
{{"tables": ["table1", "table2", "table3"], "reason": "선택 이유를 한 문장으로"}}"""
        elif "gemma" in self.model_name.lower():
            # Gemma 모델용 특별 프롬프트
            prompt = f"""{schema_summary}

사용자 요청: {user_request}

위의 데이터베이스 스키마를 분석하여 사용자 요청을 처리하는데 필요한 테이블들을 선택해주세요.

**분석 기준**:
1. 사용자가 조회하려는 주요 데이터는 무엇인가?
2. 그 데이터를 얻기 위해 어떤 테이블들이 필요한가?
3. 테이블 간 관계를 고려하여 연결에 필요한 중간 테이블도 포함해야 하는가?

**응답 형식** (JSON만 반환):
{{"tables": ["table1", "table2", "table3"], "reason": "선택 이유를 한 문장으로"}}

JSON:"""
        else:
            # 기본 모델용 프롬프트
            prompt = f"""{schema_summary}

사용자 요청: {user_request}

위의 테이블 스키마를 참고하여 사용자 요청을 처리하는데 필요한 테이블들을 JSON 형태로 반환해주세요.

응답 형식:
{{"tables": ["테이블명1", "테이블명2"], "reason": "선택 이유"}}

JSON:"""
        
        print("🧠 LLM이 관련 테이블을 분석 중...")
        response = self.call_llm(prompt)
        
        if response:
            try:
                # JSON 추출
                response = response.strip()
                
                # JSON 블록 찾기
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    result = json.loads(json_str)
                    
                    if 'tables' in result and isinstance(result['tables'], list):
                        # 유효한 테이블만 필터링
                        valid_tables = [
                            table for table in result['tables'] 
                            if table in self.table_schemas
                        ]
                        
                        if valid_tables:
                            print(f"🎯 LLM 분석 결과: {valid_tables}")
                            if 'reason' in result:
                                print(f"📝 선택 이유: {result['reason']}")
                            return valid_tables
                        
            except (json.JSONDecodeError, KeyError) as e:
                print(f"⚠️  LLM 응답 파싱 실패: {e}")
                print(f"📄 원본 응답: {response[:200]}...")
        
        # LLM 분석 실패시 키워드 기반 방식으로 폴백
        print("🔄 키워드 기반 방식으로 폴백...")
        return self.extract_relevant_tables_fallback(user_request)
    
    def extract_relevant_tables_fallback(self, user_request: str) -> List[str]:
        """키워드 기반 폴백 방식"""
        request_lower = user_request.lower()
        relevant_tables = []
        
        # 키워드 기반 테이블 매칭
        table_keywords = {
            'users': ['사용자', '유저', '고객', '회원', '사람'],
            'products': ['상품', '제품', '아이템', '물건'],
            'orders': ['주문', '구매', '결제'],
            'order_items': ['주문상세', '주문내역', '구매내역'],
            'categories': ['카테고리', '분류', '종류'],
            'reviews': ['리뷰', '평점', '평가', '후기']
        }
        
        for table, keywords in table_keywords.items():
            if any(keyword in request_lower for keyword in keywords):
                relevant_tables.append(table)
        
        # 기본적으로 관련성이 높은 테이블들 추가
        if not relevant_tables:
            relevant_tables = ['users', 'products', 'orders']
        
        return relevant_tables
    
    def extract_relevant_tables(self, user_request: str) -> List[str]:
        """사용자 요청에서 관련 테이블 추출 (LLM 우선, 키워드 폴백)"""
        # LLM 기반 추출 시도
        return self.extract_relevant_tables_with_llm(user_request)
    
    def generate_enhanced_prompt(self, user_request: str, relevant_tables: List[str], join_sequence: List[Dict]) -> str:
        """Neo4j 정보를 활용한 향상된 프롬프트 생성"""
        schema_info = self.generate_schema_prompt()
        
        # 조인 정보 생성
        join_info = "최적 조인 순서 및 관계:\n"
        for i, seq in enumerate(join_sequence):
            table = seq['table']
            joins = seq['joins']
            
            join_info += f"{i+1}. {table}\n"
            for join in joins:
                join_info += f"   └─ {join['from_table']}.{join['from_column']} = {join['to_table']}.{join['to_column']} (신뢰도: {join['confidence']})\n"
        
        # 관련 테이블의 상세 정보
        table_details = "\n관련 테이블 상세 정보:\n"
        for table in relevant_tables:
            if table in self.table_schemas:
                schema = self.table_schemas[table]
                table_details += f"\n{table} 테이블:\n"
                table_details += f"  설명: {schema.comment}\n"
                table_details += f"  주요 컬럼: {', '.join([col['name'] for col in schema.columns[:5]])}\n"
        
        # LLM 타입과 모델에 따른 프롬프트 선택
        if self.llm_type == "claude":
            # Claude는 한글을 매우 잘 지원하므로 한글 프롬프트 사용
            prompt = f"""{schema_info}

{join_info}

{table_details}

사용자 요청: {user_request}

위의 스키마와 Neo4j 그래프 분석을 통한 최적 조인 관계를 바탕으로 정확한 SELECT SQL 쿼리를 생성해주세요.
제공된 조인 순서를 따라 최적의 성능을 보장하세요.

규칙:
1. 유효한 SQL 문법 사용 (MariaDB 기준)
2. 권장된 조인 순서 따르기
3. 적절한 WHERE 조건 포함
4. 테이블명과 컬럼명이 정확한지 확인
5. SQL 쿼리만 반환하고 추가 설명 없이

SQL 쿼리:"""
        elif "starcoder" in self.model_name.lower():
            # StarCoder는 영어 위주로 학습되어 영어 프롬프트 사용
            prompt = f"""{schema_info}

{join_info}

{table_details}

User Request: {user_request}

Based on the schema above and the optimal join relationships from Neo4j graph analysis, generate an accurate SELECT SQL query.
Use the join sequence provided to ensure optimal performance.

Rules:
1. Use valid SQL syntax (MariaDB)
2. Follow the recommended join order
3. Include appropriate WHERE conditions
4. Return only the SQL query

SQL Query:"""
        else:
            # 기타 모델들은 한글 프롬프트 사용 (대부분 한글 지원)
            prompt = f"""{schema_info}

{join_info}

{table_details}

사용자 요청: {user_request}

위의 스키마와 Neo4j 그래프 분석을 통한 최적 조인 관계를 바탕으로 정확한 SELECT SQL 쿼리를 생성해주세요.
제공된 조인 순서를 따라 최적의 성능을 보장하세요.

규칙:
1. 유효한 SQL 문법 사용
2. 권장된 조인 순서 따르기
3. 적절한 WHERE 조건 포함
4. SQL 쿼리만 반환

SQL 쿼리:"""
        
        return prompt
    
    def generate_sql_query(self, user_request: str) -> Optional[str]:
        """사용자 요청에 따른 SQL 쿼리 생성"""
        schema_info = self.generate_schema_prompt()
        
        # LLM 타입과 모델에 따른 프롬프트 선택
        if self.llm_type == "claude":
            # Claude는 한글을 매우 잘 지원하므로 한글 프롬프트 사용
            prompt = f"""{schema_info}

사용자 요청: {user_request}

위의 테이블 스키마를 참고하여 사용자 요청에 맞는 정확한 SELECT SQL 쿼리를 생성해주세요.

규칙:
1. 반드시 유효한 SQL 문법을 사용하세요 (MariaDB 기준)
2. 테이블명과 컬럼명이 정확한지 확인하세요
3. WHERE 조건이 필요한 경우 적절히 추가하세요
4. 결과는 SQL 쿼리만 반환하고 부가 설명은 제외하세요
5. 쿼리는 SELECT로 시작해야 합니다

SQL 쿼리:"""
        elif "starcoder" in self.model_name.lower():
            # StarCoder는 영어 위주로 학습되어 영어 프롬프트 사용
            prompt = f"""{schema_info}

User Request: {user_request}

Based on the table schema above, generate an accurate SELECT SQL query that meets the user's request.
Please follow these rules:
1. Use valid SQL syntax (MariaDB)
2. Ensure table and column names are correct
3. Add WHERE conditions if needed
4. Return only the SQL query without additional explanations
5. The query must start with SELECT

SQL Query:"""
        else:
            # 기타 모델들은 한글 프롬프트 사용 (대부분 한글 지원)
            prompt = f"""{schema_info}

사용자 요청: {user_request}

위의 테이블 스키마를 참고하여 사용자 요청에 맞는 정확한 SELECT SQL 쿼리를 생성해주세요.
다음 규칙을 따라주세요:
1. 반드시 유효한 SQL 문법을 사용하세요
2. 테이블명과 컬럼명이 정확한지 확인하세요
3. WHERE 조건이 필요한 경우 적절히 추가하세요
4. 결과는 SQL 쿼리만 반환하고 부가 설명은 제외하세요
5. 쿼리는 SELECT로 시작해야 합니다

SQL 쿼리:"""

        print("🤖 LLM이 SQL 쿼리를 생성 중...")
        response = self.call_llm(prompt)
        
        if response:
            # SQL 쿼리 추출 (코드 블록 제거 등)
            lines = response.split('\n')
            sql_lines = []
            in_sql = False
            
            for line in lines:
                line = line.strip()
                if line.upper().startswith('SELECT'):
                    in_sql = True
                if in_sql:
                    sql_lines.append(line)
                    if line.endswith(';'):
                        break
            
            if sql_lines:
                sql_query = ' '.join(sql_lines)
                # 세미콜론 추가
                if not sql_query.endswith(';'):
                    sql_query += ';'
                return sql_query
        
        return None
    
    def execute_query(self, query: str) -> Optional[List[tuple]]:
        """생성된 SQL 쿼리 실행"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
                return results
        except Exception as e:
            print(f"❌ 쿼리 실행 실패: {e}")
            return None
    
    def run_interactive_mode(self):
        """대화형 모드 실행"""
        print("=" * 70)
        print("🚀 하이브리드 SQL 쿼리 생성기 시작 (MariaDB + Neo4j)")
        print(f"🤖 사용 중인 LLM: {self.llm_type.upper()}")
        if self.llm_type == "claude":
            print(f"📋 모델: {self.claude_model}")
        else:
            print(f"📋 모델: {self.model_name}")
        print("=" * 70)
        
        # MariaDB 연결 확인
        if not self.connect_to_database():
            return
        
        # LLM 연결 및 모델 확인
        if self.llm_type == "ollama":
            if not self.check_ollama_connection():
                return
            
            if not self.check_model_availability():
                print("\n💡 OLLAMA 모델을 먼저 설치해주세요:")
                print(f"ollama pull {self.model_name}")
                return
        elif self.llm_type == "claude":
            if not self.check_model_availability():
                print("\n💡 Claude API 설정을 확인해주세요:")
                print("1. ANTHROPIC_API_KEY 환경변수 설정")
                print("2. anthropic 라이브러리 설치: pip install anthropic")
                return
        
        # 테이블 분석
        self.analyze_all_tables()
        
        if not self.tables_info:
            print("❌ 분석할 테이블이 없습니다.")
            return
        
        # Neo4j 연결 및 스키마 그래프 생성
        neo4j_available = self.connect_to_neo4j()
        
        if neo4j_available:
            print("\n🔄 스키마 그래프 분석 중...")
            self.extract_schema_from_ddl()
            self.extract_table_relations()
            self.create_schema_graph_in_neo4j()
            print("✅ 하이브리드 모드 활성화! (Neo4j 그래프 분석 사용)")
        else:
            print("⚠️  기본 모드로 실행 (Neo4j 없이)")
        
        print("\n" + "=" * 60)
        print("🎯 대화형 SQL 쿼리 생성 모드")
        print("종료하려면 'quit' 또는 'exit'를 입력하세요")
        print("=" * 60)
        
        while True:
            try:
                user_input = input("\n📝 검색하고 싶은 내용을 설명해주세요: ").strip()
                
                if user_input.lower() in ['quit', 'exit', '종료']:
                    break
                
                if not user_input:
                    continue
                
                # SQL 쿼리 생성 (하이브리드 모드 우선)
                if neo4j_available:
                    generated_query = self.generate_hybrid_sql_query(user_input)
                else:
                    generated_query = self.generate_sql_query(user_input)
                
                if generated_query:
                    print(f"\n✨ 생성된 SQL 쿼리:")
                    print(f"```sql\n{generated_query}\n```")
                    
                    # 쿼리 실행 여부 확인
                    execute = input("\n실행하시겠습니까? (y/n): ").strip().lower()
                    
                    if execute in ['y', 'yes', 'ㅇ']:
                        results = self.execute_query(generated_query)
                        
                        if results is not None:
                            print(f"\n📊 실행 결과 ({len(results)}개 행):")
                            
                            if results:
                                for i, row in enumerate(results[:10], 1):  # 최대 10개만 표시
                                    print(f"  {i}: {row}")
                                
                                if len(results) > 10:
                                    print(f"  ... 및 {len(results) - 10}개 행 더")
                            else:
                                print("  결과가 없습니다.")
                        else:
                            print("❌ 쿼리 실행에 실패했습니다.")
                else:
                    print("❌ SQL 쿼리 생성에 실패했습니다.")
                    
            except KeyboardInterrupt:
                print("\n\n👋 프로그램을 종료합니다.")
                break
            except Exception as e:
                print(f"❌ 오류 발생: {e}")
        
        self.disconnect_from_database()
        print("🏁 프로그램이 종료되었습니다.")

def main():
    """메인 함수"""
    generator = HybridQueryGenerator()
    generator.run_interactive_mode()

if __name__ == "__main__":
    main()
