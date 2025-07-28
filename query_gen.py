"""
Code LLM을 이용한 SELECT QUERY 생성 (Hybrid: OLLAMA + Claude API 지원)

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
from pathlib import Path
from dotenv import load_dotenv
import anthropic

# .env 파일 로드
try:
    
    # .env 파일 찾기 (현재 디렉토리 또는 상위 디렉토리에서)
    env_path = Path('.env')
    if not env_path.exists():
        parent_env = Path('..') / '.env'
        if parent_env.exists():
            env_path = parent_env
    
    if env_path.exists():
        print(f"✅ .env 파일 로드: {env_path}")
        load_dotenv(env_path)
    else:
        print("⚠️ .env 파일을 찾을 수 없습니다.")
except ImportError:
    print("⚠️ python-dotenv 패키지가 필요합니다. pip install python-dotenv")

# Claude API 사용을 위한 import (설치 필요: pip install anthropic)
try:
    
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
    relation_type: str  # 'foreign_key', 'semantic', 'naming_pattern', 'description_semantic'
    confidence: float   # 관계의 확신도 (0.0 ~ 1.0)
    # 컬럼 메타데이터 추가
    from_column_type: str = ""     # 컬럼 타입 (예: INT, VARCHAR, etc.)
    to_column_type: str = ""       # 컬럼 타입
    from_column_desc: str = ""     # 컬럼 설명/코멘트
    to_column_desc: str = ""       # 컬럼 설명/코멘트
    is_nullable: bool = True       # NULL 허용 여부
    is_indexed: bool = False       # 인덱스 여부

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
        
                # LLM 모델 설정
        # =================================================================
        
        # 1. 초기 구성용 Claude 설정 (테이블 관계 분석)
        self.init_llm_type = "claude"
        self.claude_model = "claude-sonnet-4-20250514"  # 최신 Claude 모델
        self.claude_api_key = os.getenv('ANTHROPIC_API_KEY', "")  # 환경변수에서 API 키 읽기
        if not self.claude_api_key:
            print("⚠️ ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")
            self.init_llm_type = "ollama"  # Claude API 키가 없으면 OLLAMA로 폴백
        
        # 2. 쿼리 생성용 CodeLlama 설정
        self.query_llm_type = "ollama"
        self.ollama_url = "http://localhost:11434"
        self.codellama_model = "codellama:7b"  # 쿼리 생성에 사용할 모델
        
        # 현재 사용 중인 LLM 설정 (초기화는 Claude, 쿼리 생성은 CodeLlama)
        self.current_llm = self.init_llm_type  # 시작은 초기화 모드
        
        self.connection = None
        self.neo4j_driver = None
        self.tables_info = {}
        self.table_schemas = {}
        self.table_relations = []
        
        # LLM 클라이언트 초기화
        # 1. Claude 초기화 시도 (초기 분석용)
        if self.init_llm_type == "claude":
            if not ANTHROPIC_AVAILABLE:
                print("❌ anthropic 라이브러리가 설치되지 않았습니다.")
                print("💡 설치 명령: pip install anthropic")
                self.init_llm_type = "ollama"  # 폴백
            elif not self.claude_api_key:
                print("⚠️  ANTHROPIC_API_KEY가 설정되지 않았습니다.")
                print("💡 다음 중 하나를 선택하세요:")
                print("   1. .env 파일에 ANTHROPIC_API_KEY 설정")
                print("   2. 환경변수 설정: export ANTHROPIC_API_KEY='your-key'")
                print("   3. OLLAMA 모델로 자동 전환")
                self.init_llm_type = "ollama"  # 폴백
            else:
                try:
                    self.claude_client = anthropic.Anthropic(api_key=self.claude_api_key)
                    print(f"✅ Claude API 클라이언트 초기화 완료: {self.claude_model}")
                except Exception as e:
                    print(f"❌ Claude API 클라이언트 초기화 실패: {e}")
                    self.init_llm_type = "ollama"  # 폴백
        
        # 2. OLLAMA 초기화 확인 (쿼리 생성용)
        if self.init_llm_type == "ollama" or self.query_llm_type == "ollama":
            if not self.check_ollama_connection():
                print("❌ OLLAMA 서버 연결 실패")
                if self.init_llm_type == "ollama":
                    print("⚠️ 초기 분석에 필요한 LLM이 모두 사용 불가능합니다.")
                    raise RuntimeError("사용 가능한 LLM이 없습니다.")
            else:
                print(f"✅ OLLAMA 서버 연결 성공: {self.codellama_model}")
    
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
        try:
            if hasattr(self, 'connection') and self.connection:
                self.connection.close()
                print("🔌 MariaDB 연결 종료")
        except Exception as e:
            print(f"⚠️ MariaDB 연결 종료 중 오류: {e}")
        
        if hasattr(self, 'neo4j_driver') and self.neo4j_driver:
            try:
                self.neo4j_driver.close()
                print("🔌 Neo4j 연결 종료")
            except Exception as e:
                print(f"⚠️ Neo4j 연결 종료 중 오류: {e}")
        
    
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
        """OLLAMA 서버 연결 및 모델 사용 가능 여부 확인"""
        try:
            # OLLAMA 서버 연결 확인
            response = requests.get(f"{self.ollama_url}/api/tags")
            if response.status_code != 200:
                print("❌ OLLAMA 서버 응답 오류")
                print("💡 OLLAMA가 실행 중인지 확인하세요: ollama serve")
                return False
            
            # 사용할 모델이 설치되어 있는지 확인
            models = response.json().get('models', [])
            available_models = [model['name'] for model in models]
            
            if self.codellama_model not in available_models:
                print(f"❌ 모델 '{self.codellama_model}'이 설치되지 않았습니다.")
                print("📋 사용 가능한 모델들:")
                for model in available_models:
                    print(f"  - {model}")
                print(f"\n💡 모델 설치 명령: ollama pull {self.codellama_model}")
                return False
            
            print(f"✅ OLLAMA 서버 연결 및 모델 '{self.codellama_model}' 사용 가능!")
            return True
            
        except Exception as e:
            print(f"❌ OLLAMA 서버 연결 실패: {e}")
            print("💡 OLLAMA가 실행 중인지 확인하세요: ollama serve")
            return False
    
    def check_model_availability(self) -> bool:
        """초기화 및 쿼리 생성용 모델 사용 가능성 확인"""
        models_available = True
        
        # 1. 초기화용 모델 확인
        if self.init_llm_type == "claude":
            if not hasattr(self, 'claude_client'):
                print("❌ Claude API 클라이언트가 초기화되지 않았습니다.")
                models_available = False
        else:  # OLLAMA 사용
            if not self.check_ollama_connection():
                print("❌ 초기화용 OLLAMA 모델을 사용할 수 없습니다.")
                models_available = False
        
        # 2. 쿼리 생성용 모델 확인 (항상 OLLAMA)
        if not self.check_ollama_connection():
            print("❌ 쿼리 생성용 OLLAMA 모델을 사용할 수 없습니다.")
            models_available = False
        
        if models_available:
            print("✅ 모든 필요한 모델이 사용 가능합니다!")
            if self.init_llm_type == "claude":
                print(f"  - 초기화: Claude ({self.claude_model})")
            else:
                print(f"  - 초기화: OLLAMA ({self.codellama_model})")
            print(f"  - 쿼리 생성: OLLAMA ({self.codellama_model})")
        
        return models_available
    
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
    
    def call_llm(self, prompt: str, stage: str = "init") -> Optional[str]:
        """LLM 호출 - 단계별로 적절한 모델 사용
        
        Args:
            prompt: 프롬프트 문자열
            stage: 실행 단계
                - "init": 초기 구성 (Claude 또는 OLLAMA)
                - "table_search": 테이블 검색 (CodeLlama)
                - "column_search": 컬럼 검색 (CodeLlama)
                - "validation": 스키마 검증 (CodeLlama)
                - "query_gen": 최종 쿼리 생성 (CodeLlama)
        """
        print(f"\n🤖 LLM 호출 단계: {stage}")
        
        if stage == "init":
            # 초기 구성은 설정된 init_llm_type 사용
            if self.init_llm_type == "claude":
                print(f"📋 Claude 모델 사용: {self.claude_model}")
                return self.call_claude_api(prompt)
            else:
                print(f"📋 OLLAMA 모델 사용: {self.codellama_model}")
                return self.call_codellama_api(prompt)
        else:
            # 쿼리 생성 단계는 CodeLlama 사용
            print(f"📋 CodeLlama 모델 사용: {self.codellama_model}")
            return self.call_codellama_api(prompt)
    
    def call_codellama_api(self, prompt: str) -> Optional[str]:
        """CodeLlama API 호출"""
        try:
            print(f"🤖 CodeLlama 호출: {self.codellama_model}")
            
            payload = {
                "model": self.codellama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # 정확한 SQL 생성을 위해 낮은 온도
                    "top_p": 0.9,
                    "num_predict": 2000  # 토큰 수를 2000으로 증가
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
                print(f"❌ CodeLlama 호출 실패: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ CodeLlama 호출 중 오류: {e}")
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
        """테이블 간 관계 추출 - Foreign Key와 LLM 기반 의미적 분석만 사용"""
        relations = []
        
        # 1. Foreign Key 관계 추출 (데이터베이스 스키마에서 명시적으로 정의된 관계)
        print("🔍 Foreign Key 관계 추출 중...")
        for table_name, schema in self.table_schemas.items():
            for fk in schema.foreign_keys:
                # FK 컬럼 메타데이터 찾기
                from_col_meta = next((col for col in schema.columns if col['name'] == fk['from_column']), None)
                to_schema = self.table_schemas.get(fk['to_table'])
                to_col_meta = next((col for col in to_schema.columns if col['name'] == fk['to_column']), None) if to_schema else None
                
                relations.append(TableRelation(
                    from_table=table_name,
                    from_column=fk['from_column'],
                    to_table=fk['to_table'],
                    to_column=fk['to_column'],
                    relation_type='foreign_key',
                    confidence=1.0,
                    # 컬럼 메타데이터 추가
                    from_column_type=from_col_meta.get('type', '') if from_col_meta else '',
                    to_column_type=to_col_meta.get('type', '') if to_col_meta else '',
                    from_column_desc=from_col_meta.get('comment', '') if from_col_meta else '',
                    to_column_desc=to_col_meta.get('comment', '') if to_col_meta else '',
                    is_nullable=from_col_meta.get('nullable', True) if from_col_meta else True,
                    is_indexed=True  # FK는 일반적으로 인덱스가 있음
                ))
        
        print(f"✅ Foreign Key 관계 {len(relations)}개 추출 완료")
        
        # 2. LLM 기반 의미적 관계 추출 (테이블 설명 분석)
        description_relations = self.extract_semantic_relations_from_descriptions()
        
        # 의미적 관계에 대해 가능한 컬럼 정보 추가
        for rel in description_relations:
            # 관련된 테이블의 주요 컬럼 찾기 (ID 또는 이름 컬럼)
            from_schema = self.table_schemas.get(rel.from_table)
            to_schema = self.table_schemas.get(rel.to_table)
            
            if from_schema and to_schema:
                # 주요 컬럼 후보 (ID 컬럼 또는 이름 관련 컬럼)
                from_col = next((col for col in from_schema.columns 
                               if col['name'].endswith('_id') or 'name' in col['name'].lower()), None)
                to_col = next((col for col in to_schema.columns 
                             if col['name'].endswith('_id') or 'name' in col['name'].lower()), None)
                
                if from_col and to_col:
                    rel.from_column = from_col['name']
                    rel.to_column = to_col['name']
                    rel.from_column_type = from_col.get('type', '')
                    rel.to_column_type = to_col.get('type', '')
                    rel.from_column_desc = from_col.get('comment', '')
                    rel.to_column_desc = to_col.get('comment', '')
                    rel.is_nullable = from_col.get('nullable', True)
                    rel.is_indexed = from_col['name'].endswith('_id')  # ID 컬럼은 보통 인덱스가 있음
        
        relations.extend(description_relations)
        self.table_relations = relations
        
        # 관계 정보 출력
        print(f"🔗 총 {len(relations)}개 관계 추출 완료")
        for rel in relations:
            print(f"  {rel.from_table}.{rel.from_column} ({rel.from_column_type}) → "
                  f"{rel.to_table}.{rel.to_column} ({rel.to_column_type})")
            print(f"    유형: {rel.relation_type}, 신뢰도: {rel.confidence}")
            if rel.from_column_desc or rel.to_column_desc:
                print(f"    설명: {rel.from_column_desc} → {rel.to_column_desc}")
        
        return relations
    
    def extract_semantic_relations_from_descriptions(self) -> List[TableRelation]:
        """Neo4j에 저장된 테이블 설명을 활용한 의미적 관계 추출"""
        if not self.neo4j_driver:
            print("⚠️ Neo4j 연결이 없어 테이블 설명 기반 관계 추출을 건너뜁니다.")
            return []
        
        print("🧠 Neo4j 테이블 설명을 활용한 의미적 관계 분석 중...")
        
        # Neo4j에서 모든 테이블의 설명 정보 가져오기
        table_descriptions = self.get_table_descriptions_from_neo4j()
        print(table_descriptions)
        if len(table_descriptions) < 2:
            print("⚠️ 충분한 테이블 설명이 없어 의미적 관계 추출을 건너뜁니다.")
            return []
        
        # LLM을 활용하여 테이블 간 의미적 관계 분석
        semantic_relations = self.analyze_semantic_relationships_with_llm(table_descriptions)
        print(semantic_relations)
        
        return semantic_relations
    
    def get_table_descriptions_from_neo4j(self) -> Dict[str, str]:
        """Neo4j에서 모든 테이블의 설명 정보 조회"""
        table_descriptions = {}
        
        try:
            with self.neo4j_driver.session() as session:
                query = """
                MATCH (t:Table)
                RETURN t.name as table_name, t.comment as description
                ORDER BY t.name
                """
                
                result = session.run(query)
                for record in result:
                    table_name = record['table_name']
                    description = record['description']
                    if description:  # 설명이 있는 테이블만
                        table_descriptions[table_name] = description
                
                print(f"📋 Neo4j에서 {len(table_descriptions)}개 테이블 설명 조회")
                
        except Exception as e:
            print(f"❌ Neo4j에서 테이블 설명 조회 실패: {e}")
        
        return table_descriptions
    
    def analyze_semantic_relationships_with_llm(self, table_descriptions: Dict[str, str]) -> List[TableRelation]:
        """LLM을 활용하여 테이블 설명 간 의미적 관계 분석"""
        relations = []
        
        # 테이블 설명 정보를 프롬프트용으로 정리
        descriptions_text = "데이터베이스 테이블 설명:\n"
        for table, desc in table_descriptions.items():
            descriptions_text += f"- {table}: {desc}\n"
        
        # LLM 타입에 따른 최적화된 프롬프트 생성
        if self.current_llm == "claude":
            prompt = f"""{descriptions_text}

