# Code LLM - Intelligent SQL Query Generator

MariaDB와 Neo4j를 활용한 지능형 SQL 쿼리 생성 시스템입니다. LLM(Large Language Model)을 사용하여 자연어를 SQL 쿼리로 변환하며, Neo4j 그래프 데이터베이스를 활용하여 테이블 간의 관계를 최적화합니다.

## 특징

- 🤖 하이브리드 LLM 지원 (OLLAMA 로컬 모델 + Claude API)
- 📊 MariaDB 스키마 자동 분석
- 🔗 Neo4j 그래프 기반 테이블 관계 최적화
- 🎯 자연어 질의를 SQL로 변환
- ⚡ 최적의 테이블 조인 순서 자동 결정

## 시스템 요구사항

- Python 3.8 이상
- Docker 및 Docker Compose
- OLLAMA (로컬 LLM 사용시)
- Claude API 키 (Claude 사용시)

## 설치 방법

1. 저장소 클론
```bash
git clone https://github.com/theprismdata/code_llm.git
cd code_llm
```

2. Python 가상환경 생성 및 활성화
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는
.\venv\Scripts\activate  # Windows
```

3. 필요한 패키지 설치
```bash
pip install -r requirements.txt
```

4. Docker Compose로 데이터베이스 실행
```bash
docker-compose up -d
```

## 데이터베이스 설정

### MariaDB 설정
- 기본 포트: 32000
- 데이터베이스: llm_db_test
- 사용자: genai
- 비밀번호: genai1234

MariaDB 테이블은 자동으로 생성되며, 다음 테이블들이 포함됩니다:
- users (사용자 정보)
- categories (상품 카테고리)
- products (상품 정보)
- orders (주문 정보)
- order_items (주문 상세)
- reviews (상품 리뷰)

### Neo4j 설정
- 기본 포트: 7687
- 사용자: neo4j
- 비밀번호: password123

## LLM 설정

### OLLAMA 사용 (기본값)
1. OLLAMA 설치 ([ollama.ai](https://ollama.ai))
2. 코드에서 지원하는 모델 중 하나 설치:
```bash
# 추천 모델 (4GB 메모리 기준)
ollama pull codellama:7b        # 한글 지원 우수, 빠름
# 또는
ollama pull deepseek-coder:6.7b # 성능 최고
```

### Claude API 사용 (선택사항)
1. Anthropic에서 API 키 발급
2. 환경변수 설정:
```bash
export ANTHROPIC_API_KEY='your-api-key'
```

## 사용 방법

1. 프로그램 실행
```bash
python query_gen.py
```

2. 자연어로 쿼리 요청하기
예시 질문들:
- "모든 사용자의 주문 내역을 보여줘"
- "가장 많이 팔린 상품 TOP 5를 카테고리별로 보여줘"
- "5점 만점의 리뷰를 받은 상품들의 카테고리별 판매 실적을 보여줘"

### 복잡한 조인 예시

6개 테이블을 모두 활용하는 복잡한 쿼리 예시:
```sql
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
```

## 작동 방식

1. **스키마 분석**: MariaDB의 테이블 구조를 분석하여 컬럼 정보와 관계를 파악

2. **그래프 구성**: 테이블 간의 관계를 Neo4j 그래프로 구성
   - Foreign Key 관계
   - 의미적 관계 (컬럼명 기반)
   - 네이밍 패턴 기반 관계

3. **최적 조인 경로**: Neo4j를 사용하여 테이블 간 최적의 조인 경로 계산

4. **쿼리 생성**: LLM을 사용하여 자연어를 SQL로 변환
   - 스키마 정보 활용
   - 최적 조인 순서 적용
   - WHERE 조건 자동 생성

## 주의사항

1. 메모리 사용량
   - OLLAMA 모델 선택 시 서버 메모리 고려 필요
   - 4GB 메모리의 경우 `codellama:7b` 또는 `deepseek-coder:6.7b` 추천

2. API 키 보안
   - Claude API 키는 환경변수로 관리
   - API 키를 코드에 직접 포함하지 않도록 주의

3. 데이터베이스 연결
   - MariaDB와 Neo4j가 모두 실행 중이어야 함
   - 방화벽 설정 확인 필요

## 라이센스

이 프로젝트는 GNU GENERAL PUBLIC LICENSE v3 라이센스를 따릅니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.
