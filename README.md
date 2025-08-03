# LLM-SQL-Maker

자연어 질의를 SQL 쿼리로 변환하는 AI 기반 Query Generator 시스템

## 개요

이 시스템은 Neo4j 그래프 데이터베이스를 메타데이터 저장소로 활용하고, OLLAMA의 CodeLlama 모델을 통해 자연어 질의를 지능적으로 SQL 쿼리로 변환합니다.

## 시스템 아키텍처

### 인프라 계층
- **MariaDB** (port 32000): 실제 비즈니스 데이터 저장
- **Neo4j** (port 7687/7474): RDB 스키마 메타데이터 그래프 저장
- **OLLAMA** (port 11434): CodeLlama 7B 모델 서빙

### AI/LLM 계층
- **OLLAMA + CodeLlama:7b**: 자연어를 Cypher 쿼리로 변환
- **LangChain**: AI 체인 관리 및 프롬프트 엔지니어링
- **GraphCypherQAChain**: Neo4j와 LLM 연동

### 데이터 계층

#### Neo4j 그래프 모델
- `(:Table)` 노드: 테이블 정보
- `(:Column)` 노드: 컬럼 정보  
- `[:HAS_COLUMN]` 관계: 테이블-컬럼 연결
- `[:REFERENCES]` 관계: 외래키 관계

#### MariaDB E-commerce 데이터
- **테이블 구성**: users, products, orders, order_items, categories, reviews
- **설계**: 복잡한 조인 테스트를 위한 정규화된 스키마

## 동작 프로세스

### 1. 시스템 초기화

```python
# 1. Neo4j/MariaDB 연결
# 2. RDB 스키마 → Neo4j 그래프 변환
# 3. OLLAMA LLM 초기화  
# 4. GraphCypherQAChain 생성
```

### 2. 스키마 메타데이터 그래프화

```cypher
# 테이블 정보를 Neo4j 노드로 저장
CREATE (t:Table {name: 'users', comment: '사용자 계정 정보'})

# 컬럼 정보와 관계 생성
CREATE (c:Column {name: 'user_id', type: 'INT', is_pk: true})
CREATE (t)-[:HAS_COLUMN]->(c)

# 외래키 관계 생성
CREATE (c1)-[:REFERENCES]->(c2)
```

## 쿼리 변환 파이프라인

### Step 1: 자연어 질의 접수
```python
user_input = "사용자 테이블의 모든 컬럼을 보여주세요"
```

### Step 2: LLM 기반 Cypher 생성
```python
prompt = """당신은 Neo4j 전문가입니다. 
스키마: {schema}
질문: {query}
Cypher 쿼리만 반환하세요."""

result = llm.invoke(prompt)
# 결과: MATCH (t:Table {name: 'users'})-[:HAS_COLUMN]->(c:Column) RETURN c.name
```

### Step 3: Cypher 실행 및 메타데이터 조회
```python
cypher_result = neo4j.query(cypher_query)
# 결과: [{'column_name': 'user_id'}, {'column_name': 'username'}, ...]
```

### Step 4: SQL 쿼리 변환
```python
# Cypher 결과를 기반으로 SQL 생성
columns = [result['column_name'] for result in cypher_result]
sql_query = f"SELECT {', '.join(columns)} FROM users;"
```

### Step 5: SQL 실행 및 결과 반환
```python
sql_results = mariadb.execute(sql_query)
# 실제 비즈니스 데이터 반환
```

## 핵심 기능 및 특징

### 지능적 스키마 인식
- RDB 스키마가 Neo4j 그래프로 완전히 모델링
- 테이블 간 관계, 컬럼 타입, 제약사항 등 메타데이터 보존
- 외래키 관계를 통한 JOIN 최적화 가능

### LangChain 기반 AI 파이프라인
- **GraphCypherQAChain**: Neo4j + LLM 통합
- **커스텀 프롬프트**: Cypher 생성 최적화
- **중간 단계 추적**: 디버깅 및 투명성 확보

### 실시간 Query-to-Query 변환
```
자연어 → Cypher → Neo4j 메타데이터 → SQL → MariaDB 데이터
```

## 실행 방법

### 1. 환경 설정
```bash
# 의존성 설치
pip install -r requirements.txt

# Docker 환경 실행
docker-compose up -d
```

### 2. 애플리케이션 실행
```bash
python query_gen.py
```

## 기술 스택

- **Python 3.x**
- **LangChain**: AI 체인 관리
- **Neo4j**: 그래프 데이터베이스
- **MariaDB**: 관계형 데이터베이스
- **OLLAMA**: 로컬 LLM 서빙
- **LLM**: 코드 생성 특화 모델(예: CodeLlama)이 필요하나 현재 상태에서는 Gemma3:12B도 동작함.
- **Docker**: 컨테이너 오케스트레이션