위의 테이블 설명들을 분석하여 테이블 간 의미적 관계를 찾아주세요.

분석 기준:
1. 비즈니스 로직상 밀접한 관련이 있는 테이블들
2. 데이터 흐름상 연결되어야 하는 테이블들  
3. 일반적으로 함께 조회되는 테이블들
4. 부모-자식 관계나 주체-객체 관계

각 관계에 대해 다음 정보를 제공해주세요:
- 관련 테이블 쌍
- 관계의 이유/설명
- 관계 강도 (0.1~0.9, 높을수록 강한 관계)

응답은 반드시 다음 JSON 형식으로만 반환해주세요:
{{
  "relationships": [
    {{
      "table1": "테이블명1",
      "table2": "테이블명2", 
      "reason": "관계 설명",
      "confidence": 0.8
    }}
  ]
}}"""
        else:
            prompt = f"""{descriptions_text}

위의 테이블 설명을 분석하여 테이블 간 의미적 관계를 찾아주세요.

기준:
1. 비즈니스 로직상 관련 있는 테이블
2. 데이터 흐름상 연결되는 테이블
3. 함께 조회되는 테이블들

JSON 형식으로 응답:
{{
  "relationships": [
    {{
      "table1": "테이블명1",
      "table2": "테이블명2",
      "reason": "관계 설명", 
      "confidence": 0.8
    }}
  ]
}}

JSON:"""
        
        # LLM 호출
        response = self.call_llm(prompt, stage="init")
        
        if response:
            try:
                import json
                
                # JSON 블록 추출
                response_clean = response.strip()
                json_start = response_clean.find('{')
                json_end = response_clean.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_str = response_clean[json_start:json_end]
                    result = json.loads(json_str)
                    
                    if 'relationships' in result:
                        for rel_data in result['relationships']:
                            table1 = rel_data.get('table1', '')
                            table2 = rel_data.get('table2', '')
                            reason = rel_data.get('reason', '')
                            confidence = float(rel_data.get('confidence', 0.5))
                            
                            # 유효한 테이블인지 확인
                            if (table1 in self.table_schemas and 
                                table2 in self.table_schemas and 
                                table1 != table2):
                                
                                # 이미 존재하는 관계인지 확인
                                existing = any(
                                    (r.from_table == table1 and r.to_table == table2) or
                                    (r.from_table == table2 and r.to_table == table1)
                                    for r in self.table_relations
                                )
                                
                                if not existing:
                                    # 양방향 관계로 추가 (설명 기반이므로 특정 컬럼 없음)
                                    relations.append(TableRelation(
                                        from_table=table1,
                                        from_column='',  # 설명 기반이므로 특정 컬럼 없음
                                        to_table=table2,
                                        to_column='',
                                        relation_type='description_semantic',
                                        confidence=min(confidence, 0.9)  # 최대 0.9로 제한
                                    ))
                                    
                                    print(f"  📝 발견된 의미적 관계: {table1} ↔ {table2} ({reason}) [신뢰도: {confidence}]")
                        
                        print(f"✅ 설명 기반 의미적 관계 {len(relations)}개 추출 완료")
                        
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                print(f"⚠️ LLM 응답 파싱 실패: {e}")
                print(f"📄 원본 응답: {response[:200]}...")
        
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
            
            # 관계 생성 (다양한 관계 타입 지원)
            for rel in self.table_relations:
                # 관계 타입에 따라 다른 Neo4j 관계 생성
                if rel.relation_type == 'description_semantic':
                    # 의미적 관계는 양방향으로 생성 (두 개의 방향 관계로)
                    session.run("""
                        MATCH (table1:Table {name: $from_table})
                        MATCH (table2:Table {name: $to_table})
                        CREATE (table1)-[:SEMANTIC_RELATION {
                            relation_type: $relation_type,
                            confidence: $confidence,
                            description: 'LLM analyzed semantic relationship based on table descriptions'
                        }]->(table2)
                    """, from_table=rel.from_table, to_table=rel.to_table,
                    relation_type=rel.relation_type, confidence=rel.confidence)
                    
                    # 반대 방향 관계도 생성
                    session.run("""
                        MATCH (table1:Table {name: $from_table})
                        MATCH (table2:Table {name: $to_table})
                        CREATE (table2)-[:SEMANTIC_RELATION {
                            relation_type: $relation_type,
                            confidence: $confidence,
                            description: 'LLM analyzed semantic relationship based on table descriptions'
                        }]->(table1)
                    """, from_table=rel.from_table, to_table=rel.to_table,
                    relation_type=rel.relation_type, confidence=rel.confidence)
                else:
                    # 기존 방식 (FK, 네이밍 패턴 등)
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
    
    def get_semantic_relations_from_neo4j(self) -> List[Dict]:
        """Neo4j에서 의미적 관계 정보 조회"""
        if not self.neo4j_driver:
            return []
        
        semantic_relations = []
        
        try:
            with self.neo4j_driver.session() as session:
                query = """
                MATCH (t1:Table)-[r:SEMANTIC_RELATION]-(t2:Table)
                WHERE t1.name < t2.name
                RETURN t1.name as table1, t2.name as table2, 
                       r.confidence as confidence, r.relation_type as relation_type
                ORDER BY r.confidence DESC
                """
                
                result = session.run(query)
                for record in result:
                    semantic_relations.append({
                        'table1': record['table1'],
                        'table2': record['table2'],
                        'confidence': record['confidence'],
                        'relation_type': record['relation_type']
                    })
                
                print(f"📋 Neo4j에서 {len(semantic_relations)}개 의미적 관계 조회")
                
        except Exception as e:
            print(f"❌ Neo4j에서 의미적 관계 조회 실패: {e}")
        
        return semantic_relations
    
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
    
    def search_tables_with_graph_metadata(self, user_request: str) -> List[str]:
        """Neo4j 그래프 메타 정보를 활용한 순수 그래프 기반 테이블 검색"""
        if not self.neo4j_driver:
            print("❌ Neo4j 연결이 필요합니다. 키워드 방식으로 폴백합니다.")
            return self.extract_relevant_tables_fallback(user_request)
        
        print("🔍 Neo4j 그래프 메타 정보로 의미적 테이블 검색 중...")
        
        with self.neo4j_driver.session() as session:
            # 1단계: LLM을 활용한 의미적 테이블 검색
            print("🧠 LLM이 사용자 요청을 분석하여 관련 테이블을 찾는 중...")
            
            # 모든 테이블과 설명 정보 가져오기
            all_tables_query = """
            MATCH (t:Table)
            RETURN t.name as table_name, t.comment as comment
            ORDER BY t.name
            """
            
            all_tables = session.run(all_tables_query)
            table_info = []
            for record in all_tables:
                table_info.append({
                    'name': record['table_name'],
                    'description': record['comment']
                })
            
            # LLM에게 의미적 분석 요청
            table_descriptions = "\n".join([
                f"- {table['name']}: {table['description']}" 
                for table in table_info
            ])
            
            # LLM 타입에 따른 프롬프트 생성
            if self.init_llm_type == "claude":
                prompt = f"""다음은 데이터베이스의 모든 테이블과 설명입니다:

{table_descriptions}

사용자 요청: "{user_request}"

위의 테이블 설명을 바탕으로 사용자 요청을 처리하는데 필요한 테이블들을 의미적으로 분석하여 선택해주세요.

분석 기준:
1. 사용자가 원하는 정보와 직접적으로 관련된 테이블
2. 데이터를 조인하기 위해 필요한 중간 테이블
3. 비즈니스 로직상 함께 조회되어야 하는 테이블

응답은 반드시 다음 JSON 형식으로만 반환해주세요:
{{"selected_tables": ["table1", "table2"], "reasoning": "선택 이유를 설명"}}"""
            else:
                prompt = f"""데이터베이스 테이블 정보:
{table_descriptions}

사용자 요청: {user_request}

위 테이블들 중에서 사용자 요청을 처리하는데 필요한 테이블들을 선택하여 JSON으로 반환해주세요.

JSON 형식:
{{"selected_tables": ["테이블명1", "테이블명2"], "reasoning": "선택 이유"}}

JSON:"""
            
            # LLM 호출
            llm_response = self.call_llm(prompt)
            selected_tables = []
            
            if llm_response:
                try:
                    # JSON 파싱
                    import json
                    response_clean = llm_response.strip()
                    
                    # JSON 블록 찾기
                    json_start = response_clean.find('{')
                    json_end = response_clean.rfind('}') + 1
                    
                    if json_start >= 0 and json_end > json_start:
                        json_str = response_clean[json_start:json_end]
                        result = json.loads(json_str)
                        
                        if 'selected_tables' in result:
                            selected_tables = result['selected_tables']
                            reasoning = result.get('reasoning', '')
                            
                            print(f"🎯 LLM 선택 결과: {selected_tables}")
                            print(f"📝 선택 이유: {reasoning}")
                            
                except (json.JSONDecodeError, Exception) as e:
                    print(f"⚠️ LLM 응답 파싱 실패: {e}")
                    selected_tables = []
            
            # 2단계: 그래프 기반 연관 테이블 확장 (의미적 관계 포함)
            if selected_tables:
                print("🔗 그래프에서 연관 테이블 자동 확장 중...")
                
                # 2-1. 기존 FK/참조 관계로 연결된 테이블 찾기
                expand_query = """
                MATCH (selected:Table)-[:REFERENCES*1..2]-(related:Table)
                WHERE selected.name IN $selected_tables 
                  AND NOT related.name IN $selected_tables
                RETURN DISTINCT related.name as related_table, 
                       related.comment as comment,
                       shortestPath((selected)-[:REFERENCES*1..2]-(related)) as path,
                       'reference' as relation_source
                ORDER BY length(path), related_table
                LIMIT 3
                """
                
                expand_results = session.run(expand_query, selected_tables=selected_tables)
                
                for record in expand_results:
                    related_table = record['related_table']
                    comment = record['comment']
                    path_length = len(record['path'].relationships)
                    
                    # 관계 거리가 가까운 중요한 테이블만 추가
                    if path_length <= 2:
                        selected_tables.append(related_table)
                        print(f"  + {related_table}: {comment} (FK 거리: {path_length})")
                
                # 2-2. 의미적 관계로 연결된 테이블 찾기
                semantic_query = """
                MATCH (selected:Table)-[:SEMANTIC_RELATION]-(related:Table)
                WHERE selected.name IN $selected_tables 
                  AND NOT related.name IN $selected_tables
                RETURN DISTINCT related.name as related_table, 
                       related.comment as comment,
                       'semantic' as relation_source
                ORDER BY related_table
                LIMIT 2
                """
                
                semantic_results = session.run(semantic_query, selected_tables=selected_tables)
                
                for record in semantic_results:
                    related_table = record['related_table']
                    comment = record['comment']
                    
                    if related_table not in selected_tables:
                        selected_tables.append(related_table)
                        print(f"  + {related_table}: {comment} (의미적 관계)")
            
            # 3단계: 폴백 - LLM 분석이 실패한 경우
            if not selected_tables:
                print("⚠️ LLM 분석 실패. 그래프 중심성 기반으로 주요 테이블 선택...")
                
                # 테이블 중심성(연결도) 기반 선택
                centrality_query = """
                MATCH (t:Table)
                OPTIONAL MATCH (t)-[r:REFERENCES]-(other:Table)
                WITH t, count(r) as connections
                ORDER BY connections DESC, t.name
                LIMIT 4
                RETURN t.name as table_name, t.comment as comment, connections
                """
                
                centrality_results = session.run(centrality_query)
                for record in centrality_results:
                    table_name = record['table_name']
                    comment = record['comment']
                    connections = record['connections']
                    selected_tables.append(table_name)
                    print(f"  - {table_name}: {comment} (연결수: {connections})")
            
            # 4단계: 최종 검증 및 정리
            final_tables = []
            for table in selected_tables:
                if table in self.table_schemas and table not in final_tables:
                    final_tables.append(table)
            
            print(f"✅ 최종 선택된 테이블: {final_tables}")
            return final_tables[:6]  # 최대 6개 테이블로 제한
    
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
        """테이블 스키마 정보를 LLM 프롬프트용으로 변환 (정확한 컬럼 정보 포함)"""
        prompt = "다음은 데이터베이스의 정확한 테이블 스키마 정보입니다:\n\n"
        
        for table_name, info in self.tables_info.items():
            # 테이블 설명 추가
            table_schema = self.table_schemas.get(table_name)
            table_comment = table_schema.comment if table_schema else ""
            
            prompt += f"📋 테이블: {table_name}\n"
            if table_comment:
                prompt += f"   설명: {table_comment}\n"
            
            prompt += "   컬럼 정보:\n"
            
            # 실제 데이터베이스에서 조회한 컬럼 정보 사용
            for col in info['columns']:
                col_name, col_type, null_allowed = col[0], col[1], col[2]
                col_key = col[3] if len(col) > 3 else ""
                col_default = col[4] if len(col) > 4 else ""
                col_extra = col[5] if len(col) > 5 else ""
                
                # 컬럼 설명 생성
                col_desc = f"  - {col_name}: {col_type}"
                
                if col_key == "PRI":
                    col_desc += " (기본키)"
                elif col_key == "MUL":
                    col_desc += " (외래키)"
                
                if null_allowed == "NO":
                    col_desc += " NOT NULL"
                
                if col_extra == "auto_increment":
                    col_desc += " AUTO_INCREMENT"
                
                prompt += col_desc + "\n"
            
            # Foreign Key 관계 정보 추가
            if table_schema and table_schema.foreign_keys:
                prompt += "   외래키 관계:\n"
                for fk in table_schema.foreign_keys:
                    prompt += f"     - {fk['from_column']} → {fk['to_table']}.{fk['to_column']}\n"
            
            # 샘플 데이터 (컬럼명과 함께)
            if info['sample_data']:
                prompt += "   샘플 데이터:\n"
                col_names = [col[0] for col in info['columns']]
                prompt += f"     컬럼: {', '.join(col_names)}\n"
                for i, row in enumerate(info['sample_data'][:2], 1):
                    prompt += f"     {i}: {row}\n"
            
            prompt += "\n"
        
        # 중요한 주의사항 추가
        prompt += "⚠️ 중요: 쿼리 작성 시 반드시 위에 명시된 정확한 컬럼명을 사용하세요.\n"
        prompt += "테이블별 컬럼 구조를 정확히 확인하고 존재하지 않는 컬럼을 참조하지 마세요.\n\n"
        
        return prompt
    
    def validate_sql_query(self, query: str) -> Tuple[bool, List[str]]:
        """생성된 SQL 쿼리의 기본적인 검증"""
        errors = []
        
        try:
            # 기본적인 구문 검증
            query_upper = query.upper()
            
            # 1. SELECT 문인지 확인
            if not query_upper.strip().startswith('SELECT'):
                errors.append("쿼리는 SELECT 문으로 시작해야 합니다.")
            
            # 2. 테이블명 검증
            available_tables = set(self.tables_info.keys())
            
            # FROM, JOIN 절에서 테이블명과 별칭 추출
            import re
            table_pattern = r'(?:FROM|JOIN)\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?'
            found_tables = re.findall(table_pattern, query, re.IGNORECASE)
            
            # 테이블 별칭 매핑 생성
            table_aliases = {}
            for table, alias in found_tables:
                actual_table = None
                table_lower = table.lower()
                
                # 실제 테이블 찾기
                if table_lower in [t.lower() for t in available_tables]:
                    actual_table = table
                
                if not actual_table:
                    errors.append(f"존재하지 않는 테이블: {table}")
                    continue
                
                # 별칭 저장 (별칭이 없으면 테이블명 자체를 별칭으로)
                alias = alias.strip() if alias else table
                table_aliases[alias.lower()] = actual_table
            
            # 3. 컬럼 참조 검증 (더 정확한 검증)
            # 모든 컬럼 참조 추출 (SELECT, WHERE, GROUP BY, ORDER BY 등)
            column_pattern = r'(?:SELECT|WHERE|GROUP\s+BY|ORDER\s+BY|ON)\s+(?:.*?[^.\w])(\w+)\.(\w+)(?=[^.\w]|$)'
            column_refs = re.findall(column_pattern, query, re.IGNORECASE)
            
            for alias, column in column_refs:
                alias_lower = alias.lower()
                if alias_lower not in table_aliases:
                    errors.append(f"정의되지 않은 테이블 별칭: {alias}")
                    continue
                
                actual_table = table_aliases[alias_lower]
                available_columns = [col[0].lower() for col in self.tables_info[actual_table]['columns']]
                
                if column.lower() not in available_columns:
                    errors.append(f"테이블 {actual_table}에 존재하지 않는 컬럼: {column}")
            
            # 4. JOIN 조건 검증
            join_pattern = r'JOIN\s+\w+(?:\s+(?:AS\s+)?\w+)?\s+ON\s+([^()]+?)(?=\s+(?:WHERE|GROUP|ORDER|LIMIT|$))'
            join_conditions = re.findall(join_pattern, query, re.IGNORECASE)
            
            for condition in join_conditions:
                # 조인 조건의 양쪽 컬럼 추출 (a.id = b.user_id 형태)
                parts = condition.split('=')
                if len(parts) != 2:
                    errors.append(f"잘못된 JOIN 조건: {condition}")
                    continue
                
                for part in parts:
                    col_ref = part.strip().split('.')
                    if len(col_ref) != 2:
                        errors.append(f"잘못된 컬럼 참조: {part.strip()}")
                        continue
                    
                    alias, column = col_ref
                    alias_lower = alias.lower()
                    if alias_lower not in table_aliases:
                        errors.append(f"JOIN 조건에서 정의되지 않은 테이블 별칭: {alias}")
                        continue
                    
                    actual_table = table_aliases[alias_lower]
                    available_columns = [col[0].lower() for col in self.tables_info[actual_table]['columns']]
                    if column.lower() not in available_columns:
                        errors.append(f"JOIN 조건에서 테이블 {actual_table}에 존재하지 않는 컬럼: {column}")
            
        except Exception as e:
            errors.append(f"쿼리 검증 중 오류 발생: {str(e)}")
            import traceback
            print("💡 검증 오류 상세:")
            print(traceback.format_exc())
        
        return len(errors) == 0, errors
    
    def generate_hybrid_sql_query(self, user_request: str) -> Optional[str]:
        """README.md의 방향성에 따른 단계별 SQL 쿼리 생성"""
        print("\n🚀 단계별 SQL 쿼리 생성 시작...")
        
        # 단계 1: CodeLlama로 대상 테이블 검색 (Neo4j 활용)
        print("\n📋 단계 1: 대상 테이블 검색")
        relevant_tables = self.find_target_tables(user_request)
        if not relevant_tables:
            print("❌ 관련 테이블을 찾을 수 없습니다.")
            return None
        print(f"✅ 검색된 테이블: {relevant_tables}")
        
        # 단계 2: CodeLlama로 필요한 컬럼 검색 (Neo4j 활용)
        print("\n📋 단계 2: 필요 컬럼 검색")
        relevant_columns = self.find_target_columns(user_request, relevant_tables)
        if not relevant_columns:
            print("❌ 필요한 컬럼을 찾을 수 없습니다.")
            return None
        print("✅ 검색된 컬럼:")
        for table, columns in relevant_columns.items():
            print(f"  - {table}: {', '.join(columns)}")
        
        # 단계 3: 검색된 테이블/컬럼 검증
        print("\n📋 단계 3: 스키마 검증")
        is_valid, errors = self.validate_schema_elements(relevant_tables, relevant_columns)
        if not is_valid:
            print("❌ 스키마 검증 실패:")
            for error in errors:
                print(f"  - {error}")
            return None
        print("✅ 스키마 검증 완료")
        
        # 단계 4: CodeLlama로 최종 쿼리 생성
        print("\n📋 단계 4: 최종 쿼리 생성")
        final_query = self.generate_final_query(user_request, relevant_tables, relevant_columns)
        if not final_query:
            print("❌ 쿼리 생성 실패")
            return None
        
        print("✅ 쿼리 생성 완료")
        return final_query
    
    def find_target_tables(self, user_request: str) -> List[str]:
        """단계 1: CodeLlama를 사용하여 Neo4j에서 대상 테이블 검색"""
        prompt = f"""사용자 요청: {user_request}

중요: 아래 JSON 형식으로만 응답하세요. 설명이나 추가 텍스트를 포함하지 마세요.

{{"tables": ["필요한테이블1", "필요한테이블2"], "reason": "선택 이유"}}"""

        response = self.call_llm(prompt, stage="table_search")
        if not response:
            return []
        
        try:
            import json
            # JSON 블록 추출
            response_clean = response.strip()
            json_start = response_clean.find('{')
            json_end = response_clean.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_clean[json_start:json_end]
                result = json.loads(json_str)
                print(f"🔍 선택된 테이블: {result.get('tables', [])}")
                print(f"📝 선택 이유: {result.get('reason', '')}")
                return result.get('tables', [])
        except Exception as e:
            print(f"⚠️ JSON 파싱 실패: {e}")
            print(f"💡 원본 응답:\n{response}")
        return []
    
    def find_target_columns(self, user_request: str, tables: List[str]) -> Dict[str, List[str]]:
        """단계 2: Neo4j에서 실제 컬럼 메타데이터를 조회하여 필요한 컬럼 검색"""
        if not self.neo4j_driver:
            print("❌ Neo4j 연결이 없어 기본 컬럼 검색으로 폴백합니다.")
            return self._fallback_column_search(user_request, tables)
        
        print("🔍 Neo4j에서 실제 컬럼 메타데이터 조회 중...")
        
        # 1단계: Neo4j에서 각 테이블의 실제 컬럼 정보 조회
        table_columns_metadata = {}
        
        try:
            with self.neo4j_driver.session() as session:
                for table in tables:
                    query = """
                    MATCH (t:Table {name: $table_name})-[:HAS_COLUMN]->(c:Column)
                    RETURN c.name as column_name, 
                           c.type as column_type, 
                           c.nullable as nullable,
                           c.auto_increment as auto_increment
                    ORDER BY c.name
                    """
                    
                    result = session.run(query, table_name=table)
                    columns_info = []
                    
                    for record in result:
                        column_info = {
                            'name': record['column_name'],
                            'type': record['column_type'], 
                            'nullable': record.get('nullable', True),
                            'auto_increment': record.get('auto_increment', False)
                        }
                        columns_info.append(column_info)
                    
                    if columns_info:
                        table_columns_metadata[table] = columns_info
                        print(f"  📋 {table}: {len(columns_info)}개 컬럼 조회")
                    else:
                        print(f"  ⚠️ {table}: Neo4j에 컬럼 정보 없음, 직접 DB 조회")
                        # Neo4j에 컬럼 정보가 없으면 직접 DB에서 조회
                        db_columns = self._get_columns_from_db(table)
                        if db_columns:
                            table_columns_metadata[table] = db_columns
        
        except Exception as e:
            print(f"❌ Neo4j 컬럼 조회 실패: {e}")
            return self._fallback_column_search(user_request, tables)
        
        if not table_columns_metadata:
            print("⚠️ 조회된 컬럼 정보가 없습니다.")
            return self._fallback_column_search(user_request, tables)
        
        # 2단계: 컬럼 메타데이터를 포함한 프롬프트 생성
        columns_info = "실제 테이블 컬럼 정보:\n"
        for table, columns in table_columns_metadata.items():
            columns_info += f"\n{table} 테이블:\n"
            for col in columns:
                col_desc = f"  - {col['name']} ({col['type']})"
                if not col.get('nullable', True):
                    col_desc += " NOT NULL"
                if col.get('auto_increment', False):
                    col_desc += " AUTO_INCREMENT"
                columns_info += col_desc + "\n"
        
        # 3단계: LLM에게 실제 컬럼 정보를 제공하여 필요한 컬럼 선택 요청
        if self.init_llm_type == "claude":
            prompt = f"""{columns_info}

사용자 요청: {user_request}

위의 실제 컬럼 정보를 바탕으로 사용자 요청을 처리하는데 필요한 컬럼들을 선택해주세요.

분석 기준:
1. SELECT 절에 포함될 컬럼 (사용자가 조회하고자 하는 데이터)
2. WHERE 절에 필요한 컬럼 (필터링 조건)
3. JOIN 조건에 필요한 컬럼 (테이블 연결)
4. GROUP BY, ORDER BY에 필요한 컬럼

응답은 반드시 다음 JSON 형식으로만 반환해주세요:
{{"columns": {{"table1": ["col1", "col2"], "table2": ["col1", "col2"]}}, "reason": "선택 이유"}}"""
        else:
            prompt = f"""{columns_info}

사용자 요청: {user_request}

위의 실제 컬럼 정보를 보고 필요한 컬럼들을 선택해주세요.

JSON 형식으로 응답:
{{"columns": {{"table1": ["col1", "col2"], "table2": ["col1", "col2"]}}, "reason": "선택 이유"}}

JSON:"""
        
        response = self.call_llm(prompt, stage="column_search")
        if not response:
            print("❌ LLM 컬럼 분석 실패")
            return self._auto_select_essential_columns(table_columns_metadata)
        
        # 4단계: LLM 응답 파싱 및 검증
        try:
            import json
            response_clean = response.strip()
            json_start = response_clean.find('{')
            json_end = response_clean.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_clean[json_start:json_end]
                result = json.loads(json_str)
                
                if 'columns' in result:
                    selected_columns = result['columns']
                    reason = result.get('reason', '')
                    
                    # 5단계: 선택된 컬럼이 실제로 존재하는지 검증
                    validated_columns = {}
                    for table, cols in selected_columns.items():
                        if table in table_columns_metadata:
                            available_columns = [col['name'] for col in table_columns_metadata[table]]
                            valid_cols = [col for col in cols if col in available_columns]
                            
                            if valid_cols:
                                validated_columns[table] = valid_cols
                            else:
                                print(f"⚠️ {table}: 선택된 컬럼 중 유효한 것이 없음, 필수 컬럼 자동 선택")
                                validated_columns[table] = self._get_essential_columns(table_columns_metadata[table])
                    
                    if validated_columns:
                        print(f"✅ 컬럼 선택 완료: {reason}")
                        for table, cols in validated_columns.items():
                            print(f"  - {table}: {', '.join(cols)}")
                        return validated_columns
                        
        except (json.JSONDecodeError, KeyError) as e:
            print(f"⚠️ LLM 응답 파싱 실패: {e}")
        
        # 6단계: 모든 분석이 실패한 경우 필수 컬럼 자동 선택
        print("🔄 자동 필수 컬럼 선택으로 폴백")
        return self._auto_select_essential_columns(table_columns_metadata)
    
    def _get_columns_from_db(self, table_name: str) -> List[Dict]:
        """데이터베이스에서 직접 컬럼 정보 조회 (Neo4j 정보가 없을 때)"""
        try:
            if table_name in self.tables_info:
                db_columns = []
                for col in self.tables_info[table_name]['columns']:
                    col_name, col_type = col[0], col[1]
                    null_allowed = col[2] if len(col) > 2 else "YES"
                    col_extra = col[5] if len(col) > 5 else ""
                    
                    db_columns.append({
                        'name': col_name,
                        'type': col_type,
                        'nullable': null_allowed == "YES",
                        'auto_increment': 'auto_increment' in col_extra.lower()
                    })
                return db_columns
        except Exception as e:
            print(f"⚠️ DB에서 {table_name} 컬럼 조회 실패: {e}")
        return []
    
    def _fallback_column_search(self, user_request: str, tables: List[str]) -> Dict[str, List[str]]:
        """Neo4j 없이 기본 컬럼 검색 (기존 방식)"""
        print("🔄 기본 컬럼 검색 방식으로 폴백")
        
        # 각 테이블의 주요 컬럼들을 자동 선택
        result = {}
        for table in tables:
            if table in self.tables_info:
                # ID 컬럼, name 컬럼, 주요 컬럼들 자동 선택
                columns = [col[0] for col in self.tables_info[table]['columns']]
                essential_cols = []
                
                for col in columns:
                    col_lower = col.lower()
                    if (col_lower.endswith('_id') or 
                        'name' in col_lower or 
                        col_lower in ['id', 'title', 'email', 'status', 'created_at']):
                        essential_cols.append(col)
                
                if essential_cols:
                    result[table] = essential_cols[:5]  # 최대 5개
                else:
                    result[table] = columns[:3]  # 처음 3개 컬럼
        
        return result
    
    def _auto_select_essential_columns(self, table_columns_metadata: Dict[str, List[Dict]]) -> Dict[str, List[str]]:
        """테이블별 필수 컬럼 자동 선택"""
        result = {}
        
        for table, columns in table_columns_metadata.items():
            essential_cols = []
            
            # 우선순위별 컬럼 선택
            for col in columns:
                col_name = col['name'].lower()
                
                # 1순위: ID 컬럼 (PK, FK)
                if col_name.endswith('_id') or col_name == 'id':
                    essential_cols.append(col['name'])
                # 2순위: 이름/제목 컬럼
                elif 'name' in col_name or 'title' in col_name:
                    essential_cols.append(col['name'])
                # 3순위: 상태, 날짜 컬럼
                elif col_name in ['status', 'email', 'created_at', 'updated_at']:
                    essential_cols.append(col['name'])
            
            # 필수 컬럼이 없으면 처음 몇 개 선택
            if not essential_cols:
                essential_cols = [col['name'] for col in columns[:3]]
            
            result[table] = essential_cols[:5]  # 최대 5개로 제한
            print(f"  🔧 {table}: 자동 선택된 컬럼 {essential_cols}")
        
        return result
    
    def _get_essential_columns(self, columns_metadata: List[Dict]) -> List[str]:
        """단일 테이블의 필수 컬럼 추출"""
        essential = []
        
        for col in columns_metadata:
            col_name = col['name'].lower()
            if (col_name.endswith('_id') or col_name == 'id' or 
                'name' in col_name or col_name in ['status', 'email']):
                essential.append(col['name'])
        
        return essential[:3] if essential else [col['name'] for col in columns_metadata[:2]]
    
    def validate_schema_elements(self, tables: List[str], columns: Dict[str, List[str]]) -> Tuple[bool, List[str]]:
        """단계 3: 검색된 테이블과 컬럼이 실제 스키마와 일치하는지 검증"""
        errors = []
        
        # 테이블 존재 여부 검증
        for table in tables:
            if table not in self.tables_info:
                errors.append(f"존재하지 않는 테이블: {table}")
        
        # 컬럼 존재 여부 검증
        for table, cols in columns.items():
            if table not in self.tables_info:
                continue
            
            available_columns = [col[0] for col in self.tables_info[table]['columns']]
            for col in cols:
                if col not in available_columns:
                    errors.append(f"테이블 {table}에 존재하지 않는 컬럼: {col}")
        
        return len(errors) == 0, errors
    
    def generate_final_query(self, user_request: str, tables: List[str], columns: Dict[str, List[str]]) -> Optional[str]:
        """단계 4: CodeLlama를 사용하여 최종 SQL 쿼리 생성 (개선된 버전)"""
        
        # 상세한 스키마 정보 생성
        detailed_schema = self._generate_detailed_schema_info(tables, columns)
        
        # LLM 타입에 따른 최적화된 프롬프트 생성
        if self.init_llm_type == "claude":
            prompt = f"""{detailed_schema}

사용자 요청: {user_request}

위의 정확한 스키마 정보를 바탕으로 SQL 쿼리를 생성해주세요.

중요한 규칙:
1. 반드시 위에 명시된 정확한 컬럼명만 사용하세요
2. ENUM 타입의 경우 명시된 값들만 사용하세요
3. JOIN 조건에는 올바른 외래키 관계를 사용하세요
4. SELECT 문만 생성하고 추가 설명은 포함하지 마세요
5. 쿼리는 세미콜론(;)으로 끝나야 합니다

응답 형식: 순수한 SQL 쿼리만 반환

SQL:"""
        else:
            prompt = f"""{detailed_schema}

사용자 요청: {user_request}

위 스키마 정보를 바탕으로 SQL 쿼리를 생성해주세요.

규칙:
1. 정확한 컬럼명 사용
2. ENUM 값 확인
3. 올바른 JOIN 조건
4. SELECT문만 생성
5. 세미콜론으로 종료

SQL:"""

        response = self.call_llm(prompt, stage="query_gen")
        if not response:
            print("❌ LLM 쿼리 생성 실패")
            return None

        # SQL 쿼리 추출
        sql_query = self.extract_sql_from_response(response)
        if not sql_query:
            print("❌ SQL 추출 실패")
            return None

        print(f"\n📝 추출된 SQL: {sql_query}")

        # 쿼리 검증
        print("\n🔍 생성된 SQL 쿼리 검증 중...")
        is_valid, errors = self.validate_sql_query(sql_query)

        if not is_valid:
            print("❌ SQL 쿼리 검증 실패:")
            for error in errors:
                print(f"  - {error}")
            
            # 더 상세한 오류 정보로 재시도
            error_details = self._analyze_query_errors(sql_query, errors)
            retry_sql = self._retry_query_generation(user_request, detailed_schema, error_details)
            
            if retry_sql:
                return retry_sql
            else:
                print("❌ 재시도도 실패")
                return None
        else:
            print("✅ SQL 쿼리 검증 성공")
            return sql_query
    
    def _generate_detailed_schema_info(self, tables: List[str], columns: Dict[str, List[str]]) -> str:
        """상세한 스키마 정보 생성"""
        schema_parts = ["=== 정확한 데이터베이스 스키마 정보 ===\n"]
        
        for table in tables:
            if table not in self.tables_info:
                continue
                
            # 테이블 설명 추가
            table_schema = self.table_schemas.get(table)
            if table_schema:
                schema_parts.append(f"📋 테이블: {table}")
                schema_parts.append(f"   설명: {table_schema.comment}")
            else:
                schema_parts.append(f"📋 테이블: {table}")
            
            schema_parts.append("   컬럼:")
            
            # 선택된 컬럼들의 상세 정보
            selected_columns = columns.get(table, [])
            for col_info in self.tables_info[table]['columns']:
                col_name = col_info[0]
                
                # 선택된 컬럼만 표시하거나, 선택된 컬럼이 없으면 모든 컬럼 표시
                if selected_columns and col_name not in selected_columns:
                    continue
                
                col_type = col_info[1]
                null_allowed = col_info[2] if len(col_info) > 2 else "YES"
                col_key = col_info[3] if len(col_info) > 3 else ""
                col_default = col_info[4] if len(col_info) > 4 else ""
                col_extra = col_info[5] if len(col_info) > 5 else ""
                
                # 컬럼 상세 정보 생성
                col_detail = f"     - {col_name}: {col_type}"
                
                if col_key == "PRI":
                    col_detail += " (Primary Key)"
                elif col_key == "MUL":
                    col_detail += " (Foreign Key)"
                
                if null_allowed == "NO":
                    col_detail += " NOT NULL"
                
                if col_extra == "auto_increment":
                    col_detail += " AUTO_INCREMENT"
                
                # ENUM 타입의 경우 가능한 값들 표시
                if "enum" in col_type.lower():
                    col_detail += f" 가능한 값: {col_type}"
                
                if col_default and col_default != "NULL":
                    col_detail += f" DEFAULT {col_default}"
                
                schema_parts.append(col_detail)
            
            # 외래키 관계 정보 추가
            if table_schema and table_schema.foreign_keys:
                schema_parts.append("   외래키 관계:")
                for fk in table_schema.foreign_keys:
                    schema_parts.append(f"     - {fk['from_column']} → {fk['to_table']}.{fk['to_column']}")
            
            schema_parts.append("")  # 테이블 간 구분
        
        # 중요 주의사항 추가
        schema_parts.extend([
            "⚠️ 중요 주의사항:",
            "- 위에 명시된 정확한 컬럼명만 사용하세요",
            "- ENUM 타입은 명시된 값만 사용 가능합니다",
            "- 존재하지 않는 컬럼이나 값을 사용하지 마세요",
            "- JOIN 시 올바른 외래키 관계를 사용하세요",
            ""
        ])
        
        return "\n".join(schema_parts)
    
    def _analyze_query_errors(self, sql_query: str, errors: List[str]) -> str:
        """쿼리 오류 분석"""
        error_analysis = ["쿼리 오류 분석:"]
        
        for error in errors:
            if "존재하지 않는" in error:
                error_analysis.append(f"- {error}")
                if "컬럼" in error:
                    error_analysis.append("  → 스키마에 명시된 정확한 컬럼명을 사용하세요")
                elif "테이블" in error:
                    error_analysis.append("  → 제공된 테이블명만 사용하세요")
            elif "JOIN" in error:
                error_analysis.append(f"- {error}")
                error_analysis.append("  → 외래키 관계를 확인하고 올바른 조인 조건을 사용하세요")
            else:
                error_analysis.append(f"- {error}")
        
        return "\n".join(error_analysis)
    
    def _retry_query_generation(self, user_request: str, schema_info: str, error_details: str) -> Optional[str]:
        """오류 정보를 바탕으로 쿼리 재생성"""
        retry_prompt = f"""{schema_info}

사용자 요청: {user_request}

이전 시도에서 다음 오류가 발생했습니다:
{error_details}

위 오류를 수정하여 올바른 SQL 쿼리를 생성해주세요.
스키마 정보를 정확히 확인하고 존재하는 컬럼과 값만 사용하세요.

수정된 SQL 쿼리만 반환하세요:"""

        print("\n🔄 쿼리 재생성 시도 중...")
        retry_response = self.call_llm(retry_prompt, stage="query_gen")
        
        if retry_response:
            retry_sql = self.extract_sql_from_response(retry_response)
            if retry_sql:
                print(f"📝 재생성된 SQL: {retry_sql}")
                
                # 재검증
                is_valid, new_errors = self.validate_sql_query(retry_sql)
                if is_valid:
                    print("✅ 수정된 쿼리 검증 성공")
                    return retry_sql
                else:
                    print("❌ 수정된 쿼리도 검증 실패:")
                    for error in new_errors:
                        print(f"  - {error}")
        
        return None
    
    def extract_sql_from_response(self, response: str) -> Optional[str]:
        """LLM 응답에서 SQL 쿼리 추출 (개선된 버전)"""
        if not response:
            return None
        
        print("🔍 LLM 응답에서 SQL 추출 중...")
        print(f"📄 원본 응답 (처음 200자): {response[:200]}...")
        
        # 1단계: 코드 블록에서 SQL 추출 시도
        sql_query = self._extract_from_code_blocks(response)
        if sql_query:
            print("✅ 코드 블록에서 SQL 추출 성공")
            return sql_query
        
        # 2단계: SELECT로 시작하는 라인 찾기
        sql_query = self._extract_from_select_lines(response)
        if sql_query:
            print("✅ SELECT 라인에서 SQL 추출 성공")
            return sql_query
        
        # 3단계: 정규식으로 SQL 패턴 찾기
        sql_query = self._extract_with_regex(response)
        if sql_query:
            print("✅ 정규식으로 SQL 추출 성공")
            return sql_query
        
        print("❌ SQL 추출 실패")
        return None
    
    def _extract_from_code_blocks(self, response: str) -> Optional[str]:
        """코드 블록(```sql)에서 SQL 추출"""
        import re
        
        # ```sql ... ``` 패턴 찾기
        sql_blocks = re.findall(r'```sql\s*(.*?)\s*```', response, re.DOTALL | re.IGNORECASE)
        if sql_blocks:
            sql = sql_blocks[0].strip()
            return self._clean_sql(sql)
        
        # ``` ... ``` (sql 태그 없음) 패턴 찾기
        code_blocks = re.findall(r'```\s*(.*?)\s*```', response, re.DOTALL)
        for block in code_blocks:
            block = block.strip()
            if block.upper().startswith('SELECT'):
                return self._clean_sql(block)
        
        return None
    
    def _extract_from_select_lines(self, response: str) -> Optional[str]:
        """SELECT로 시작하는 라인들에서 SQL 추출"""
        lines = response.split('\n')
        sql_lines = []
        in_sql = False
        
        for line in lines:
            line = line.strip()
            
            # SELECT로 시작하면 SQL 시작
            if line.upper().startswith('SELECT'):
                in_sql = True
                sql_lines = [line]
            elif in_sql:
                # SQL이 시작된 후 계속 추가
                if line and not line.startswith('#') and not line.startswith('//') and not line.startswith('--'):
                    sql_lines.append(line)
                    
                    # 세미콜론으로 끝나면 종료
                    if line.endswith(';'):
                        break
                elif not line:  # 빈 줄은 무시
                    continue
                else:  # 주석이나 설명이 나오면 SQL 종료
                    break
        
        if sql_lines:
            sql = ' '.join(sql_lines)
            return self._clean_sql(sql)
        
        return None
    
    def _extract_with_regex(self, response: str) -> Optional[str]:
        """정규식으로 SQL 패턴 추출"""
        import re
        
        # SELECT로 시작해서 세미콜론까지의 패턴
        pattern = r'SELECT\s+.*?;'
        matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
        
        if matches:
            # 가장 긴 매치 선택 (더 완전한 쿼리일 가능성)
            sql = max(matches, key=len)
            return self._clean_sql(sql)
        
        return None
    
    def _clean_sql(self, sql: str) -> str:
        """SQL 쿼리 정리"""
        if not sql:
            return ""
        
        # 불필요한 공백 제거
        sql = ' '.join(sql.split())
        
        # 세미콜론 확인 및 추가
        if not sql.endswith(';'):
            sql += ';'
        
        # 한국어 설명이나 마크다운 제거
        import re
        
        # 백틱 제거
        sql = re.sub(r'```\w*', '', sql)
        sql = re.sub(r'```', '', sql)
        
        # SQL 키워드 이후 한글 설명 제거 (예: "; 이 쿼리는..." 부분)
        sql = re.sub(r';\s*[가-힣].*$', ';', sql)
        
        # "위 쿼리는", "이 쿼리는" 등으로 시작하는 설명 제거
        sql = re.sub(r'\s+[위이]\s*쿼리는.*$', '', sql)
        
        return sql.strip()
    
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
        if self.init_llm_type == "claude":
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
        elif "gemma" in self.codellama_model.lower():
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

위의 테이블 스키마를 참고하여 사용자 요청에 필요한 테이블들을 선택해주세요.

중요: JSON 형식으로만 응답하세요. 설명이나 예시는 포함하지 마세요.

JSON:
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
        
        # LLM 분석 실패시 다른 LLM 기반 방식으로 폴백
        print("🔄 LLM 기반 폴백 방식으로 재시도...")
        return self.extract_relevant_tables_fallback(user_request)
    
    def extract_relevant_tables_fallback(self, user_request: str) -> List[str]:
        """LLM 기반 순수 의미적 분석 폴백 방식"""
        print("🧠 LLM 기반 의미적 분석으로 테이블 선택 중...")
        
        # 모든 테이블의 설명 정보 수집
        table_descriptions = {}
        for table_name, schema in self.table_schemas.items():
            table_descriptions[table_name] = schema.comment
        
        # 테이블 설명 정보를 프롬프트용으로 정리
        descriptions_text = "데이터베이스 테이블 목록:\n"
        for table, desc in table_descriptions.items():
            descriptions_text += f"- {table}: {desc}\n"
        
        # LLM을 활용한 테이블 선택
        if self.init_llm_type == "claude":
            prompt = f"""{descriptions_text}

사용자 요청: "{user_request}"

위의 테이블 설명을 바탕으로 사용자 요청을 처리하는데 필요한 테이블들을 선택해주세요.

분석 기준:
1. 사용자가 원하는 정보와 직접 관련된 테이블
2. 데이터 조회나 분석에 필요한 테이블
3. 비즈니스 로직상 연관된 테이블

응답은 반드시 JSON 형식으로만 반환해주세요:
{{"tables": ["table1", "table2"], "reason": "선택 이유"}}"""
        else:
            prompt = f"""{descriptions_text}

사용자 요청: {user_request}

위 테이블들 중에서 사용자 요청에 필요한 테이블을 선택하여 JSON으로 반환해주세요.

JSON:
{{"tables": ["테이블명1", "테이블명2"], "reason": "선택 이유"}}

JSON:"""
        
        response = self.call_llm(prompt)
        selected_tables = []
        
        if response:
            try:
                import json
                response_clean = response.strip()
                json_start = response_clean.find('{')
                json_end = response_clean.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_str = response_clean[json_start:json_end]
                    result = json.loads(json_str)
                    
                    if 'tables' in result and isinstance(result['tables'], list):
                        # 유효한 테이블만 필터링
                        selected_tables = [
                            table for table in result['tables'] 
                            if table in self.table_schemas
                        ]
                        
                        if selected_tables:
                            print(f"🎯 LLM 폴백 분석 결과: {selected_tables}")
                            if 'reason' in result:
                                print(f"📝 선택 이유: {result['reason']}")
                            return selected_tables
                        
            except (json.JSONDecodeError, KeyError) as e:
                print(f"⚠️ LLM 폴백 응답 파싱 실패: {e}")
        
        # 최종 폴백: 가장 중심적인 테이블들 반환
        print("⚠️ LLM 분석 실패. 중심성 높은 테이블들로 폴백...")
        core_tables = list(self.table_schemas.keys())[:3]  # 처음 3개 테이블
        return core_tables
    
    def extract_relevant_tables(self, user_request: str) -> List[str]:
        """사용자 요청에서 관련 테이블 추출 (그래프 기반 검색)"""
        # Neo4j 그래프 메타 정보 기반 검색
        return self.search_tables_with_graph_metadata(user_request)
    
    def generate_enhanced_prompt(self, user_request: str, relevant_tables: List[str], join_sequence: List[Dict]) -> str:
        """Neo4j 정보를 활용한 향상된 프롬프트 생성"""
        schema_info = self.generate_schema_prompt()
        
        # 테이블 별칭 규칙 추가
        alias_info = "테이블 별칭 규칙:\n"
        for table in relevant_tables:
            # 첫 글자를 별칭으로 사용하되, 중복을 피함
            base_alias = table[0].lower()
            alias_info += f"- {table} AS {base_alias} (예: {base_alias}.column_name)\n"
        
        # 조인 정보 생성
        join_info = "\n최적 조인 순서 및 관계:\n"
        for i, seq in enumerate(join_sequence):
            table = seq['table']
            joins = seq['joins']
            
            join_info += f"{i+1}. {table}\n"
            for join in joins:
                join_info += f"   └─ {join['from_table']}.{join['from_column']} = {join['to_table']}.{join['to_column']} (신뢰도: {join['confidence']})\n"
        
        # 테이블별 필수 컬럼 정보 추가
        column_info = "\n테이블별 주요 컬럼 (정확한 이름 사용 필수):\n"
        for table in relevant_tables:
            if table in self.tables_info:
                info = self.tables_info[table]
                column_info += f"\n{table} 테이블:\n"
                for col in info['columns']:
                    col_name, col_type = col[0], col[1]
                    # 컬럼 타입에 따른 사용법 힌트 추가
                    usage_hint = ""
                    if "INT" in col_type.upper():
                        usage_hint = "숫자 연산/비교 가능"
                    elif "DECIMAL" in col_type.upper():
                        usage_hint = "소수점 연산 가능"
                    elif "DATE" in col_type.upper() or "TIMESTAMP" in col_type.upper():
                        usage_hint = "날짜/시간 함수 사용 가능"
                    elif "ENUM" in col_type.upper():
                        usage_hint = f"가능한 값: {col_type}"
                    
                    column_info += f"  - {col_name}: {col_type}"
                    if usage_hint:
                        column_info += f" ({usage_hint})"
                    column_info += "\n"
        
        # 관련 테이블의 상세 정보
        table_details = "\n관련 테이블 상세 정보:\n"
        for table in relevant_tables:
            if table in self.table_schemas:
                schema = self.table_schemas[table]
                table_details += f"\n{table} 테이블:\n"
                table_details += f"  설명: {schema.comment}\n"
                table_details += f"  주요 컬럼: {', '.join([col['name'] for col in schema.columns[:5]])}\n"
        
        # LLM 타입과 모델에 따른 프롬프트 선택
        if self.init_llm_type == "claude":
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
        elif "starcoder" in self.codellama_model.lower():
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
        
        return prompt
    
    def generate_sql_query(self, user_request: str) -> Optional[str]:
        """사용자 요청에 따른 SQL 쿼리 생성"""
        schema_info = self.generate_schema_prompt()
        
        # LLM 타입과 모델에 따른 프롬프트 선택
        if self.init_llm_type == "claude":
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
        elif "starcoder" in self.codellama_model.lower():
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
        response = self.call_llm(prompt, stage="query_gen")
        
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
        """생성된 SQL 쿼리 실행 (검증 포함)"""
        try:
            # 실행 전 쿼리 검증
            is_valid, errors = self.validate_sql_query(query)
            if not is_valid:
                print("❌ SQL 쿼리 검증 실패:")
                for error in errors:
                    print(f"  - {error}")
                return None
            
            # 쿼리 실행 전 디버깅 정보 출력
            print("\n🔍 실행할 SQL 쿼리:")
            print(f"```sql\n{query}\n```")
            
            # 테이블 정보 출력
            print("\n📋 관련 테이블 정보:")
            import re
            table_pattern = r'(?:FROM|JOIN)\s+(\w+)'
            found_tables = re.findall(table_pattern, query, re.IGNORECASE)
            
            for table in found_tables:
                if table in self.tables_info:
                    info = self.tables_info[table]
                    print(f"\n테이블: {table}")
                    print("컬럼:")
                    for col in info['columns']:
                        col_name, col_type = col[0], col[1]
                        print(f"  - {col_name}: {col_type}")
            
            # 쿼리 실행
            with self.connection.cursor() as cursor:
                print("\n⚡ 쿼리 실행 중...")
                cursor.execute(query)
                results = cursor.fetchall()
                print("✅ 쿼리 실행 성공")
                return results
                
        except Exception as e:
            print(f"❌ 쿼리 실행 실패: {e}")
            print("💡 오류 상세:")
            import traceback
            print(traceback.format_exc())
            return None
    
    def run_interactive_mode(self):
        """대화형 모드 실행"""
        try:
            # 시작 메시지 및 설정 표시
            print("=" * 70)
            print("🚀 하이브리드 SQL 쿼리 생성기 시작 (MariaDB + Neo4j)")
            print("\n📋 LLM 설정:")
            print(f"  - 초기 분석: {self.init_llm_type.upper()}")
            if self.init_llm_type == "claude":
                print(f"    모델: {self.claude_model}")
            else:
                print(f"    모델: {self.codellama_model}")
            print(f"  - 쿼리 생성: {self.query_llm_type.upper()}")
            print(f"    모델: {self.codellama_model}")
            print("=" * 70)
            
            # 초기화 단계
            try:
                # MariaDB 연결 확인
                if not self.connect_to_database():
                    return
                
                # LLM 모델 가용성 확인
                if not self.check_model_availability():
                    return  # 오류 메시지는 check_model_availability에서 출력됨
                
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
                print("💡 대화형 SQL 쿼리 생성 모드")
                print("종료하려면 'quit' 또는 'exit'를 입력하세요")
                print("컬럼 검색 테스트: 'test_columns'")
                print("Neo4j 메타데이터 확인: 'check_metadata'")
                print("=" * 60)
                
                # 대화형 루프
                while True:
                    try:
                        user_input = input("\n📝 검색하고 싶은 내용을 설명해주세요: ").strip()
                        
                        if user_input.lower() in ['quit', 'exit', '종료']:
                            break
                        
                        if not user_input:
                            continue
                        
                        # 테스트 명령어 처리
                        if user_input.lower() == 'test_columns':
                            print("\n🧪 컬럼 검색 기능 테스트")
                            self.verify_column_search_improvement()
                            continue
                        
                        if user_input.lower() == 'check_metadata':
                            print("\n🔍 Neo4j 메타데이터 확인")
                            self.test_neo4j_column_metadata()
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
                        print(f"❌ 대화형 모드 실행 중 오류: {e}")
                        import traceback
                        print("💡 오류 상세:")
                        print(traceback.format_exc())
            
            finally:
                self.disconnect_from_database()
                print("🏁 프로그램이 종료되었습니다.")
                
        except Exception as e:
            print(f"❌ 프로그램 초기화 중 오류 발생: {e}")
            import traceback
            print("💡 오류 상세:")
            print(traceback.format_exc())
            self.disconnect_from_database()
    
    def test_neo4j_column_metadata(self) -> None:
        """Neo4j 컬럼 메타데이터 조회 테스트 (디버깅용)"""
        if not self.neo4j_driver:
            print("❌ Neo4j 연결이 필요합니다.")
            return
        
        print("🧪 Neo4j 컬럼 메타데이터 테스트 중...")
        
        try:
            with self.neo4j_driver.session() as session:
                # 모든 테이블과 컬럼 조회
                query = """
                MATCH (t:Table)-[:HAS_COLUMN]->(c:Column)
                RETURN t.name as table_name, 
                       c.name as column_name, 
                       c.type as column_type,
                       c.nullable as nullable,
                       c.auto_increment as auto_increment
                ORDER BY t.name, c.name
                """
                
                result = session.run(query)
                
                current_table = None
                for record in result:
                    table_name = record['table_name']
                    column_name = record['column_name']
                    column_type = record['column_type']
                    nullable = record.get('nullable', True)
                    auto_increment = record.get('auto_increment', False)
                    
                    if current_table != table_name:
                        current_table = table_name
                        print(f"\n📋 테이블: {table_name}")
                    
                    col_info = f"  - {column_name} ({column_type})"
                    if not nullable:
                        col_info += " NOT NULL"
                    if auto_increment:
                        col_info += " AUTO_INCREMENT"
                    print(col_info)
                
                # 테이블 수 카운트
                table_count_query = "MATCH (t:Table) RETURN count(t) as table_count"
                table_count = session.run(table_count_query).single()['table_count']
                
                # 컬럼 수 카운트
                column_count_query = "MATCH (c:Column) RETURN count(c) as column_count"
                column_count = session.run(column_count_query).single()['column_count']
                
                print(f"\n📊 총 테이블: {table_count}개, 총 컬럼: {column_count}개")
                
        except Exception as e:
            print(f"❌ Neo4j 컬럼 메타데이터 테스트 실패: {e}")
    
    def verify_column_search_improvement(self, user_request: str = "사용자들의 주문 정보를 보여줘") -> None:
        """개선된 컬럼 검색 기능 검증"""
        print("🔍 개선된 컬럼 검색 기능 테스트 중...")
        print(f"테스트 요청: {user_request}")
        
        # 1. 먼저 테이블 검색
        relevant_tables = self.extract_relevant_tables(user_request)
        print(f"검색된 테이블: {relevant_tables}")
        
        if not relevant_tables:
            print("❌ 관련 테이블을 찾을 수 없어 테스트를 중단합니다.")
            return
        
        # 2. 개선된 컬럼 검색 테스트
        selected_columns = self.find_target_columns(user_request, relevant_tables)
        
        if selected_columns:
            print("✅ 컬럼 검색 성공!")
            for table, columns in selected_columns.items():
                print(f"  📋 {table}: {', '.join(columns)}")
        else:
            print("❌ 컬럼 검색 실패")
    
    def get_column_metadata_summary(self) -> Dict[str, Dict]:
        """전체 컬럼 메타데이터 요약 정보 반환"""
        if not self.neo4j_driver:
            return {}
        
        summary = {}
        
        try:
            with self.neo4j_driver.session() as session:
                query = """
                MATCH (t:Table)-[:HAS_COLUMN]->(c:Column)
                RETURN t.name as table_name,
                       collect({
                           name: c.name,
                           type: c.type,
                           nullable: c.nullable,
                           auto_increment: c.auto_increment
                       }) as columns
                ORDER BY t.name
                """
                
                result = session.run(query)
                
                for record in result:
                    table_name = record['table_name']
                    columns = record['columns']
                    
                    summary[table_name] = {
                        'column_count': len(columns),
                        'columns': columns,
                        'id_columns': [col['name'] for col in columns if col['name'].lower().endswith('_id') or col['name'].lower() == 'id'],
                        'name_columns': [col['name'] for col in columns if 'name' in col['name'].lower()],
                        'date_columns': [col['name'] for col in columns if 'date' in col['name'].lower() or 'created_at' in col['name'].lower() or 'updated_at' in col['name'].lower()]
                    }
                
        except Exception as e:
            print(f"❌ 컬럼 메타데이터 요약 생성 실패: {e}")
        
        return summary

def main():
    """메인 함수"""
    import sys
    
    generator = HybridQueryGenerator()
    
    # 명령행 인수 확인
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "test":
            # 간단한 테스트 모드
            print("🧪 간단한 테스트 모드")
            test_query_generation(generator)
            return
        elif command == "demo":
            # 데모 모드 - 몇 가지 예제 쿼리 테스트
            print("🎬 데모 모드")
            demo_queries(generator)
            return
    
    # 기본 대화형 모드
    generator.run_interactive_mode()

def test_query_generation(generator):
    """쿼리 생성 테스트"""
    try:
        # 데이터베이스 연결
        if not generator.connect_to_database():
            return
        
        # 기본 초기화
        generator.analyze_all_tables()
        generator.extract_schema_from_ddl()
        
        # 간단한 테스트 요청
        test_request = "활성 사용자들의 이름과 이메일을 보여주세요"
        print(f"\n🔍 테스트 요청: {test_request}")
        
        # 테이블 검색
        tables = ["users"]  # 간단한 테스트용
        print(f"📋 사용할 테이블: {tables}")
        
        # 컬럼 검색 (폴백 모드 사용)
        columns = generator._fallback_column_search(test_request, tables)
        print(f"📋 선택된 컬럼: {columns}")
        
        # 쿼리 생성
        if columns:
            sql_query = generator.generate_final_query(test_request, tables, columns)
            
            if sql_query:
                print(f"\n✅ 생성된 쿼리: {sql_query}")
                
                # 실행 테스트
                results = generator.execute_query(sql_query)
                if results:
                    print(f"📊 결과: {len(results)}개 행")
                    for i, row in enumerate(results[:3], 1):
                        print(f"  {i}: {row}")
            else:
                print("❌ 쿼리 생성 실패")
        
    except Exception as e:
        print(f"❌ 테스트 중 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        generator.disconnect_from_database()

def demo_queries(generator):
    """데모 쿼리들"""
    demo_requests = [
        "활성 사용자의 수를 알려주세요",
        "사용자별 주문 수를 보여주세요", 
        "가장 비싼 상품 5개를 보여주세요"
    ]
    
    try:
        if not generator.connect_to_database():
            return
            
        generator.analyze_all_tables()
        generator.extract_schema_from_ddl()
        
        for i, request in enumerate(demo_requests, 1):
            print(f"\n{'='*50}")
            print(f"🎬 데모 {i}: {request}")
            print('='*50)
            
            # 간소화된 테스트
            if "사용자" in request:
                tables = ["users"]
                columns = {"users": ["user_id", "username", "email", "status"]}
            elif "주문" in request:
                tables = ["users", "orders"]
                columns = {"users": ["user_id", "username"], "orders": ["order_id", "user_id"]}
            elif "상품" in request:
                tables = ["products"]
                columns = {"products": ["product_id", "product_name", "price"]}
            else:
                continue
                
            sql_query = generator.generate_final_query(request, tables, columns)
            
            if sql_query:
                print(f"✅ SQL: {sql_query}")
            else:
                print("❌ 쿼리 생성 실패")
                
    except Exception as e:
        print(f"❌ 데모 중 오류: {e}")
    finally:
        generator.disconnect_from_database()

if __name__ == "__main__":
    main()
